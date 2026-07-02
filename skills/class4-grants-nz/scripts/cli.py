#!/usr/bin/env python3
"""Read-only CLI for NZ Class 4 gambling grants data.

Uses the Department of Internal Affairs / Granted.govt.nz public datasets
published on catalogue.data.govt.nz. Standard library only; no auth, no cache,
no browser automation, and no mutation.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Callable, Iterable

CKAN_BASE = "https://catalogue.data.govt.nz"
CKAN_ACTION = CKAN_BASE + "/api/3/action/"
GRANTS_DATASET = "class-4-grants-data"
VENUES_DATASET = "class-4-gambling-venue-and-gaming-machine-numbers-quarterly-lists"
GRANTS_RESOURCE_ID = "06d99ad0-47d6-4591-84c7-8872a4f77da9"
GRANTS_CSV_URL = (
    CKAN_BASE
    + "/dataset/b6b7f1cc-bfa4-4c7a-81e8-8a03f2983cae/resource/"
    + GRANTS_RESOURCE_ID
    + "/download/class-4-grants-dataset-csv.csv"
)
GRANTED_URL = "https://www.granted.govt.nz/"
DIA_GRANTS_URL = "https://www.dia.govt.nz/Gambling-statistics-class-4-grants-data"
DIA_SOCIETIES_URL = "https://www.dia.govt.nz/Services-Casino-and-Non-Casino-Gaming-List-of-Society-Websites"
UA = "class4-grants-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

MONEY_FIELDS = {"Amount_Requested_Final", "Amount_Granted_Final", "Amount_Refunded_Clean"}
FIELD_ALIASES = {
    "society": "Society_Name",
    "funder": "Society_Name",
    "organisation": "Final_Organisation_Name",
    "organization": "Final_Organisation_Name",
    "recipient": "Final_Organisation_Name",
    "status": "Status",
    "year": "Year_of_Accept/Decline",
    "category1": "Category_1",
    "category2": "Category_2",
    "tla": "Territorial_Local_Authority",
    "region": "Region",
}


def die(message: str, code: int = 1) -> None:
    print(f"class4-grants-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    try:
        with request(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def fetch_text(url: str, timeout: int = 30) -> str:
    try:
        with request(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def ckan(action: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = CKAN_ACTION + action + ("?" + query if query else "")
    data = fetch_json(url)
    if not data.get("success"):
        die(f"CKAN {action} returned success=false: {data.get('error')}")
    return {"source_url": url, "result": data.get("result", {})}


def emit(payload: dict[str, Any], json_flag: bool, renderer: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        renderer(payload)


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def money(value: Any) -> float:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text or text.lower() in {"n/a", "na", "-", ".."}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def clean_row(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)
    for field in MONEY_FIELDS:
        out[field + "_Number"] = money(row.get(field))
    return out


def csv_rows(timeout: int = 90) -> Iterable[dict[str, str]]:
    try:
        with request(GRANTS_CSV_URL, timeout=timeout) as resp:
            text = io.TextIOWrapper(resp, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.DictReader(text)
            for row in reader:
                yield row
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} downloading grants CSV: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error downloading grants CSV: {e.reason}")
    except csv.Error as e:
        die(f"invalid grants CSV: {e}")


def matches(row: dict[str, str], args: argparse.Namespace) -> bool:
    if args.year and str(row.get("Year_of_Accept/Decline", "")) != str(args.year):
        return False
    if args.status and norm(row.get("Status")) != norm(args.status):
        return False
    if args.society and norm(args.society) not in norm(row.get("Society_Name")):
        return False
    if args.recipient and norm(args.recipient) not in norm(row.get("Final_Organisation_Name") or row.get("Organisation_Name")):
        return False
    if args.category and norm(args.category) not in (norm(row.get("Category_1")) + " " + norm(row.get("Category_2"))):
        return False
    if args.region and norm(args.region) not in norm(row.get("Region")):
        return False
    if args.tla and norm(args.tla) not in norm(row.get("Territorial_Local_Authority")):
        return False
    if args.query:
        haystack = " ".join(str(v) for v in row.values())
        if norm(args.query) not in norm(haystack):
            return False
    return True


def dataset_summary(pkg: dict[str, Any]) -> dict[str, Any]:
    org = pkg.get("organization") or {}
    return {
        "name": pkg.get("name"),
        "title": pkg.get("title"),
        "organisation": org.get("title") or org.get("name") if isinstance(org, dict) else None,
        "notes": pkg.get("notes"),
        "metadata_modified": pkg.get("metadata_modified"),
        "url": f"{CKAN_BASE}/dataset/{pkg.get('name')}",
        "resources": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "url": r.get("url"),
                "last_modified": r.get("last_modified") or r.get("created"),
                "datastore_active": r.get("datastore_active"),
            }
            for r in pkg.get("resources", [])
        ],
    }


def cmd_datasets(args: argparse.Namespace) -> None:
    ids = [GRANTS_DATASET, VENUES_DATASET]
    packages = []
    source_urls = []
    for package_id in ids:
        data = ckan("package_show", {"id": package_id})
        source_urls.append(data["source_url"])
        packages.append(dataset_summary(data["result"]))
    payload = {
        "kind": "datasets",
        "source": "data.govt.nz CKAN / DIA / Granted.govt.nz",
        "source_urls": source_urls,
        "granted_url": GRANTED_URL,
        "dia_grants_url": DIA_GRANTS_URL,
        "datasets": packages,
    }
    emit(payload, args.json, render_datasets)


def render_datasets(payload: dict[str, Any]) -> None:
    print("Class 4 grants / Granted.govt.nz public datasets")
    print(f"Granted portal: {payload['granted_url']}")
    for ds in payload["datasets"]:
        print(f"\n- {ds['title']} ({ds['name']})")
        print(f"  organisation: {ds.get('organisation') or '-'} | modified: {(ds.get('metadata_modified') or '')[:10]}")
        print(f"  url: {ds['url']}")
        for r in ds["resources"][:6]:
            print(f"  * {r.get('name') or r.get('id')} [{r.get('format') or '-'}] {r.get('url')}")


def cmd_preview(args: argparse.Namespace) -> None:
    rows = []
    for row in csv_rows():
        rows.append(clean_row(row))
        if len(rows) >= args.limit:
            break
    payload = {"kind": "preview", "source_url": GRANTS_CSV_URL, "count": len(rows), "records": rows}
    emit(payload, args.json, render_records)


def cmd_grants(args: argparse.Namespace) -> None:
    records = []
    scanned = 0
    matched = 0
    total_granted = 0.0
    total_requested = 0.0
    for row in csv_rows():
        scanned += 1
        if not matches(row, args):
            continue
        matched += 1
        total_granted += money(row.get("Amount_Granted_Final"))
        total_requested += money(row.get("Amount_Requested_Final"))
        if len(records) < args.limit:
            records.append(clean_row(row))
    payload = {
        "kind": "grants",
        "source_url": GRANTS_CSV_URL,
        "filters": filter_payload(args),
        "scanned": scanned,
        "matched": matched,
        "returned": len(records),
        "total_requested": round(total_requested, 2),
        "total_granted": round(total_granted, 2),
        "records": records,
    }
    emit(payload, args.json, render_records)


def filter_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {k: getattr(args, k, None) for k in ["query", "year", "status", "society", "recipient", "category", "region", "tla"] if getattr(args, k, None)}


def render_records(payload: dict[str, Any]) -> None:
    if payload["kind"] == "grants":
        print(
            f"Class 4 grants: {payload['matched']:,} matched from {payload['scanned']:,} rows; "
            f"granted {fmt_money(payload['total_granted'])}"
        )
    else:
        print(f"Class 4 grants preview: {payload['count']} rows")
    for row in payload.get("records", []):
        print(
            "- "
            + f"{row.get('Year_of_Accept/Decline')} | {row.get('Status')} | {row.get('Society_Name')} -> "
            + f"{row.get('Final_Organisation_Name') or row.get('Organisation_Name')} | "
            + f"granted {row.get('Amount_Granted_Final')} | {row.get('Category_1')} / {row.get('Category_2')} | "
            + f"{row.get('Territorial_Local_Authority')}, {row.get('Region')}"
        )


def cmd_funders(args: argparse.Namespace) -> None:
    aggregate(args, key_field="Society_Name", kind="funders")


def cmd_recipients(args: argparse.Namespace) -> None:
    aggregate(args, key_field="Final_Organisation_Name", kind="recipients")


def cmd_categories(args: argparse.Namespace) -> None:
    aggregate(args, key_field=args.field, kind="categories")


def aggregate(args: argparse.Namespace, key_field: str, kind: str) -> None:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"applications": 0, "accepted": 0, "declined": 0, "requested": 0.0, "granted": 0.0, "refunded": 0.0})
    scanned = 0
    for row in csv_rows():
        scanned += 1
        if not matches(row, args):
            continue
        key = (row.get(key_field) or "Unknown").strip() or "Unknown"
        bucket = buckets[key]
        bucket["applications"] += 1
        status = norm(row.get("Status"))
        if status == "accepted":
            bucket["accepted"] += 1
        elif status == "declined":
            bucket["declined"] += 1
        bucket["requested"] += money(row.get("Amount_Requested_Final"))
        bucket["granted"] += money(row.get("Amount_Granted_Final"))
        bucket["refunded"] += money(row.get("Amount_Refunded_Clean"))
    rows = []
    for name, b in buckets.items():
        rows.append({"name": name, **{k: round(v, 2) if isinstance(v, float) else v for k, v in b.items()}})
    sort_key = args.sort
    rows.sort(key=lambda r: (r.get(sort_key) or 0, r.get("name") or ""), reverse=sort_key != "name")
    rows = rows[: args.limit]
    payload = {"kind": kind, "source_url": GRANTS_CSV_URL, "group_by": key_field, "filters": filter_payload(args), "scanned": scanned, "count": len(rows), "records": rows}
    emit(payload, args.json, render_aggregate)


def render_aggregate(payload: dict[str, Any]) -> None:
    print(f"Class 4 grant {payload['kind']} grouped by {payload['group_by']} ({payload['count']} shown)")
    for row in payload["records"]:
        print(
            f"- {row['name']}: {row['applications']:,} applications, {row['accepted']:,} accepted, "
            f"granted {fmt_money(float(row['granted']))}, requested {fmt_money(float(row['requested']))}"
        )


def cmd_society_websites(args: argparse.Namespace) -> None:
    html = fetch_text(DIA_SOCIETIES_URL)
    links = []
    for href, label in re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
        text = re.sub(r"<[^>]+>", " ", label)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or not href:
            continue
        if "societ" in text.lower() or "trust" in text.lower() or "foundation" in text.lower() or "gaming" in text.lower() or "charity" in text.lower():
            links.append({"name": text, "url": urllib.parse.urljoin(DIA_SOCIETIES_URL, href)})
    # De-duplicate while preserving order.
    seen = set()
    unique = []
    for item in links:
        key = (item["name"].lower(), item["url"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    payload = {"kind": "society-websites", "source_url": DIA_SOCIETIES_URL, "count": len(unique[: args.limit]), "records": unique[: args.limit]}
    emit(payload, args.json, render_society_websites)


def render_society_websites(payload: dict[str, Any]) -> None:
    print(f"DIA society website links ({payload['count']} shown)")
    for item in payload["records"]:
        print(f"- {item['name']}: {item['url']}")


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", help="case-insensitive text search across grant row fields")
    parser.add_argument("--year", type=int, help="accept/decline year, e.g. 2024")
    parser.add_argument("--status", choices=["Accepted", "Declined"], help="grant application status")
    parser.add_argument("--society", help="society/funder name contains")
    parser.add_argument("--recipient", help="recipient/final organisation name contains")
    parser.add_argument("--category", help="category 1 or 2 contains")
    parser.add_argument("--region", help="region contains")
    parser.add_argument("--tla", help="territorial local authority contains")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query NZ Class 4 grants / Granted.govt.nz public data")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("datasets", help="show grants and gaming-machine datasets from data.govt.nz")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_datasets)

    p = sub.add_parser("preview", help="download and show the first rows of the Class 4 grants CSV")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("grants", help="filter grant application rows")
    add_filter_args(p)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_grants)

    for name, help_text, func in [
        ("funders", "aggregate grants by society/funder", cmd_funders),
        ("recipients", "aggregate grants by recipient organisation", cmd_recipients),
    ]:
        p = sub.add_parser(name, help=help_text)
        add_filter_args(p)
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--sort", choices=["name", "applications", "accepted", "declined", "requested", "granted", "refunded"], default="granted")
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=func)

    p = sub.add_parser("categories", help="aggregate grants by Category_1 or Category_2")
    add_filter_args(p)
    p.add_argument("--field", choices=["Category_1", "Category_2"], default="Category_1")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", choices=["name", "applications", "accepted", "declined", "requested", "granted", "refunded"], default="granted")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_categories)

    p = sub.add_parser("society-websites", help="extract DIA list of Class 4 society website links")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_society_websites)

    args = parser.parse_args()
    if hasattr(args, "limit") and args.limit < 1:
        die("--limit must be >= 1")
    args.func(args)


if __name__ == "__main__":
    main()
