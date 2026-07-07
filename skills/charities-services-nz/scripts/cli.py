#!/usr/bin/env python3
"""Charities Services NZ OData CLI.

Read-only wrapper for https://www.odata.charities.govt.nz/ using Python stdlib.
Useful for registered charity lookup, officer records, annual-return financials,
grant-making signals, and schema discovery.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, NoReturn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE = "https://www.odata.charities.govt.nz/"
UA = "Mozilla/5.0 (compatible; thecolab-ai-skills/charities-services-nz; +https://github.com/thecolab-ai/.skills)"
MAX_TOP = 1000
DEFAULT_ORG_SELECT = "OrganisationId,Name,CharityRegistrationNumber,RegistrationStatus,NZBNNumber,CompaniesOfficeNumber,WebSiteURL,CharityEmailAddress,PostalAddressCity,StreetAddressCity,MainActivityId,MainBeneficiaryId,MainSectorId,DateRegistered,DeregistrationDate,AnnualReturnDueDate,ModifiedOn,PurposeToGiveGrantsAndDonations"
DEFAULT_OFFICER_SELECT = "OfficerId,OrganisationId,FullName,FirstName,MiddleName,LastName,OfficerStatus,PositioninOrganisation,PositionAppointmentDate,LastDateAsAnOfficer,BodyCorporateName,IsaBodyCorporate,ModifiedOn"
DEFAULT_RETURN_SELECT = "Id,EntityType,Name,CharityRegistrationNumber,RegistrationStatus,CharitySummaryURL,MainActivityName,MainBeneficiaryName,MainSectorName,Activities,AnnualReturnId,ReportingTier,YearEnded,FinancialPositionDate,GrantsPaidWithinNZ,GrantsPaidOutsideNZ,GrantsAndDonationsMade,GrantsorDonationsPaid,TotalGrossIncome,TotalExpenditure,TotalAssets,TotalLiabilities,TotalEquity,NetSurplusDeficitForTheYear,DonationsKoha,GovtGrantsContracts,GeneralGrantsReceived,ServiceDeliveryGrantsContracts,ModifiedOn"
DEFAULT_GRANTMAKER_SELECT = "Id,EntityType,Name,CharityRegistrationNumber,RegistrationStatus,CharitySummaryURL,MainActivityName,MainSectorName,YearEnded,GrantsPaidWithinNZ,GrantsPaidOutsideNZ,GrantsAndDonationsMade,GrantsorDonationsPaid,TotalGrossIncome,TotalExpenditure,TotalAssets"


class UpstreamBlocked(Exception):
    """Raised when the public OData endpoint appears to be bot-blocking JSON."""


class UpstreamUnavailable(Exception):
    """Raised for network/HTTP/service failures that should be reported gracefully."""


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"charities-services-nz: {msg}", file=sys.stderr)
    raise SystemExit(code)


def clamp_limit(n: int) -> int:
    return max(1, min(int(n), MAX_TOP))


def request(url: str, accept: str = "application/json", timeout: int = 20) -> tuple[str, str]:
    # Route through the shared nzfetch helper (browser-shaped headers + rotating
    # proxy retry on a bot-block). fetch_bytes preserves the exact per-call Accept
    # and lets us keep the original utf-8-sig decoding (charities OData/CSV ships a
    # BOM). expect_json is inferred from `accept`: True for application/json (so an
    # interstitial is caught), False for text/csv and application/xml.
    try:
        body, content_type, _final = nzfetch.fetch_bytes(url, accept=accept, timeout=timeout)
    except nzfetch.Blocked as e:
        raise UpstreamBlocked(f"blocked_by_upstream: {e}") from e
    except nzfetch.FetchError as e:
        raise UpstreamUnavailable(f"network error calling {url}: {e}") from e
    return body.decode("utf-8-sig", "replace"), content_type


def odata_url(entity: str, params: dict[str, Any]) -> str:
    if not entity or any(ch in entity for ch in "/?&"):
        die("entity must be an OData collection name, e.g. Organisations")
    return BASE + entity + "?" + urllib.parse.urlencode(params)


def odata_get(entity: str, *, select: str | None = None, filter_: str | None = None,
              orderby: str | None = None, top: int = 10, skip: int = 0,
              inlinecount: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    params: dict[str, str | int] = {"$top": clamp_limit(top), "$skip": max(0, int(skip))}
    if select:
        params["$select"] = select
    if filter_:
        params["$filter"] = filter_
    if orderby:
        params["$orderby"] = orderby
    if inlinecount:
        params["$inlinecount"] = "allpages"
    url = odata_url(entity, params)
    text, _ = request(url)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise UpstreamUnavailable(f"invalid JSON from OData service: {e}") from e
    d = payload.get("d")
    count = None
    next_url = None
    if isinstance(d, list):
        rows = d
    elif isinstance(d, dict):
        rows = d.get("results") if isinstance(d.get("results"), list) else []
        count = d.get("__count")
        next_url = d.get("__next")
    else:
        rows = []
    clean = [clean_row(r) for r in rows if isinstance(r, dict)]
    meta = {"source": "odata", "source_url": url, "returned": len(clean), "skip": max(0, int(skip)), "top": clamp_limit(top), "inline_count": count, "next_url": next_url, "row_cap": MAX_TOP}
    return clean, meta, url


def csv_rows(entity: str, *, filter_fn=None, limit: int = 10) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Fetch CSV from the same public endpoint for fallback when JSON is blocked.

    Charities Services documents `$format=csv` and `$returnall=true`; this is most
    practical for targeted Organisations search/org lookups.
    """
    params = {"$format": "csv", "$returnall": "true"}
    url = odata_url(entity, params)
    text, _ = request(url, accept="text/csv", timeout=60)
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        if filter_fn is None or filter_fn(row):
            rows.append(dict(row))
            if len(rows) >= clamp_limit(limit):
                break
    meta = {"source": "csv_fallback", "source_url": url, "returned": len(rows), "returnall": True, "row_cap": MAX_TOP}
    return rows, meta, url


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if k == "__metadata" or (isinstance(v, dict) and "__deferred" in v):
            continue
        out[k] = v
    return out


