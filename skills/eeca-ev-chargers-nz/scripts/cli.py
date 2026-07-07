#!/usr/bin/env python3
"""EECA public EV charger dashboard CLI.

Read-only, keyless access to the official EECA public EV charger CSV exports
and the data.govt.nz CKAN package metadata. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any, Callable

UA = "eeca-ev-chargers-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
CKAN_PACKAGE_URL = "https://catalogue.data.govt.nz/api/3/action/package_show?id=public-ev-chargers"
DATASET_PAGE = "https://catalogue.data.govt.nz/dataset/public-ev-chargers"
EECA_DASHBOARD = "https://www.eeca.govt.nz/insights/data-tools/public-ev-charger-dashboard/"

RESOURCES: dict[str, dict[str, str]] = {
    "chargers": {
        "label": "Public EV chargers",
        "url": "https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/Public-EV-chargers.csv",
    },
    "cofunded": {
        "label": "Co-funded EV chargers",
        "url": "https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/Co-funded-EV-chargers.csv",
    },
    "metrics-region": {
        "label": "EV metrics by region",
        "url": "https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/EV-metrics-by-region.csv",
    },
    "metrics-district": {
        "label": "EV metrics by district",
        "url": "https://www.eeca.govt.nz/assets/EECA-Resources/Public-EV-Charger-Dashboard/EV-metrics-by-district.csv",
    },
}


def die(message: str, code: int = 1) -> None:
    print(f"eeca-ev-chargers-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def _looks_like_bot_challenge(body: str, content_type: str) -> bool:
    """A public NZ source behind Incapsula/Cloudflare answers a JSON API request
    with an HTML interstitial (often HTTP 200). That is a transient *block*, not
    a dead source or malformed JSON — detect it so callers classify it as such."""
    if "text/html" in content_type:
        return True
    head = body.lstrip()[:512].lower()
    return (
        head.startswith("<")
        or "<!doctype html" in head
        or "incapsula" in body.lower()
        or "_incapsula_resource" in body.lower()
        or "request unsuccessful" in head
    )


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    try:
        with request(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            content_type = (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        # 403/429 (with or without an HTML challenge body) mean the public
        # source is bot-blocking this network — a transient block, so report it
        # as a network error (callers/smoke tests skip rather than hard-fail).
        if e.code in (403, 429):
            die(f"network error: HTTP {e.code} from {url} — the public source is bot-blocking this network (blocked). {raw[:200]}")
        die(f"HTTP {e.code} from {url}: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if _looks_like_bot_challenge(raw, content_type):
            die(f"network error: {url} returned a non-JSON bot-challenge response (blocked — likely an Incapsula/Cloudflare interstitial, not a dead source).")
        die(f"invalid JSON from {url}: {e}")


def fetch_csv_rows(resource: str, timeout: int = 30) -> tuple[list[dict[str, str]], str]:
    url = RESOURCES[resource]["url"]
    try:
        with request(url, timeout=timeout) as resp:
            final_url = resp.geturl()
            text = io.TextIOWrapper(resp, encoding="utf-8-sig", newline="")
            return list(csv.DictReader(text)), final_url
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def as_float(raw: Any) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    if not text or text.lower() in {"n/a", "na", "null", "none", "-", ".."}:
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


def fmt_float(value: Any, digits: int = 2) -> str:
    number = as_float(value)
    if number is None:
        return "n/a"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{digits}f}"


def compact_date(value: str) -> str:
    return str(value or "").strip().split(" ")[0]


def parse_connectors(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def emit(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        render(payload)


def match_contains(value: str, query: str | None) -> bool:
    return True if not query else norm(query) in norm(value)


def point_count(rows: list[dict[str, Any]]) -> int:
    return sum(as_int(row.get("points")) or 0 for row in rows)


def kw_total(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        kw = as_float(row.get("kw_rated"))
        points = as_int(row.get("points")) or 1
        if kw is not None:
            total += kw * points
    return total


def normalise_charger(row: dict[str, str]) -> dict[str, Any]:
    return {
        "unit_id": row.get("UnitId"),
        "points": as_int(row.get("Points")),
        "site_id": row.get("SiteId"),
        "owner": row.get("Owner"),
        "operator": row.get("Operator"),
        "date_first_operational": row.get("DateFirstOperational"),
        "current": row.get("Current"),
        "kw_rated": as_float(row.get("KwRated")),
        "address": row.get("Address"),
        "latitude": as_float(row.get("Latitude")),
        "longitude": as_float(row.get("Longitude")),
        "locality": row.get("Locality"),
        "region": row.get("Region"),
        "district": row.get("District"),
        "connectors": parse_connectors(row.get("Connectors", "")),
    }


def normalise_cofunded(row: dict[str, str]) -> dict[str, Any]:
    return {
        "application_id": row.get("ApplicationId"),
        "points": as_int(row.get("Points")),
        "applicant": row.get("Applicant"),
        "status": row.get("Status"),
        "go_live_date": compact_date(row.get("GoLiveDate", "")),
        "kw_rated": as_float(row.get("KwRated")),
        "address": row.get("Address"),
        "locality": row.get("Locality"),
        "region": row.get("Region"),
        "district": row.get("District"),
        "latitude": as_float(row.get("Latitude")),
        "longitude": as_float(row.get("Longitude")),
    }


def normalise_metric(row: dict[str, str], level: str) -> dict[str, Any]:
    result = {
        "level": level,
        "name": row.get("Region") if level == "region" else row.get("District"),
        "region": row.get("Region"),
        "charge_points": as_int(row.get("Charge Points")),
        "units": as_int(row.get("Units")),
        "sites": as_int(row.get("Sites")),
        "battery_electric_vehicles": as_int(row.get("Battery Electric Vehicles")),
        "total_vehicles": as_int(row.get("Total Vehicles")),
        "population_estimate": as_float(row.get("Population Estimate")),
        "total_kw_charging": as_float(row.get("Total KW Charging")),
        "bevs_per_charge_point": as_float(row.get("BEVs per Charge Point")),
        "kw_charging_per_bev": as_float(row.get("KW Charging per BEV")),
        "bev_penetration": as_float(row.get("BEV Penetration")),
        "bevs_per_capita": as_float(row.get("BEVs per Capita")),
    }
    if level == "district":
        result["district"] = row.get("District")
    return result


def command_datasets(args: argparse.Namespace) -> None:
    data = fetch_json(CKAN_PACKAGE_URL)
    if not data.get("success"):
        die("data.govt.nz package_show returned success=false")
    package = data.get("result", {})
    resources = []
    for res in package.get("resources", []):
        resources.append(
            {
                "name": res.get("name"),
                "format": res.get("format"),
                "url": res.get("url"),
                "created": res.get("created"),
                "last_modified": res.get("last_modified"),
                "metadata_modified": res.get("metadata_modified"),
            }
        )
    payload = {
        "status": "ok",
        "source": "EECA Public EV Charger Dashboard and data.govt.nz CKAN",
        "dashboard_url": EECA_DASHBOARD,
        "dataset_page": DATASET_PAGE,
        "package": {
            "name": package.get("name"),
            "title": package.get("title"),
            "metadata_modified": package.get("metadata_modified"),
            "frequency_of_update": package.get("frequency_of_update"),
            "notes": package.get("notes"),
        },
        "resources": resources,
        "caveats": [
            "CSV resource last-modified fields may be blank in CKAN; use package metadata plus row content for currency.",
            "EECA dashboard data is derived from EVRoam/EECA sources and may lag live charger commissioning.",
        ],
    }

    def render(p: dict[str, Any]) -> None:
        pkg = p["package"]
        print(f"{pkg['title']} ({pkg['name']})")
        print(f"Modified: {pkg.get('metadata_modified') or 'unknown'}")
        for res in p["resources"]:
            print(f"- [{res.get('format') or 'unknown'}] {res.get('name')}: {res.get('url')}")
        print(p["dashboard_url"])

    emit(payload, args.json, render)


def command_chargers(args: argparse.Namespace) -> None:
    rows, final_url = fetch_csv_rows("chargers")
    records = [normalise_charger(row) for row in rows]
    if args.region:
        records = [row for row in records if match_contains(row.get("region", ""), args.region)]
    if args.district:
        records = [row for row in records if match_contains(row.get("district", ""), args.district)]
    if args.current:
        records = [row for row in records if norm(row.get("current")) == norm(args.current)]
    if args.min_kw is not None:
        records = [row for row in records if (row.get("kw_rated") or 0) >= args.min_kw]
    if args.operator:
        records = [row for row in records if match_contains(row.get("operator", ""), args.operator)]
    if args.limit:
        records = records[: args.limit]
    payload = {
        "status": "ok",
        "source": RESOURCES["chargers"]["label"],
        "url": final_url,
        "filters": {
            "region": args.region,
            "district": args.district,
            "current": args.current,
            "min_kw": args.min_kw,
            "operator": args.operator,
        },
        "count": len(records),
        "charge_points": point_count(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Public EV charger units: {p['count']} units, {p['charge_points']} charge points")
        for row in p["records"][: args.limit or 20]:
            print(
                f"- {row['site_id']} ({row['region']}, {row['district']}): "
                f"{row['points']} point(s), {fmt_float(row['kw_rated'])} kW {row['current']}"
            )
            print(f"  {row['address']}")

    emit(payload, args.json, render)


def command_metrics(args: argparse.Namespace) -> None:
    resource = "metrics-region" if args.level == "region" else "metrics-district"
    rows, final_url = fetch_csv_rows(resource)
    records = [normalise_metric(row, args.level) for row in rows]
    if args.region:
        records = [row for row in records if match_contains(row.get("region", ""), args.region)]
    if args.district and args.level == "district":
        records = [row for row in records if match_contains(row.get("district", ""), args.district)]
    if args.sort:
        records.sort(key=lambda row: row.get(args.sort) if row.get(args.sort) is not None else -1, reverse=True)
    if args.limit:
        records = records[: args.limit]
    payload = {
        "status": "ok",
        "source": RESOURCES[resource]["label"],
        "url": final_url,
        "level": args.level,
        "count": len(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"EV metrics by {p['level']}: {p['count']} row(s)")
        for row in p["records"][: args.limit or 20]:
            print(
                f"- {row['name']}: {fmt_int(row['charge_points'])} points, "
                f"{fmt_int(row['sites'])} sites, {fmt_int(row['battery_electric_vehicles'])} BEVs, "
                f"{fmt_float(row['bevs_per_charge_point'])} BEVs/point"
            )

    emit(payload, args.json, render)


def command_cofunded(args: argparse.Namespace) -> None:
    rows, final_url = fetch_csv_rows("cofunded")
    records = [normalise_cofunded(row) for row in rows]
    if args.status:
        status_map = {"live": "live", "in-progress": "in progress"}
        target = status_map[args.status]
        records = [row for row in records if norm(row.get("status")) == target]
    if args.region:
        records = [row for row in records if match_contains(row.get("region", ""), args.region)]
    if args.district:
        records = [row for row in records if match_contains(row.get("district", ""), args.district)]
    if args.min_kw is not None:
        records = [row for row in records if (row.get("kw_rated") or 0) >= args.min_kw]
    if args.limit:
        records = records[: args.limit]
    payload = {
        "status": "ok",
        "source": RESOURCES["cofunded"]["label"],
        "url": final_url,
        "filters": {
            "status": args.status,
            "region": args.region,
            "district": args.district,
            "min_kw": args.min_kw,
        },
        "count": len(records),
        "charge_points": point_count(records),
        "records": records,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"Co-funded EV chargers: {p['count']} application row(s), {p['charge_points']} charge points")
        for row in p["records"][: args.limit or 20]:
            print(
                f"- {row['application_id']} {row['applicant']} ({row['status']}): "
                f"{row['region']} {fmt_float(row['kw_rated'])} kW, live {row['go_live_date'] or 'n/a'}"
            )

    emit(payload, args.json, render)


def command_summary(args: argparse.Namespace) -> None:
    charger_rows, charger_url = fetch_csv_rows("chargers")
    metric_rows, metric_url = fetch_csv_rows("metrics-region" if args.level == "region" else "metrics-district")
    chargers = [normalise_charger(row) for row in charger_rows]
    metrics = [normalise_metric(row, args.level) for row in metric_rows]
    if args.min_kw is not None:
        chargers = [row for row in chargers if (row.get("kw_rated") or 0) >= args.min_kw]
    if args.region:
        chargers = [row for row in chargers if match_contains(row.get("region", ""), args.region)]
        metrics = [row for row in metrics if match_contains(row.get("region", ""), args.region)]
    if args.district and args.level == "district":
        chargers = [row for row in chargers if match_contains(row.get("district", ""), args.district)]
        metrics = [row for row in metrics if match_contains(row.get("district", ""), args.district)]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in chargers:
        key = row.get("region") if args.level == "region" else row.get("district")
        grouped[str(key or "Unknown")].append(row)
    metric_by_name = {norm(str(row["name"])): row for row in metrics}

    records = []
    for name, rows in grouped.items():
        site_ids = {row.get("site_id") for row in rows if row.get("site_id")}
        dc_fast_sites = {
            row.get("site_id")
            for row in rows
            if row.get("site_id") and norm(row.get("current")) == "dc" and (row.get("kw_rated") or 0) >= 50
        }
        kws = [row.get("kw_rated") for row in rows if row.get("kw_rated") is not None]
        metric = metric_by_name.get(norm(name), {})
        charge_points = point_count(rows)
        bevs = metric.get("battery_electric_vehicles")
        total_kw = kw_total(rows)
        records.append(
            {
                "level": args.level,
                "name": name,
                "units": len(rows),
                "charge_points": charge_points,
                "sites": len(site_ids),
                "dc_fast_sites": len(dc_fast_sites),
                "total_kw_charging_from_units": round(total_kw, 3),
                "median_unit_kw": statistics.median(kws) if kws else None,
                "battery_electric_vehicles": bevs,
                "bevs_per_charge_point": (bevs / charge_points) if bevs and charge_points else None,
                "kw_per_bev_from_units": (total_kw / bevs) if bevs and total_kw else None,
                "dashboard_metric": metric,
            }
        )
    records.sort(key=lambda row: row["charge_points"], reverse=True)
    if args.limit:
        records = records[: args.limit]
    payload = {
        "status": "ok",
        "source": "EECA public charger units plus EV metrics CSVs",
        "level": args.level,
        "filters": {"min_kw": args.min_kw, "region": args.region, "district": args.district},
        "urls": {"chargers": charger_url, "metrics": metric_url},
        "count": len(records),
        "records": records,
        "caveats": [
            "Summary totals from charger units multiply each unit's rated kW by point count; EECA metric totals may use different source timing.",
            "DC fast sites are counted as sites with at least one DC unit rated 50 kW or above.",
            "District and region names are matched from dashboard CSV text, not geocoded.",
        ],
    }

    def render(p: dict[str, Any]) -> None:
        print(f"EV charger summary by {p['level']}: {p['count']} row(s)")
        for row in p["records"][: args.limit or 20]:
            print(
                f"- {row['name']}: {fmt_int(row['charge_points'])} points, "
                f"{fmt_int(row['sites'])} sites, {fmt_int(row['dc_fast_sites'])} DC fast sites, "
                f"{fmt_float(row['bevs_per_charge_point'])} BEVs/point"
            )

    emit(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query EECA public EV charger dashboard CSVs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("datasets", help="Report package/resources and metadata")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_datasets)

    p = sub.add_parser("chargers", help="List public EV charger units")
    p.add_argument("--region")
    p.add_argument("--district")
    p.add_argument("--min-kw", type=float)
    p.add_argument("--current", choices=["AC", "DC"])
    p.add_argument("--operator")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_chargers)

    p = sub.add_parser("metrics", help="Return EV metrics by region or district")
    p.add_argument("--level", choices=["region", "district"], default="region")
    p.add_argument("--region")
    p.add_argument("--district")
    p.add_argument("--sort", choices=["charge_points", "sites", "battery_electric_vehicles", "bevs_per_charge_point", "kw_charging_per_bev"])
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_metrics)

    p = sub.add_parser("cofunded", help="List EECA co-funded charger applications")
    p.add_argument("--status", choices=["live", "in-progress"])
    p.add_argument("--region")
    p.add_argument("--district")
    p.add_argument("--min-kw", type=float)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_cofunded)

    p = sub.add_parser("summary", help="Aggregate charger coverage and EV ratios")
    p.add_argument("--level", choices=["region", "district"], default="region")
    p.add_argument("--region")
    p.add_argument("--district")
    p.add_argument("--min-kw", type=float)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_summary)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
