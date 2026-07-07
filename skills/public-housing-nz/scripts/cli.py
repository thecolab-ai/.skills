#!/usr/bin/env python3
"""Public / social housing in New Zealand — read-only stdlib CLI.

Wraps the Ministry of Housing and Urban Development (HUD) open-data releases
published on data.govt.nz (CKAN at catalogue.data.govt.nz): public housing
stock, social housing (IRRS + market rent) tenancies, accommodation supplement
recipients and spend, and the Local Housing Statistics dashboard (which
includes the year-on-year change in the public/social housing register).

No login, API key, browser automation, cache, or data mutation. Standard
library only (urllib, csv, json, argparse, re).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
import urllib.parse
from collections import defaultdict
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

CKAN_BASE = "https://catalogue.data.govt.nz"
UA = "public-housing-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

# Verified HUD resources on data.govt.nz (CKAN DataStore-backed CSVs).
RESOURCES: dict[str, dict[str, str]] = {
    "sochouse": {
        "resource_id": "37acd9dc-c7aa-467c-a899-f2d3923b1a2e",
        "url": (
            CKAN_BASE
            + "/dataset/877577c5-b059-4750-84eb-730662ae92b8/resource/"
            + "37acd9dc-c7aa-467c-a899-f2d3923b1a2e/download/sochouse_output.csv"
        ),
        "label": "Social Housing Tenancies (IRRS + Market Rent)",
    },
    "publichomes": {
        "resource_id": "169a57e5-8bf2-4799-9fd6-fd3eaceee060",
        "url": (
            CKAN_BASE
            + "/dataset/877577c5-b059-4750-84eb-730662ae92b8/resource/"
            + "169a57e5-8bf2-4799-9fd6-fd3eaceee060/download/publichomes_output.csv"
        ),
        "label": "Public Homes Stock by TLA and provider",
    },
    "as": {
        "resource_id": "66a8ec7f-8027-4f05-a46b-f2160c2784fb",
        "url": (
            CKAN_BASE
            + "/dataset/877577c5-b059-4750-84eb-730662ae92b8/resource/"
            + "66a8ec7f-8027-4f05-a46b-f2160c2784fb/download/as_output.csv"
        ),
        "label": "Accommodation Supplement recipients and weekly spend",
    },
    "local": {
        "resource_id": "30ed710c-79d9-4343-b36b-a18c2012ea0e",
        "url": (
            CKAN_BASE
            + "/dataset/7445503d-5e59-43f3-a3bd-862d2b8a1e3e/resource/"
            + "30ed710c-79d9-4343-b36b-a18c2012ea0e/download/local_housing_stats.csv"
        ),
        "label": "Local Housing Statistics dashboard",
    },
}

PROVIDER_ALIASES = {
    "ko": "KO",
    "kainga ora": "KO",
    "kaingaora": "KO",
    "chp": "CHP",
    "community housing provider": "CHP",
}


def die(message: str, code: int = 1) -> None:
    print(f"public-housing-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_json(url: str, timeout: int = 60) -> dict[str, Any]:
    try:
        return nzfetch.fetch_json(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))


def fetch_csv_rows(
    url: str,
    keep: Callable[[dict[str, str]], bool] | None = None,
    timeout: int = 120,
) -> tuple[list[dict[str, str]], str]:
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace"), newline=""))
        rows = []
        for row in reader:
            if keep is None or keep(row):
                rows.append(row)
        return rows, final_url
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")


def as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text.lower() in {"s", "n/a", "na", "..", "-", "c"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def as_int(raw: Any) -> int | None:
    value = as_float(raw)
    return None if value is None else int(round(value))


def fmt_int(value: Any) -> str:
    number = as_int(value)
    return "n/a" if number is None else f"{number:,}"


def fmt_number(value: Any) -> str:
    number = as_float(value)
    if number is None:
        return "n/a"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def norm_date(text: str) -> str:
    """Normalise a date cell to YYYY-MM-DD (CKAN returns ISO datetimes)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(text or "").strip())
    return m.group(1) if m else str(text or "").strip()


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


def latest_date(rows: list[dict[str, str]], field: str) -> str | None:
    dates = {norm_date(r.get(field, "")) for r in rows if norm_date(r.get(field, ""))}
    return max(dates) if dates else None


