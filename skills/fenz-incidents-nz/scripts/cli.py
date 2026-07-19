#!/usr/bin/env python3
"""Query official FENZ operational reports and annual incident datasets."""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402
from fenz_incidents import aggregate_annual, parse_annual_resources, parse_incidents  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

RECENT_URL = "https://www.fireandemergency.nz/incidents-and-news/incident-reports/incidents/"
ANNUAL_URL = "https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/"
METADATA_URL = "https://www.fireandemergency.nz/assets/Documents/About-FENZ/Incident-data/FENZ-Incident-Metadata-2025_12.pdf"
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


def fetch_annual_rows(resource, stamp, *, region=None, incident_type=None):
    body, _, final_url = nzfetch.fetch_bytes(resource["download_url"], timeout=60, allowed_hosts=HOSTS)
    return aggregate_annual(body, final_url, stamp, resource["financial_year"], region=region, incident_type=incident_type, metadata_url=METADATA_URL)


def main():
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 100:
        print(json.dumps({"error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr)
        return 2
    if args.command == "annual" and not re.fullmatch(r"20\d{2}[-/]\d{2}", args.year):
        print(json.dumps({"error": "invalid_input", "message": "--year must be a financial year such as 2024-25"}), file=sys.stderr)
        return 2
    stamp = utc_now()
    try:
        if args.command in {"annual", "trend"}:
            partial_warning = None
            page = nzfetch.fetch_text(ANNUAL_URL, timeout=30, allowed_hosts=HOSTS)
            resources = parse_annual_resources(page, ANNUAL_URL, stamp)
            if args.command == "annual":
                wanted = args.year.replace("/", "-")
                resource = next((item for item in resources if item["financial_year"] == wanted), None)
                if not resource:
                    print(json.dumps({"error": "unsupported_operation", "code": 7, "message": f"Official annual incident data is not published for {args.year}."}), file=sys.stderr)
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
            freshness = "annual; source currently publishes 2017-18 through 2024-25"
            source_name = "FENZ annual incident data"
        else:
            rows = parse_incidents(nzfetch.fetch_text(RECENT_URL, timeout=20, allowed_hosts=HOSTS), RECENT_URL, stamp)
            term = getattr(args, "query", None) or getattr(args, "name", None) or getattr(args, "id", None)
            data = [row for row in rows if not term or term.casefold() in json.dumps(row).casefold()][: args.limit]
            source_url = RECENT_URL
            warnings = WARNINGS[:2]
            freshness = "operational seven-day feed"
            source_name = "FENZ public incident reports"
        output = result_envelope(ok=True, source_name=source_name, source_url=source_url, retrieved_at=stamp, freshness=freshness, query=vars(args), data=data, warnings=warnings, blocked=False)
        print(json.dumps(output if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5
    except ValueError as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
