#!/usr/bin/env python3
"""Query official Stats NZ building-consent release series and workbook tables."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402
from building_consents import graph_records, parse_annual_workbook, parse_release  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

RELEASE_URL = "https://www.stats.govt.nz/information-releases/building-consents-issued-may-2026/"
HOSTS = {"stats.govt.nz", "www.stats.govt.nz", "datainfoplus.stats.govt.nz"}
WARNINGS = [
    "Consents are intentions or authorisations, not completed buildings.",
    "Residential units, buildings, alterations, and non-residential measures are distinct.",
    "The latest release workbook can revise previously published series.",
    "Regional release graphs cover new-dwelling counts; this release publishes national value and floor-area tables.",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("latest", "compare-regions", "definitions"):
        child = commands.add_parser(name)
        child.add_argument("--limit", type=int, default=50)
        child.add_argument("--json", action="store_true")
    for name, positional in (("region", "name"), ("type", "name")):
        child = commands.add_parser(name)
        child.add_argument(positional)
        child.add_argument("--limit", type=int, default=50)
        child.add_argument("--json", action="store_true")
    series = commands.add_parser("timeseries")
    series.add_argument("--from", dest="from_date", required=True)
    series.add_argument("--to", dest="to_date", required=True)
    series.add_argument("--limit", type=int, default=50)
    series.add_argument("--json", action="store_true")
    value = commands.add_parser("value")
    value.add_argument("--region", required=True)
    value.add_argument("--limit", type=int, default=50)
    value.add_argument("--json", action="store_true")
    return parser


def parse_date(value: str, *, end: bool = False) -> date:
    try:
        if len(value) == 7:
            year, month = map(int, value.split("-"))
            if end:
                return date(year + (month == 12), 1 if month == 12 else month + 1, 1)
            return date(year, month, 1)
        parsed = date.fromisoformat(value)
        return parsed + timedelta(days=1) if end else parsed
    except ValueError as exc:
        raise ValueError("dates must be YYYY-MM or YYYY-MM-DD") from exc


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 100:
        print(json.dumps({"error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr)
        return 2
    stamp = utc_now()
    try:
        timeseries_bounds = None
        if args.command == "timeseries":
            start = parse_date(args.from_date)
            end = parse_date(args.to_date, end=True)
            if start >= end:
                raise ValueError("--from must not be after --to")
            timeseries_bounds = (start, end)
        release = parse_release(nzfetch.fetch_text(RELEASE_URL, timeout=30, allowed_hosts=HOSTS), RELEASE_URL, stamp)
        source_url = RELEASE_URL
        if args.command == "latest":
            monthly = graph_records(release, "New dwellings consented, monthly")
            latest_period = max(row["period"] for row in monthly)
            data = [{
                "title": release["title"],
                "publication_date": release["publication_date"],
                "latest_period": latest_period,
                "documents": release["documents"],
                "latest_series": [row for row in monthly if row["period"] == latest_period],
                "source_url": RELEASE_URL,
                "retrieved_at": stamp,
            }]
        elif args.command in {"region", "compare-regions"}:
            rows = graph_records(release, "New dwellings consented, by region")
            latest_period = max(row["period"] for row in rows)
            rows = [row for row in rows if row["period"] == latest_period]
            if args.command == "region":
                needle = args.name.casefold()
                rows = [row for row in rows if needle in row["category"].casefold()]
            data = rows[: args.limit]
        elif args.command == "timeseries":
            start, end = timeseries_bounds
            rows = graph_records(release, "New dwellings consented, monthly")
            data = [row for row in rows if start <= date.fromisoformat(row["period"]) < end][: args.limit]
        elif args.command == "definitions":
            data = [{
                "measures": {"count": "number", "value": "NZD million", "floor_area": "thousand square metres"},
                "adjustments": ["actual", "seasonally adjusted", "trend"],
                "frequency": ["monthly", "year ended release month"],
                "revision_status": "current release values may revise earlier publications",
                "methodology_url": "https://datainfoplus.stats.govt.nz/item/nz.govt.stats/ee083b32-8c10-4ccf-b1ee-a4990b27273c",
                "source_url": RELEASE_URL,
                "retrieved_at": stamp,
            }]
            source_url = data[0]["methodology_url"]
        else:
            workbook = next((item for item in release["documents"] if item["url"].lower().endswith(".xlsx")), None)
            if not workbook:
                raise ValueError("Stats NZ release no longer links its XLSX workbook")
            body, _, _ = nzfetch.fetch_bytes(workbook["url"], timeout=45, allowed_hosts=HOSTS)
            rows = parse_annual_workbook(body, workbook["url"], stamp)
            source_url = workbook["url"]
            if args.command == "type":
                needle = args.name.casefold()
                rows = [row for row in rows if needle in row["building_type"].casefold()]
            else:
                if args.region.casefold() not in {"new zealand", "nz", "national"}:
                    print(json.dumps({"error": "unsupported_operation", "message": "This release workbook publishes value series nationally; use region for regional new-dwelling counts."}), file=sys.stderr)
                    return 7
                rows = [row for row in rows if row["measure"] == "value"]
            data = sorted(rows, key=lambda item: item["period"], reverse=True)[: args.limit]
        envelope = result_envelope(
            ok=True,
            source_name="Stats NZ Building Consents Issued",
            source_url=source_url,
            retrieved_at=stamp,
            freshness=f"monthly release published {release['publication_date']}",
            query=vars(args),
            data=data,
            warnings=WARNINGS,
            blocked=False,
        )
        print(json.dumps(envelope if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input_or_source_schema", "message": str(exc)}), file=sys.stderr)
        return 2 if str(exc).startswith(("--", "dates")) else 6
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
