#!/usr/bin/env python3
"""Charities Services NZ OData CLI.

Read-only wrapper for https://www.odata.charities.govt.nz/ using Python stdlib.
Useful for registered charity lookup, grant-making intent, latest-return grant
payments, and schema discovery.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

BASE = "https://www.odata.charities.govt.nz/"
UA = "Mozilla/5.0 (compatible; thecolab-ai-skills/charities-services-nz; +https://github.com/thecolab-ai/.skills)"
DEFAULT_ORG_SELECT = "OrganisationId,Name,CharityRegistrationNumber,RegistrationStatus,NZBNNumber,CharityEmailAddress,PostalAddressCity,StreetAddressCity,MainActivityId,MainBeneficiaryId,MainSectorId,DateRegistered,ModifiedOn,PurposeToGiveGrantsAndDonations"
DEFAULT_RETURN_SELECT = "Id,EntityType,Name,CharityRegistrationNumber,RegistrationStatus,CharitySummaryURL,CharityEmailAddress,PostalAddressCity,StreetAddressCity,MainActivityName,MainBeneficiaryName,MainSectorName,YearEnded,ReportingTier,GrantsPaidWithinNZ,GrantsPaidOutsideNZ,GrantsAndDonationsMade,GrantsorDonationsPaid,TotalGrossIncome,TotalExpenditure,TotalAssets"


def die(msg: str, code: int = 1) -> None:
    print(f"charities-services-nz: {msg}", file=sys.stderr)
    raise SystemExit(code)


def request(url: str, accept: str = "application/json", timeout: int = 10) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), resp.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        die(f"HTTP {e.code} from {url}: {body}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except TimeoutError:
        die(f"timeout calling {url}")


def odata_get(entity: str, *, select: str | None = None, filter_: str | None = None,
              orderby: str | None = None, top: int = 10, skip: int = 0,
              inlinecount: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if not entity or "/" in entity or "?" in entity:
        die("entity must be an OData collection name, e.g. Organisations")
    params: dict[str, str | int] = {"$top": max(1, min(top, 1000)), "$skip": max(0, skip)}
    if select:
        params["$select"] = select
    if filter_:
        params["$filter"] = filter_
    if orderby:
        params["$orderby"] = orderby
    if inlinecount:
        params["$inlinecount"] = "allpages"
    url = BASE + entity + "?" + urllib.parse.urlencode(params)
    text, _ = request(url)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from OData service: {e}")
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
    meta = {"source_url": url, "returned": len(clean), "skip": skip, "top": top, "inline_count": count, "next_url": next_url}
    return clean, meta, url


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if k == "__metadata" or (isinstance(v, dict) and "__deferred" in v):
            continue
        out[k] = v
    return out


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
        if kind in {"grant-intent", "search", "query"} and "CharityRegistrationNumber" in r:
            print(f"- {r.get('Name') or '-'} ({r.get('CharityRegistrationNumber') or '-'})")
            bits = []
            for key, label in [("RegistrationStatus", "status"), ("PostalAddressCity", "city"), ("CharityEmailAddress", "email")]:
                if r.get(key):
                    bits.append(f"{label}: {r.get(key)}")
            if bits:
                print("  " + " | ".join(bits))
        elif kind == "grants-paid":
            print(f"- {r.get('Name') or '-'} ({r.get('CharityRegistrationNumber') or '-'})")
            print(f"  grants within NZ: {fmt_money(r.get('GrantsPaidWithinNZ'))} | year ended: {fmt_date(r.get('YearEnded'))} | status: {r.get('RegistrationStatus') or '-'}")
            if r.get("TotalGrossIncome") is not None or r.get("TotalExpenditure") is not None:
                print(f"  gross income: {fmt_money(r.get('TotalGrossIncome'))} | expenditure: {fmt_money(r.get('TotalExpenditure'))}")
        else:
            print("- " + json.dumps(r, ensure_ascii=False)[:800])
    if data.get("meta", {}).get("source_url"):
        print(f"source: {data['meta']['source_url']}")


def cmd_collections(args: argparse.Namespace) -> None:
    text, _ = request(BASE, accept="application/xml")
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
    text, _ = request(BASE + "$metadata", accept="application/xml")
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


def cmd_query(args: argparse.Namespace) -> None:
    rows, meta, _ = odata_get(args.entity, select=args.select, filter_=args.filter, orderby=args.orderby, top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "query", "title": f"{args.entity} query", "entity": args.entity, "filter": args.filter, "meta": meta, "rows": rows}, args.json)


def cmd_search(args: argparse.Namespace) -> None:
    q = args.query.replace("'", "''")
    filter_ = f"substringof('{q}',Name) eq true"
    if args.registered_only:
        filter_ = f"({filter_}) and RegistrationStatus eq 'Registered'"
    rows, meta, _ = odata_get("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, orderby="Name", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "search", "title": f"charity search for {args.query!r}", "query": args.query, "meta": meta, "rows": rows}, args.json)


def cmd_grant_intent(args: argparse.Namespace) -> None:
    filter_ = "PurposeToGiveGrantsAndDonations eq true"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    rows, meta, _ = odata_get("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, orderby=args.orderby or "Name", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "grant-intent", "title": "charities with PurposeToGiveGrantsAndDonations=true", "spot_query": "Organisations?$filter=PurposeToGiveGrantsAndDonations eq true", "meta": meta, "rows": rows}, args.json)


def cmd_grants_paid(args: argparse.Namespace) -> None:
    amount = max(0, args.min_amount)
    filter_ = f"GrantsPaidWithinNZ gt {amount}"
    if args.registered_only:
        filter_ += " and RegistrationStatus eq 'Registered'"
    rows, meta, _ = odata_get("GrpOrgLatestReturns", select=args.select or DEFAULT_RETURN_SELECT, filter_=filter_, orderby=args.orderby or "GrantsPaidWithinNZ desc", top=args.limit, skip=args.skip, inlinecount=args.count)
    output_rows({"kind": "grants-paid", "title": f"latest returns with GrantsPaidWithinNZ > {amount}", "spot_query": "GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ gt 0", "meta": meta, "rows": rows}, args.json)


def cmd_entity(args: argparse.Namespace) -> None:
    if args.id_type == "cc":
        cc = args.identifier.upper().replace("'", "''")
        filter_ = f"CharityRegistrationNumber eq '{cc}'"
    else:
        if not args.identifier.isdigit():
            die("organisation id lookup expects a numeric OrganisationId; use search for names or --id-type cc for CC numbers")
        filter_ = f"OrganisationId eq {args.identifier}"
    rows, meta, _ = odata_get("Organisations", select=args.select or DEFAULT_ORG_SELECT, filter_=filter_, top=1, inlinecount=False)
    output_rows({"kind": "query", "title": f"charity {args.identifier}", "meta": meta, "rows": rows}, args.json)


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
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--count", action="store_true", help="request $inlinecount=allpages")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("search", help="search Organisations by charity name")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--select")
    s.add_argument("--registered-only", action="store_true")
    s.add_argument("--count", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("entity", help="lookup one charity by OrganisationId or CC registration number")
    s.add_argument("identifier")
    s.add_argument("--id-type", choices=["org", "cc"], default="org")
    s.add_argument("--select")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_entity)

    s = sub.add_parser("grant-intent", help="spot query: Organisations where PurposeToGiveGrantsAndDonations is true")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--select")
    s.add_argument("--orderby")
    s.add_argument("--registered-only", action="store_true")
    s.add_argument("--count", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_grant_intent)

    s = sub.add_parser("grants-paid", help="spot query: latest returns with GrantsPaidWithinNZ above a threshold")
    s.add_argument("--min-amount", type=int, default=0)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--select")
    s.add_argument("--orderby")
    s.add_argument("--registered-only", action="store_true")
    s.add_argument("--count", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_grants_paid)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
