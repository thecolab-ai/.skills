#!/usr/bin/env python3
"""Charities Register NZ public OData CLI (stdlib only)."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NoReturn

BASE = "https://www.odata.charities.govt.nz/"
UA = "Mozilla/5.0 (compatible; thecolab-ai-skills/charities-register-nz; +https://github.com/thecolab-ai/.skills)"
MAX_TOP = 1000
DEFAULT_LIMIT = 25
ORG_SELECT = "OrganisationId,Name,CharityRegistrationNumber,RegistrationStatus,NZBNNumber,CompaniesOfficeNumber,WebSiteURL,CharityEmailAddress,PostalAddressCity,StreetAddressCity,MainActivityId,MainBeneficiaryId,MainSectorId,DateRegistered,DeregistrationDate,AnnualReturnDueDate,ModifiedOn,PurposeToGiveGrantsAndDonations"
OFFICER_SELECT = "OfficerId,OrganisationId,FullName,FirstName,MiddleName,LastName,OfficerStatus,PositioninOrganisation,PositionAppointmentDate,LastDateAsAnOfficer,BodyCorporateName,IsaBodyCorporate,ModifiedOn"
RETURN_SELECT = "Id,EntityType,Name,CharityRegistrationNumber,RegistrationStatus,CharitySummaryURL,MainActivityName,MainBeneficiaryName,MainSectorName,Activities,AnnualReturnId,ReportingTier,YearEnded,FinancialPositionDate,GrantsPaidWithinNZ,GrantsPaidOutsideNZ,GrantsAndDonationsMade,GrantsorDonationsPaid,TotalGrossIncome,TotalExpenditure,TotalAssets,TotalLiabilities,TotalEquity,NetSurplusDeficitForTheYear,DonationsKoha,GovtGrantsContracts,GeneralGrantsReceived,ServiceDeliveryGrantsContracts,ModifiedOn"
GRANTMAKER_SELECT = "Id,EntityType,Name,CharityRegistrationNumber,RegistrationStatus,CharitySummaryURL,MainActivityName,MainSectorName,YearEnded,GrantsPaidWithinNZ,GrantsPaidOutsideNZ,GrantsAndDonationsMade,GrantsorDonationsPaid,TotalGrossIncome,TotalExpenditure,TotalAssets"


class UpstreamBlocked(Exception):
    pass


class UpstreamUnavailable(Exception):
    pass


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"charities-register-nz: {msg}", file=sys.stderr)
    raise SystemExit(code)


def clamp_limit(n: int) -> int:
    return max(1, min(int(n), MAX_TOP))


def strip_odata(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key == "__metadata" or (isinstance(value, dict) and "__deferred" in value):
            continue
        out[key] = value
    return out


def strip_officer_private(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if "email" not in k.lower() and "mailaddress" not in k.lower()}


def request_text(url: str, accept: str = "application/json", timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if e.code == 403 or "incapsula" in body.lower() or "blocked" in body.lower():
            raise UpstreamBlocked(f"blocked_by_upstream: HTTP {e.code} from {url}") from e
        raise UpstreamUnavailable(f"HTTP {e.code} from {url}: {body}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise UpstreamUnavailable(f"network error calling {url}: {e}") from e


def odata_url(entity: str, params: dict[str, Any]) -> str:
    if not entity or any(ch in entity for ch in "/?&"):
        die("invalid OData collection name")
    return BASE + entity + "?" + urllib.parse.urlencode(params)


def odata_get(entity: str, *, select: str | None = None, filter_: str | None = None,
              orderby: str | None = None, top: int = DEFAULT_LIMIT, skip: int = 0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params: dict[str, Any] = {"$top": clamp_limit(top), "$skip": max(0, int(skip))}
    if select:
        params["$select"] = select
    if filter_:
        params["$filter"] = filter_
    if orderby:
        params["$orderby"] = orderby
    url = odata_url(entity, params)
    text = request_text(url)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise UpstreamUnavailable(f"invalid JSON from OData service: {e}") from e
    d = payload.get("d")
    if isinstance(d, list):
        rows = d
        next_url = None
    elif isinstance(d, dict):
        results = d.get("results")
        rows = results if isinstance(results, list) else []
        next_url = d.get("__next")
    else:
        rows = []
        next_url = None
    clean = [strip_odata(r) for r in rows if isinstance(r, dict)]
    return clean, {"source": "odata", "source_url": url, "returned": len(clean), "top": params["$top"], "skip": params["$skip"], "next_url": next_url, "row_cap": MAX_TOP}


def csv_rows(entity: str, *, filter_fn=None, limit: int = DEFAULT_LIMIT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # data.govt.nz lists this public CSV mirror form for Organisations.
    params = {"$format": "csv", "$returnall": "true"}
    url = BASE + entity + "?" + urllib.parse.urlencode(params)
    text = request_text(url, accept="text/csv", timeout=60)
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        if filter_fn is None or filter_fn(row):
            rows.append(dict(row))
            if len(rows) >= clamp_limit(limit):
                break
    return rows, {"source": "csv_mirror", "source_url": url, "returned": len(rows), "returnall": True, "row_cap": MAX_TOP}


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


def output(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    rows = data.get("rows", [])
    print(f"{data.get('title', data.get('kind', 'result'))}: {len(rows)} row(s)")
    for row in rows:
        name = row.get("Name") or row.get("FullName") or row.get("name") or row.get("ActivityId") or row.get("AnnualReturnId") or "-"
        ident = row.get("CharityRegistrationNumber") or row.get("OrganisationId") or row.get("OfficerId") or row.get("Id") or ""
        print(f"- {name}" + (f" ({ident})" if ident else ""))
        bits = []
        for key in ["RegistrationStatus", "OfficerStatus", "PositioninOrganisation", "YearEnded", "GrantsPaidWithinNZ", "TotalGrossIncome", "CharitySummaryURL"]:
            if row.get(key) not in (None, ""):
                bits.append(f"{key}={row.get(key)}")
        if bits:
            print("  " + " | ".join(bits))
    meta = data.get("meta", {})
    if meta.get("source_url"):
        print(f"source: {meta['source_url']}")


def cmd_search(args: argparse.Namespace) -> None:
    query = args.name.strip()
    filter_ = f"substringof('{esc(query)}',Name) eq true"
    try:
        rows, meta = odata_get("Organisations", select=ORG_SELECT, filter_=filter_, orderby="Name", top=args.limit, skip=args.skip)
    except UpstreamBlocked as e:
        q = query.lower()
        rows, meta = csv_rows("Organisations", filter_fn=lambda r: q in (r.get("Name") or "").lower(), limit=args.limit)
        meta["fallback_reason"] = str(e)
    except UpstreamUnavailable as e:
        die(str(e))
    output({"kind": "search", "title": f"charity search for {query!r}", "query": query, "meta": meta, "rows": rows}, args.json)


def cmd_org(args: argparse.Namespace) -> None:
    variants = reg_variants(args.registration_number)
    filters = [f"CharityRegistrationNumber eq '{esc(v)}'" for v in variants]
    filter_ = " or ".join(filters)
    try:
        rows, meta = odata_get("Organisations", select=ORG_SELECT, filter_=filter_, top=1)
    except UpstreamBlocked as e:
        wanted = set(variants)
        rows, meta = csv_rows("Organisations", filter_fn=lambda r: (r.get("CharityRegistrationNumber") or "").upper() in wanted, limit=1)
        meta["fallback_reason"] = str(e)
    except UpstreamUnavailable as e:
        die(str(e))
    output({"kind": "org", "title": f"charity {args.registration_number}", "registration_number": args.registration_number, "meta": meta, "rows": rows}, args.json)


def cmd_officers(args: argparse.Namespace) -> None:
    if not args.id.isdigit():
        die("officers <id> expects a numeric OrganisationId")
    try:
        rows, meta = odata_get("Officers", select=OFFICER_SELECT, filter_=f"OrganisationId eq {args.id}", orderby="FullName", top=args.limit, skip=args.skip)
    except UpstreamBlocked as e:
        die(str(e))
    except UpstreamUnavailable as e:
        die(str(e))
    rows = [strip_officer_private(r) for r in rows]
    output({"kind": "officers", "title": f"officers for OrganisationId {args.id}", "organisation_id": int(args.id), "privacy_note": "email-like officer fields are removed", "meta": meta, "rows": rows}, args.json)


def cmd_returns(args: argparse.Namespace) -> None:
    if not args.id.isdigit():
        die("returns <id> expects a numeric organisation/group id")
    entity = "GrpOrgAllReturns" if args.all else "GrpOrgLatestReturns"
    try:
        rows, meta = odata_get(entity, select=RETURN_SELECT, filter_=f"Id eq {args.id}", orderby="YearEnded desc", top=args.limit, skip=args.skip)
    except UpstreamBlocked as e:
        die(str(e))
    except UpstreamUnavailable as e:
        die(str(e))
    output({"kind": "returns", "title": f"{'all' if args.all else 'latest'} returns for id {args.id}", "id": int(args.id), "entity": entity, "meta": meta, "rows": rows}, args.json)


def cmd_grantmakers(args: argparse.Namespace) -> None:
    minimum = max(0, int(args.min_grants))
    filter_ = f"GrantsPaidWithinNZ ge {minimum}"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    try:
        rows, meta = odata_get("GrpOrgLatestReturns", select=GRANTMAKER_SELECT, filter_=filter_, orderby="GrantsPaidWithinNZ desc", top=args.limit, skip=args.skip)
    except UpstreamBlocked as e:
        die(str(e))
    except UpstreamUnavailable as e:
        die(str(e))
    output({"kind": "grantmakers", "title": f"grantmakers with GrantsPaidWithinNZ >= {minimum}", "min_grants": minimum, "meta": meta, "rows": rows}, args.json)


def cmd_activities(args: argparse.Namespace) -> None:
    try:
        rows, meta = odata_get("Activities", select="ActivityId,Name", orderby="Name", top=args.limit, skip=args.skip)
    except UpstreamBlocked as e:
        die(str(e))
    except UpstreamUnavailable as e:
        die(str(e))
    output({"kind": "activities", "title": "Charities Register activities", "meta": meta, "rows": rows}, args.json)


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"max rows to return (1-{MAX_TOP}; default: {DEFAULT_LIMIT})")
    p.add_argument("--skip", type=int, default=0, help="OData $skip offset")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query the NZ Charities Services Register public OData API")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search Organisations by charity name")
    p.add_argument("name")
    add_common(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("org", help="lookup an organisation by CC registration number")
    p.add_argument("registration_number")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_org)

    p = sub.add_parser("officers", help="list public officers for an OrganisationId")
    p.add_argument("id")
    add_common(p)
    p.set_defaults(func=cmd_officers)

    p = sub.add_parser("returns", help="fetch latest/all annual-return financial rows for an organisation/group id")
    p.add_argument("id")
    p.add_argument("--all", action="store_true", help="use GrpOrgAllReturns instead of GrpOrgLatestReturns")
    add_common(p)
    p.set_defaults(func=cmd_returns)

    p = sub.add_parser("grantmakers", help="latest returns with GrantsPaidWithinNZ at or above a threshold")
    p.add_argument("--min-grants", type=int, default=10000)
    p.add_argument("--registered-only", action="store_true")
    add_common(p)
    p.set_defaults(func=cmd_grantmakers)

    p = sub.add_parser("activities", help="list public activity taxonomy values")
    add_common(p)
    p.set_defaults(func=cmd_activities)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