def strip_officer_private(row: dict[str, Any]) -> dict[str, Any]:
    # Anti-spam/privacy terms restrict officer email use; remove any email-like
    # fields defensively even if the current public Officers entity does not
    # expose them in the default select list.
    return {k: v for k, v in row.items() if "email" not in k.lower() and "mailaddress" not in k.lower()}


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False))


def fmt_money(v: Any) -> str:
    if v is None:
        return "-"
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_date(v: Any) -> str:
    return str(v)[:10] if v else "-"


def esc(s: str) -> str:
    return s.replace("'", "''")


def reg_variants(reg: str) -> list[str]:
    reg = reg.strip().upper()
    variants = [reg]
    if reg.startswith("CC") and reg[2:].isdigit():
        variants.append(reg[2:])
    elif reg.isdigit():
        variants.append("CC" + reg)
    return list(dict.fromkeys(variants))


def output_rows(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print_json(data)
        return
    kind = data.get("kind")
    rows = data.get("rows", [])
    count = data.get("meta", {}).get("inline_count")
    suffix = f" of {count}" if count is not None else ""
    print(f"{data.get('title', kind)}: {len(rows)} rows{suffix}")
    for r in rows:
        if kind in {"grant-intent", "search", "query", "org"} and "CharityRegistrationNumber" in r:
            print(f"- {r.get('Name') or '-'} ({r.get('CharityRegistrationNumber') or '-'})")
            bits = []
            for key, label in [("RegistrationStatus", "status"), ("PostalAddressCity", "city"), ("CharityEmailAddress", "email")]:
                if r.get(key):
                    bits.append(f"{label}: {r.get(key)}")
            if bits:
                print("  " + " | ".join(bits))
        elif kind in {"grants-paid", "grantmakers"}:
            print(f"- {r.get('Name') or '-'} ({r.get('CharityRegistrationNumber') or '-'})")
            print(f"  grants within NZ: {fmt_money(r.get('GrantsPaidWithinNZ'))} | year ended: {fmt_date(r.get('YearEnded'))} | status: {r.get('RegistrationStatus') or '-'}")
            if r.get("TotalGrossIncome") is not None or r.get("TotalExpenditure") is not None:
                print(f"  gross income: {fmt_money(r.get('TotalGrossIncome'))} | expenditure: {fmt_money(r.get('TotalExpenditure'))}")
        elif kind == "officers":
            print(f"- {r.get('FullName') or r.get('BodyCorporateName') or '-'} ({r.get('OfficerId') or '-'})")
            bits = []
            for key in ("OfficerStatus", "PositioninOrganisation", "PositionAppointmentDate", "LastDateAsAnOfficer"):
                if r.get(key):
                    bits.append(f"{key}: {r.get(key)}")
            if bits:
                print("  " + " | ".join(bits))
        else:
            print("- " + json.dumps(r, ensure_ascii=False)[:800])
    if data.get("meta", {}).get("source_url"):
        print(f"source: {data['meta']['source_url']}")


def cmd_collections(args: argparse.Namespace) -> None:
    try:
        text, _ = request(BASE, accept="application/xml")
    except (UpstreamBlocked, UpstreamUnavailable) as e:
        die(str(e))
    root = ET.fromstring(text)
    ns = {"app": "http://www.w3.org/2007/app", "atom": "http://www.w3.org/2005/Atom"}
    collections = []
    for c in root.findall(".//app:collection", ns):
        title = c.findtext("atom:title", default="", namespaces=ns)
        collections.append({"name": c.attrib.get("href"), "title": title})
    data = {"kind": "collections", "source": "Charities Services OData", "source_url": BASE, "collections": collections}
    if args.json:
        print_json(data)
    else:
        print(f"Charities Services OData collections: {len(collections)}")
        for c in collections:
            print(f"- {c['name']}")


def metadata_fields(entity: str) -> list[dict[str, str | None]]:
    try:
        text, _ = request(BASE + "$metadata", accept="application/xml")
    except (UpstreamBlocked, UpstreamUnavailable) as e:
        die(str(e))
    root = ET.fromstring(text)
    ns = {"edm": "http://schemas.microsoft.com/ado/2008/09/edm"}
    ent = root.find(f'.//edm:EntityType[@Name="{entity}"]', ns)
    if ent is None:
        die(f"entity not found in metadata: {entity}")
    fields = []
    for p in ent.findall("edm:Property", ns):
        fields.append({"name": p.attrib.get("Name"), "type": p.attrib.get("Type"), "nullable": p.attrib.get("Nullable", "true")})
    return fields


def cmd_fields(args: argparse.Namespace) -> None:
    fields = metadata_fields(args.entity)
    data = {"kind": "fields", "entity": args.entity, "source_url": BASE + "$metadata", "fields": fields}
    if args.json:
        print_json(data)
    else:
        print(f"{args.entity} fields: {len(fields)}")
        for f in fields:
            print(f"- {f['name']} ({f['type']})")


def run_odata_or_die(entity: str, **kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    try:
        return odata_get(entity, **kwargs)
    except (UpstreamBlocked, UpstreamUnavailable) as e:
        die(str(e))


def cmd_query(args: argparse.Namespace) -> None:
    rows, meta, _ = run_odata_or_die(args.entity, select=args.select, filter_=args.filter, orderby=args.orderby, top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "query", "title": f"{args.entity} query", "entity": args.entity, "filter": args.filter, "meta": meta, "rows": rows}, args.json)


def cmd_search(args: argparse.Namespace) -> None:
    q = esc(args.query)
    filter_ = f"substringof('{q}',Name) eq true"
    if args.registered_only:
        filter_ = f"({filter_}) and RegistrationStatus eq 'Registered'"
    try:
        rows, meta, _ = odata_get("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, orderby="Name", top=args.limit, skip=args.skip, inlinecount=args.count)
    except UpstreamBlocked as e:
        if args.skip or args.count or args.select:
            die(f"{e}; CSV fallback supports targeted search without --skip/--count/--select")
        needle = args.query.lower()
        try:
            rows, meta, _ = csv_rows("Organisations", filter_fn=lambda r: needle in (r.get("Name") or "").lower() and (not args.registered_only or r.get("RegistrationStatus") == "Registered"), limit=args.limit)
        except (UpstreamBlocked, UpstreamUnavailable) as csv_e:
            die(f"{e}; CSV fallback also unavailable: {csv_e}")
        meta["fallback_reason"] = str(e)
    except UpstreamUnavailable as e:
        die(str(e))
    output_rows({"kind": "search", "title": f"charity search for {args.query!r}", "query": args.query, "meta": meta, "rows": rows}, args.json)


def cmd_org(args: argparse.Namespace) -> None:
    variants = reg_variants(args.registration_number)
    wanted = set(variants)
    filter_ = " or ".join(f"CharityRegistrationNumber eq '{esc(v)}'" for v in variants)
    try:
        rows, meta, _ = odata_get("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, top=1)
    except UpstreamBlocked as e:
        if args.select:
            die(f"{e}; CSV fallback supports org lookup without --select")
        try:
            rows, meta, _ = csv_rows("Organisations", filter_fn=lambda r: (r.get("CharityRegistrationNumber") or "").upper() in wanted, limit=1)
        except (UpstreamBlocked, UpstreamUnavailable) as csv_e:
            die(f"{e}; CSV fallback also unavailable: {csv_e}")
        meta["fallback_reason"] = str(e)
    except UpstreamUnavailable as e:
        die(str(e))
    output_rows({"kind": "org", "title": f"charity {args.registration_number}", "registration_number": args.registration_number, "meta": meta, "rows": rows}, args.json)


def cmd_entity(args: argparse.Namespace) -> None:
    if args.id_type == "cc":
        class OrgArgs(argparse.Namespace):
            pass
        org_args = OrgArgs(registration_number=args.identifier, select=args.select, json=args.json)
        cmd_org(org_args)
        return
    if not args.identifier.isdigit():
        die("organisation id lookup expects a numeric OrganisationId; use search for names or --id-type cc for CC numbers")
    rows, meta, _ = run_odata_or_die("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=f"OrganisationId eq {args.identifier}", top=1, inlinecount=False)
    output_rows({"kind": "query", "title": f"charity {args.identifier}", "meta": meta, "rows": rows}, args.json)


def cmd_officers(args: argparse.Namespace) -> None:
    if not args.id.isdigit():
        die("officers <OrganisationId> expects a numeric OrganisationId")
    rows, meta, _ = run_odata_or_die("Officers", select=args.select or DEFAULT_OFFICER_SELECT, filter_=f"OrganisationId eq {args.id}", orderby=args.orderby or "FullName", top=args.limit, skip=args.skip, inlinecount=args.count)
    rows = [strip_officer_private(r) for r in rows]
    output_rows({"kind": "officers", "title": f"officers for OrganisationId {args.id}", "organisation_id": int(args.id), "privacy_note": "email-like officer fields are removed from output", "meta": meta, "rows": rows}, args.json)


def cmd_returns(args: argparse.Namespace) -> None:
    if not args.id.isdigit():
        die("returns <id> expects a numeric organisation/group id")
    entity = "GrpOrgAllReturns" if args.all else "GrpOrgLatestReturns"
    rows, meta, _ = run_odata_or_die(entity, select=args.select or DEFAULT_RETURN_SELECT, filter_=f"Id eq {args.id}", orderby=args.orderby or "YearEnded desc", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "returns", "title": f"{'all' if args.all else 'latest'} returns for id {args.id}", "id": int(args.id), "entity": entity, "meta": meta, "rows": rows}, args.json)


def cmd_activities(args: argparse.Namespace) -> None:
    rows, meta, _ = run_odata_or_die("Activities", select=args.select or "ActivityId,Name", orderby=args.orderby or "Name", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "activities", "title": "Charities Services activity taxonomy", "meta": meta, "rows": rows}, args.json)


def cmd_grant_intent(args: argparse.Namespace) -> None:
    filter_ = "PurposeToGiveGrantsAndDonations eq true"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    rows, meta, _ = run_odata_or_die("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, orderby=args.orderby or "Name", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "grant-intent", "title": "charities with PurposeToGiveGrantsAndDonations=true", "spot_query": "Organisations?$filter=PurposeToGiveGrantsAndDonations eq true", "meta": meta, "rows": rows}, args.json)


def cmd_grants_paid(args: argparse.Namespace) -> None:
    amount = max(0, args.min_amount)
    filter_ = f"GrantsPaidWithinNZ gt {amount}"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    rows, meta, _ = run_odata_or_die("GrpOrgLatestReturns", select=args.select or DEFAULT_RETURN_SELECT, filter_=filter_, orderby=args.orderby or "GrantsPaidWithinNZ desc", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "grants-paid", "title": f"latest returns with GrantsPaidWithinNZ > {amount}", "spot_query": "GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ gt 0", "meta": meta, "rows": rows}, args.json)


def cmd_grantmakers(args: argparse.Namespace) -> None:
    amount = max(0, args.min_grants)
    filter_ = f"GrantsPaidWithinNZ ge {amount}"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    rows, meta, _ = run_odata_or_die("GrpOrgLatestReturns", select=args.select or DEFAULT_GRANTMAKER_SELECT, filter_=filter_, orderby=args.orderby or "GrantsPaidWithinNZ desc", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "grantmakers", "title": f"latest returns with GrantsPaidWithinNZ >= {amount}", "spot_query": "GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ ge min_grants", "meta": meta, "rows": rows}, args.json)


def add_paging_args(s: argparse.ArgumentParser) -> None:
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--count", action="store_true", help="request $inlinecount=allpages")
    s.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Query Charities Services NZ public OData")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("collections", help="list OData collections")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_collections)

    s = sub.add_parser("fields", help="list fields for an OData entity")
    s.add_argument("entity")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_fields)

    s = sub.add_parser("query", help="generic safe OData collection query")
    s.add_argument("entity")
    s.add_argument("--filter")
    s.add_argument("--select")
    s.add_argument("--orderby")
    add_paging_args(s)
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("search", help="search Organisations by charity name")
    s.add_argument("query")
    s.add_argument("--select")
    s.add_argument("--registered-only", action="store_true")
    add_paging_args(s)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("org", help="lookup one charity by CC registration number")
    s.add_argument("registration_number")
    s.add_argument("--select")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_org)

    s = sub.add_parser("entity", help="lookup one charity by OrganisationId or CC registration number")
    s.add_argument("identifier")
    s.add_argument("--id-type", choices=["org", "cc"], default="org")
    s.add_argument("--select")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_entity)

    s = sub.add_parser("officers", help="list public officer roles for an OrganisationId (email-like fields stripped)")
    s.add_argument("id")
    s.add_argument("--select")
    s.add_argument("--orderby")
    add_paging_args(s)
    s.set_defaults(func=cmd_officers)

    s = sub.add_parser("returns", help="fetch latest/all annual-return financial rows for an organisation/group id")
    s.add_argument("id")
    s.add_argument("--all", action="store_true", help="use GrpOrgAllReturns instead of GrpOrgLatestReturns")
    s.add_argument("--select")
    s.add_argument("--orderby")
    add_paging_args(s)
    s.set_defaults(func=cmd_returns)

    s = sub.add_parser("activities", help="list public activity taxonomy values")
    s.add_argument("--select")
    s.add_argument("--orderby")
    add_paging_args(s)
    s.set_defaults(func=cmd_activities)

    s = sub.add_parser("grant-intent", help="spot query: Organisations where PurposeToGiveGrantsAndDonations is true")
    s.add_argument("--select")
    s.add_argument("--orderby")
    s.add_argument("--registered-only", action="store_true")
    add_paging_args(s)
    s.set_defaults(func=cmd_grant_intent)

    s = sub.add_parser("grants-paid", help="spot query: latest returns with GrantsPaidWithinNZ above a threshold")
    s.add_argument("--min-amount", type=int, default=0)
    s.add_argument("--select")
    s.add_argument("--orderby")
    s.add_argument("--registered-only", action="store_true")
    add_paging_args(s)
    s.set_defaults(func=cmd_grants_paid)

    s = sub.add_parser("grantmakers", help="latest returns with GrantsPaidWithinNZ at or above a threshold")
    s.add_argument("--min-grants", type=int, default=10000)
    s.add_argument("--select")
    s.add_argument("--orderby")
    s.add_argument("--registered-only", action="store_true")
    add_paging_args(s)
    s.set_defaults(func=cmd_grantmakers)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
