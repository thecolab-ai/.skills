#!/usr/bin/env python3
"""Query official FENZ operational reports and annual incident datasets."""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402
from fenz_incidents import LICENCE, PUBLISHER, aggregate_annual, parse_annual_resources, parse_incidents  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

RECENT_URL = "https://www.fireandemergency.nz/incidents-and-news/incident-reports/incidents/"
ANNUAL_URL = "https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/"
METADATA_URL = "https://www.fireandemergency.nz/assets/Documents/About-FENZ/Incident-data/FENZ-Incident-Metadata-2025_12.pdf"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
REPORT_REGIONS = {"north": "1", "central": "2", "south": "3"}
HOSTS = {"www.fireandemergency.nz"}
WARNINGS = [
    "Operational incident labels are preliminary, not final annual classifications.",
    "Absence from the seven-day public feed does not prove no incident occurred.",
    "Annual files contain one row per exposure; incident counts use distinct Incident ID within each returned region/type group.",
    "FENZ can revise annual data for correctness and completeness.",
]


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    recent = commands.add_parser("recent")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--json", action="store_true")
    for name, positional in (("search", "query"), ("region", "name"), ("type", "name"), ("incident", "id")):
        child = commands.add_parser(name)
        child.add_argument(positional)
        child.add_argument("--limit", type=int, default=20)
        child.add_argument("--json", action="store_true")
    for child in (recent, *[commands.choices[name] for name in ("search", "region", "type", "incident")]):
        child.add_argument("--day", choices=DAYS, help="Published weekday; defaults to yesterday in NZ")
        child.add_argument("--report-region", choices=("all", *REPORT_REGIONS), default="all")
    annual = commands.add_parser("annual")
    annual.add_argument("--year", required=True, help="financial year, for example 2024-25")
    annual.add_argument("--region")
    annual.add_argument("--type", dest="incident_type")
    annual.add_argument("--limit", type=int, default=20)
    annual.add_argument("--json", action="store_true")
    trend = commands.add_parser("trend")
    trend.add_argument("--region", required=True)
    trend.add_argument("--type", dest="incident_type")
    trend.add_argument("--limit", type=int, default=100)
    trend.add_argument("--json", action="store_true")
    return parser


def incident_url(day, region_id):
    if day not in DAYS or region_id not in REPORT_REGIONS.values():
        raise ValueError("Invalid FENZ report day or region")
    return RECENT_URL + "?" + urlencode({"day": day, "region": region_id})


def fetch_annual_rows(resource, stamp, *, region=None, incident_type=None):
    body, _, final_url = nzfetch.fetch_bytes(resource["download_url"], timeout=10, allowed_hosts=HOSTS)
    return aggregate_annual(body, final_url, stamp, resource["financial_year"], region=region, incident_type=incident_type, metadata_url=METADATA_URL)


def error_provenance(stamp):
    return {"source_url": RECENT_URL, "publisher": PUBLISHER, "licence": LICENCE, "retrieved_at": stamp}


def main():
    args = build_parser().parse_args()
    stamp = utc_now()
    if not 1 <= args.limit <= 100:
        print(json.dumps({**error_provenance(stamp), "error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr)
        return 2
    if args.command == "annual" and not re.fullmatch(r"20\d{2}[-/]\d{2}", args.year):
        print(json.dumps({**error_provenance(stamp), "error": "invalid_input", "message": "--year must be a financial year such as 2024-25"}), file=sys.stderr)
        return 2
    try:
        if args.command in {"annual", "trend"}:
            partial_warning = None
            page = nzfetch.fetch_text(ANNUAL_URL, timeout=10, allowed_hosts=HOSTS)
            resources = parse_annual_resources(page, ANNUAL_URL, stamp)
            if args.command == "annual":
                wanted = args.year.replace("/", "-")
                resource = next((item for item in resources if item["financial_year"] == wanted), None)
                if not resource:
                    print(json.dumps({**error_provenance(stamp), "error": "unsupported_operation", "code": 7, "message": f"Official annual incident data is not published for {args.year}."}), file=sys.stderr)
                    return 7
                data = fetch_annual_rows(resource, stamp, region=args.region, incident_type=args.incident_type)[: args.limit]
                source_url = resource["download_url"]
            else:
                data = []
                failures = []
                for resource in resources:
                    try:
                        data.extend(fetch_annual_rows(resource, stamp, region=args.region, incident_type=args.incident_type))
                    except nzfetch.RateLimited:
                        raise
                    except nzfetch.Blocked:
                        raise
                    except (nzfetch.FetchError, ValueError) as exc:
                        failures.append(f"{resource['financial_year']}: {exc}")
                if not data and failures:
                    raise ValueError("all FENZ annual datasets failed: " + "; ".join(failures))
                data = sorted(data, key=lambda row: (row["financial_year"], row["incident_type"]))[: args.limit]
                source_url = ANNUAL_URL
                if failures:
                    partial_warning = "Some annual datasets failed independently: " + "; ".join(failures)
            warnings = list(WARNINGS) + [f"Field definitions and codes: {METADATA_URL}"]
            if partial_warning:
                warnings.append(partial_warning)
            freshness = "annual; published financial-year resources discovered from the official source"
            source_name = "FENZ annual incident data"
        else:
            day = args.day or DAYS[(datetime.now(ZoneInfo("Pacific/Auckland")) - timedelta(days=1)).weekday()]
            selected = REPORT_REGIONS if args.report_region == "all" else {args.report_region: REPORT_REGIONS[args.report_region]}
            rows = []
            for report_region, region_id in selected.items():
                url = incident_url(day, region_id)
                records = parse_incidents(nzfetch.fetch_text(url, timeout=10, allowed_hosts=HOSTS), url, stamp)
                for row in records:
                    row["report_region"] = report_region
                rows.extend(records)
            rows.sort(key=lambda row: (row.get("latest_data", ""), row["date_and_time"], row["incident_number"]), reverse=True)
            term = getattr(args, "query", None) or getattr(args, "name", None) or getattr(args, "id", None)
            field = {"region": "location", "type": "call_type", "incident": "incident_number"}.get(args.command)
            data = [row for row in rows if not term or
                    (term.casefold() == row[field].casefold() if args.command == "incident" else
                     term.casefold() in (row[field] if field else json.dumps(row)).casefold())][: args.limit]
            source_url = incident_url(day, next(iter(selected.values()))) if len(selected) == 1 else RECENT_URL.rsplit("incidents/", 1)[0]
            warnings = WARNINGS[:2] + [f"Scope: {day}, {args.report_region} report region(s); this is a single published day, not the entire seven-day archive."]
            freshness = "operational seven-day feed"
            source_name = "FENZ public incident reports"
        output = result_envelope(ok=True, source_name=source_name, source_url=source_url, retrieved_at=stamp, freshness=freshness, query=vars(args), data=data, warnings=warnings, blocked=False)
        output.update({"source_url": source_url, "publisher": PUBLISHER, "licence": LICENCE, "retrieved_at": stamp})
        if data and any(row.get("latest_data") for row in data):
            output["latest_data"] = max(row["latest_data"] for row in data if row.get("latest_data"))
        print(json.dumps(output if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except nzfetch.RateLimited as exc:
        print(json.dumps({**error_provenance(stamp), "error": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({**error_provenance(stamp), "error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        if re.search(r"HTTP (?:400|401|404|405|410|422)\b", str(exc), re.I):
            print(json.dumps({**error_provenance(stamp), "error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
            return 6
        print(json.dumps({**error_provenance(stamp), "error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5
    except ValueError as exc:
        print(json.dumps({**error_provenance(stamp), "error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