# ---------------------------------------------------------------------------
# datasets — discover HUD housing datasets/resources via CKAN package_search
# ---------------------------------------------------------------------------

def cmd_datasets(args: argparse.Namespace) -> None:
    query = args.query or "public housing OR social housing OR accommodation supplement"
    params = urllib.parse.urlencode({"q": query, "rows": args.limit})
    url = f"{CKAN_BASE}/api/3/action/package_search?{params}"
    data = fetch_json(url)
    if not data.get("success"):
        die(f"CKAN package_search returned success=false for {url}")
    result = data.get("result", {})
    packages = []
    for pkg in result.get("results", []):
        resources = []
        for res in pkg.get("resources", []):
            resources.append(
                {
                    "id": res.get("id"),
                    "name": res.get("name"),
                    "format": res.get("format"),
                    "last_modified": res.get("last_modified") or res.get("created"),
                    "url": res.get("url"),
                }
            )
        packages.append(
            {
                "name": pkg.get("name"),
                "title": pkg.get("title"),
                "organization": (pkg.get("organization") or {}).get("title"),
                "metadata_modified": pkg.get("metadata_modified"),
                "num_resources": pkg.get("num_resources"),
                "resources": resources,
            }
        )
    payload = {
        "source": "data.govt.nz (CKAN)",
        "query": query,
        "url": url,
        "count": result.get("count"),
        "returned": len(packages),
        "packages": packages,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HUD / NZ housing datasets matching: {p['query']}")
        print(f"Total catalogue matches: {p['count']}; showing {p['returned']}")
        for pkg in p["packages"]:
            print(f"- {pkg['title']} ({pkg['organization'] or 'unknown org'})")
            print(f"  modified: {pkg['metadata_modified']}; resources: {pkg['num_resources']}")
            for res in pkg["resources"][:6]:
                print(f"    [{res['format']}] {res['name']}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# public-homes — public housing stock (Kainga Ora + CHP) by TLA
# ---------------------------------------------------------------------------

def cmd_public_homes(args: argparse.Namespace) -> None:
    res = RESOURCES["publichomes"]
    provider = None
    if args.provider:
        provider = PROVIDER_ALIASES.get(norm(args.provider))
        if not provider:
            die("--provider must be KO (Kainga Ora) or CHP")
    area = norm(args.area) if args.area else None
    date = norm_date(args.date) if args.date else None

    def keep(row: dict[str, str]) -> bool:
        if area and area not in norm(row.get("Area_Name", "")):
            return False
        if provider and norm(row.get("Provider", "")) != norm(provider):
            return False
        if date and norm_date(row.get("As_At_Date", "")) != date:
            return False
        return True

    rows, final_url = fetch_csv_rows(res["url"], keep)
    if not date and rows:
        latest = latest_date(rows, "As_At_Date")
        rows = [r for r in rows if norm_date(r.get("As_At_Date", "")) == latest]
        date = latest
    if not rows:
        die("no public homes rows matched the supplied filters")

    records = []
    total = 0
    suppressed = 0
    for row in rows:
        value = as_int(row.get("Total Public Homes"))
        if value is None:
            suppressed += 1
        else:
            total += value
        records.append(
            {
                "tla": row.get("TLA"),
                "area_name": row.get("Area_Name"),
                "as_at_date": norm_date(row.get("As_At_Date", "")),
                "provider": row.get("Provider"),
                "total_public_homes": value,
            }
        )
    records.sort(key=lambda r: (r["area_name"] or "", r["provider"] or ""))
    payload = {
        "source": "Ministry of Housing and Urban Development (HUD)",
        "dataset": res["label"],
        "url": final_url,
        "as_at_date": date,
        "filters": {"area": args.area, "provider": provider},
        "total_public_homes": total,
        "suppressed_rows": suppressed,
        "row_count": len(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HUD public housing stock as at {p['as_at_date']}")
        flt = p["filters"]
        if flt["area"] or flt["provider"]:
            print(f"Filters: area={flt['area'] or 'all'}, provider={flt['provider'] or 'all'}")
        print(f"Total public homes: {fmt_int(p['total_public_homes'])} across {p['row_count']} rows"
              + (f" ({p['suppressed_rows']} suppressed)" if p['suppressed_rows'] else ""))
        for rec in p["records"][:25]:
            print(f"- {rec['area_name']} [{rec['provider']}]: {fmt_int(rec['total_public_homes'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# tenancies — social housing (IRRS + market rent) tenancies by TLA
# ---------------------------------------------------------------------------

def cmd_tenancies(args: argparse.Namespace) -> None:
    res = RESOURCES["sochouse"]
    area = norm(args.area) if args.area else None
    date = norm_date(args.date) if args.date else None

    def keep(row: dict[str, str]) -> bool:
        if area and area not in norm(row.get("TLA_Name", "")):
            return False
        if date and norm_date(row.get("As_At_Date", "")) != date:
            return False
        return True

    rows, final_url = fetch_csv_rows(res["url"], keep)
    if not date and rows:
        latest = latest_date(rows, "As_At_Date")
        rows = [r for r in rows if norm_date(r.get("As_At_Date", "")) == latest]
        date = latest
    if not rows:
        die("no social housing tenancy rows matched the supplied filters")

    records = []
    total = 0
    for row in rows:
        value = as_int(row.get("Total IRRS and Market Rent Tenancies"))
        if value is not None:
            total += value
        records.append(
            {
                "series": row.get("Series"),
                "tla_name": row.get("TLA_Name"),
                "as_at_date": norm_date(row.get("As_At_Date", "")),
                "total_irrs_and_market_rent_tenancies": value,
            }
        )
    records.sort(key=lambda r: r["tla_name"] or "")
    payload = {
        "source": "Ministry of Housing and Urban Development (HUD)",
        "dataset": res["label"],
        "url": final_url,
        "as_at_date": date,
        "filters": {"area": args.area},
        "total_tenancies": total,
        "row_count": len(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HUD social housing tenancies (IRRS + market rent) as at {p['as_at_date']}")
        if p["filters"]["area"]:
            print(f"Filter: area={p['filters']['area']}")
        print(f"Total tenancies: {fmt_int(p['total_tenancies'])} across {p['row_count']} TLAs")
        for rec in p["records"][:25]:
            print(f"- {rec['tla_name']}: {fmt_int(rec['total_irrs_and_market_rent_tenancies'])}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# accommodation-supplement — AS recipients and weekly spend by area
# ---------------------------------------------------------------------------

def cmd_accommodation_supplement(args: argparse.Namespace) -> None:
    res = RESOURCES["as"]
    area = norm(args.area) if args.area else None
    area_type = norm(args.area_type) if args.area_type else None
    date = norm_date(args.date) if args.date else None

    def keep(row: dict[str, str]) -> bool:
        if area and area not in norm(row.get("Area", "")):
            return False
        if area_type and norm(row.get("Area_Type", "")) != area_type:
            return False
        if date and norm_date(row.get("Date", "")) != date:
            return False
        return True

    rows, final_url = fetch_csv_rows(res["url"], keep)
    if not date and rows:
        latest = latest_date(rows, "Date")
        rows = [r for r in rows if norm_date(r.get("Date", "")) == latest]
        date = latest
    if not rows:
        die("no accommodation supplement rows matched the supplied filters")

    records = []
    total_recipients = 0.0
    total_weekly = 0.0
    for row in rows:
        recipients = as_float(row.get("AS Recipients"))
        weekly = as_float(row.get("Total Weekly AS"))
        if recipients is not None:
            total_recipients += recipients
        if weekly is not None:
            total_weekly += weekly
        records.append(
            {
                "series": row.get("Series"),
                "area": row.get("Area"),
                "area_type": row.get("Area_Type"),
                "date": norm_date(row.get("Date", "")),
                "as_recipients": recipients,
                "total_weekly_as": weekly,
            }
        )
    records.sort(key=lambda r: r["area"] or "")
    payload = {
        "source": "Ministry of Housing and Urban Development (HUD)",
        "dataset": res["label"],
        "url": final_url,
        "date": date,
        "filters": {"area": args.area, "area_type": args.area_type},
        "total_recipients": int(round(total_recipients)),
        "total_weekly_as": round(total_weekly, 2),
        "row_count": len(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HUD Accommodation Supplement as at {p['date']}")
        flt = p["filters"]
        if flt["area"] or flt["area_type"]:
            print(f"Filters: area={flt['area'] or 'all'}, area_type={flt['area_type'] or 'all'}")
        print(f"Recipients: {fmt_int(p['total_recipients'])}; total weekly AS: ${fmt_number(p['total_weekly_as'])}")
        for rec in p["records"][:25]:
            print(f"- {rec['area']} [{rec['area_type']}]: "
                  f"{fmt_int(rec['as_recipients'])} recipients, ${fmt_number(rec['total_weekly_as'])}/wk")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# local-stats — Local Housing Statistics dashboard (incl register change)
# ---------------------------------------------------------------------------

def cmd_local_stats(args: argparse.Namespace) -> None:
    res = RESOURCES["local"]
    area = norm(args.area) if args.area else None
    theme = norm(args.theme) if args.theme else None
    series = norm(args.series) if args.series else None
    year = str(args.year) if args.year else None

    def keep(row: dict[str, str]) -> bool:
        if area and area not in norm(row.get("Group_Name", "")):
            return False
        if theme and theme not in norm(row.get("theme", "")):
            return False
        if series and series not in norm(row.get("series", "")):
            return False
        if year and str(row.get("year", "")).strip() != year:
            return False
        return True

    rows, final_url = fetch_csv_rows(res["url"], keep)
    if not rows:
        die("no Local Housing Statistics rows matched the supplied filters")
    rows.sort(key=lambda r: (str(r.get("date", "")), str(r.get("series", ""))))
    if args.limit:
        rows = rows[-args.limit:]

    records = [
        {
            "group_type": row.get("Group_Type"),
            "group_name": row.get("Group_Name"),
            "date": norm_date(row.get("date", "")),
            "year": row.get("year"),
            "series": row.get("series"),
            "value": as_float(row.get("value")),
            "prefix": row.get("prefix"),
            "ethnicity": row.get("ethnicity"),
            "theme": row.get("theme"),
        }
        for row in rows
    ]
    payload = {
        "source": "Ministry of Housing and Urban Development (HUD)",
        "dataset": res["label"],
        "url": final_url,
        "filters": {"area": args.area, "theme": args.theme, "series": args.series, "year": args.year},
        "row_count": len(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"HUD Local Housing Statistics ({p['row_count']} rows)")
        flt = p["filters"]
        print(f"Filters: area={flt['area'] or 'all'}, theme={flt['theme'] or 'all'}, "
              f"series={flt['series'] or 'all'}, year={flt['year'] or 'all'}")
        for rec in p["records"][:25]:
            suffix = rec["prefix"] or ""
            eth = f" ({rec['ethnicity']})" if rec.get("ethnicity") else ""
            print(f"- {rec['date']} {rec['group_name']} | {rec['series']}{eth}: "
                  f"{fmt_number(rec['value'])}{suffix}")
        print(f"Source: {p['dataset']}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# series — list distinct series and themes available in local-stats
# ---------------------------------------------------------------------------

def cmd_series(args: argparse.Namespace) -> None:
    res = RESOURCES["local"]
    rows, final_url = fetch_csv_rows(res["url"])
    by_theme: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        theme = (row.get("theme") or "").strip() or "(none)"
        series = (row.get("series") or "").strip()
        if series:
            by_theme[theme].add(series)
    themes = {theme: sorted(items) for theme, items in sorted(by_theme.items())}
    all_series = sorted({s for items in by_theme.values() for s in items})
    payload = {
        "source": "Ministry of Housing and Urban Development (HUD)",
        "dataset": res["label"],
        "url": final_url,
        "theme_count": len(themes),
        "series_count": len(all_series),
        "themes": themes,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Local Housing Statistics: {p['series_count']} series across {p['theme_count']} themes")
        for theme, items in p["themes"].items():
            print(f"[{theme}]")
            for series in items:
                print(f"  - {series}")
        print(p["url"])

    output(payload, args.json, render)


# ---------------------------------------------------------------------------
# query — passthrough to CKAN datastore_search for server-side filtering
# ---------------------------------------------------------------------------

def cmd_query(args: argparse.Namespace) -> None:
    res = RESOURCES.get(args.resource)
    if not res:
        die(f"--resource must be one of: {', '.join(RESOURCES)}")
    params: dict[str, Any] = {"resource_id": res["resource_id"], "limit": args.limit}
    if args.q:
        params["q"] = args.q
    filters: dict[str, str] = {}
    for item in args.filter or []:
        if "=" not in item:
            die(f"--filter expects k=v, got: {item}")
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    if filters:
        params["filters"] = json.dumps(filters)
    url = f"{CKAN_BASE}/api/3/action/datastore_search?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    if not data.get("success"):
        die(f"CKAN datastore_search returned success=false for {url}")
    result = data.get("result", {})
    records = result.get("records", [])
    for rec in records:
        rec.pop("_full_text", None)
    payload = {
        "source": "data.govt.nz (CKAN DataStore)",
        "dataset": res["label"],
        "resource": args.resource,
        "url": url,
        "total": result.get("total"),
        "returned": len(records),
        "filters": filters,
        "q": args.q,
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"CKAN datastore_search on {p['dataset']} ({p['resource']})")
        print(f"Total matching: {p['total']}; returned: {p['returned']}")
        for rec in p["records"][:25]:
            cells = {k: v for k, v in rec.items() if k != "_id"}
            print(f"- {cells}")
        print(p["url"])

    output(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for NZ public/social housing open data (HUD via data.govt.nz)."
    )
    sub = parser.add_subparsers(dest="command")

    datasets = sub.add_parser("datasets", help="List HUD housing datasets/resources via CKAN package_search")
    datasets.add_argument("--query", help="CKAN search query (default: public/social housing terms)")
    datasets.add_argument("--limit", type=int, default=10, help="Maximum packages to return")
    datasets.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    datasets.set_defaults(func=cmd_datasets)

    ph = sub.add_parser("public-homes", help="Public housing stock (Kainga Ora + CHP) by TLA")
    ph.add_argument("--area", help="Filter by Area_Name (substring, e.g. Whangarei District)")
    ph.add_argument("--provider", help="Filter by provider: KO (Kainga Ora) or CHP")
    ph.add_argument("--date", help="As-at date YYYY-MM-DD (default: latest available)")
    ph.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ph.set_defaults(func=cmd_public_homes)

    ten = sub.add_parser("tenancies", help="Social housing (IRRS + market rent) tenancies by TLA")
    ten.add_argument("--area", help="Filter by TLA_Name (substring, e.g. Invercargill City)")
    ten.add_argument("--date", help="As-at date YYYY-MM-DD (default: latest available)")
    ten.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ten.set_defaults(func=cmd_tenancies)

    acc = sub.add_parser("accommodation-supplement", help="Accommodation Supplement recipients and weekly spend")
    acc.add_argument("--area", help="Filter by Area (substring, e.g. Ashburton District)")
    acc.add_argument("--area-type", dest="area_type", help="Filter by Area_Type (e.g. TLA)")
    acc.add_argument("--date", help="Date YYYY-MM-DD (default: latest available)")
    acc.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    acc.set_defaults(func=cmd_accommodation_supplement)

    local = sub.add_parser("local-stats", help="Local Housing Statistics dashboard (incl register change)")
    local.add_argument("--area", help="Filter by Group_Name (substring, e.g. New Zealand)")
    local.add_argument("--theme", help="Filter by theme (substring, e.g. MSD, Affordability)")
    local.add_argument("--series", help="Filter by series (substring, e.g. Change in Housing Register)")
    local.add_argument("--year", type=int, help="Filter by year (e.g. 2024)")
    local.add_argument("--limit", type=int, default=50, help="Maximum rows from the end of the range")
    local.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    local.set_defaults(func=cmd_local_stats)

    series = sub.add_parser("series", help="List distinct series and themes in the Local Housing Statistics dashboard")
    series.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    series.set_defaults(func=cmd_series)

    query = sub.add_parser("query", help="Passthrough to CKAN datastore_search for server-side filtering")
    query.add_argument("--resource", required=True, help="One of: sochouse, publichomes, as, local")
    query.add_argument("--filter", action="append", help="Server-side filter k=v (repeatable)")
    query.add_argument("--q", help="Full-text query string")
    query.add_argument("--limit", type=int, default=20, help="Maximum records to return")
    query.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    query.set_defaults(func=cmd_query)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    if hasattr(args, "limit") and args.limit is not None and args.limit < 1:
        die("--limit must be at least 1")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
