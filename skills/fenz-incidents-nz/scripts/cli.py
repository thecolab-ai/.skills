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
from result_contract import utc_now  # noqa: E402

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


class InvalidInput(ValueError):
    pass


class ContractParser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidInput(message)


def build_parser():
    parser = ContractParser(description=__doc__)
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


def default_report_day(now=None):
    """Yesterday in NZ, even when the caller's timezone has a different date."""
    now = now or datetime.now(ZoneInfo("Pacific/Auckland"))
    return DAYS[(now.astimezone(ZoneInfo("Pacific/Auckland")) - timedelta(days=1)).weekday()]


def fetch_annual_rows(resource, stamp, *, region=None, incident_type=None):
    body, _, final_url = nzfetch.fetch_bytes(resource["download_url"], timeout=10, allowed_hosts=HOSTS)
    return aggregate_annual(body, final_url, stamp, resource["financial_year"], region=region, incident_type=incident_type, metadata_url=METADATA_URL)


def provenance(url, stamp):
    return {"source_url": url, "publisher": PUBLISHER, "licence": LICENCE, "retrieved_at": stamp}


def emit_error(json_mode, code, message, url, stamp, retry_after=None):
    error = {"code": code, "type": {2: "invalid_input", 4: "blocked", 5: "upstream_unavailable",
             6: "schema_failure", 7: "unsupported_operation"}[code], "message": message}
    if retry_after is not None:
        error["retry_after"] = retry_after
    if json_mode:
        print(json.dumps({"meta": provenance(url, stamp), "results": [], "error": error}))
    else:
        print(f"fenz-incidents: {message}", file=sys.stderr)
    return code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    stamp = utc_now()
    source_url = RECENT_URL
    try:
        args = build_parser().parse_args(argv)
        if args.command in {"annual", "trend"}:
            source_url = ANNUAL_URL
        else:
            day = args.day or default_report_day()
            selected = REPORT_REGIONS if args.report_region == "all" else {args.report_region: REPORT_REGIONS[args.report_region]}
            source_url = incident_url(day, next(iter(selected.values())))
        if not 1 <= args.limit <= 100:
            raise InvalidInput("--limit must be between 1 and 100")
        if args.command == "annual" and not re.fullmatch(r"20\d{2}[-/]\d{2}", args.year):
            raise InvalidInput("--year must be a financial year such as 2024-25")
    except InvalidInput as exc:
        return emit_error("--json" in argv, 2, str(exc), source_url, stamp)
    try:
        if args.command in {"annual", "trend"}:
            partial_warning = None
            page = nzfetch.fetch_text(ANNUAL_URL, timeout=10, allowed_hosts=HOSTS)
            resources = parse_annual_resources(page, ANNUAL_URL, stamp)
            if args.command == "annual":
                wanted = args.year.replace("/", "-")
                resource = next((item for item in resources if item["financial_year"] == wanted), None)
                if not resource:
                    return emit_error(args.json, 7, f"Official annual incident data is not published for {args.year}.", source_url, stamp)
                source_url = resource["download_url"]
                data = fetch_annual_rows(resource, stamp, region=args.region, incident_type=args.incident_type)[: args.limit]
                source_url = resource["download_url"]
            else:
                data = []
                failures = []
                for resource in resources:
                    try:
                        source_url = resource["download_url"]
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
        else:
            rows = []
            for report_region, region_id in selected.items():
                url = incident_url(day, region_id)
                source_url = url  # Retain the actual failed request for error provenance.
                records = parse_incidents(nzfetch.fetch_text(url, timeout=10, allowed_hosts=HOSTS), url, stamp)
                for row in records:
                    row["report_region"] = report_region
                rows.extend(records)
            rows.sort(key=lambda row: (row.get("latest_data", ""), row["date_and_time"], row["incident_number"]), reverse=True)
            term = getattr(args, "query", None) or getattr(args, "name", None) or getattr(args, "id", None)
            field = {"region": "location", "type": "call_type", "incident": "incident_number"}.get(args.command)
            data = [row for row in rows if not term or
                    (term.casefold() == row.get(field, "").casefold() if args.command == "incident" else
                     term.casefold() in (row.get(field, "") if field else json.dumps(row)).casefold())][: args.limit]
            source_url = incident_url(day, next(iter(selected.values()))) if len(selected) == 1 else RECENT_URL.rsplit("incidents/", 1)[0]
            warnings = WARNINGS[:2] + [f"Scope: {day}, {args.report_region} report region(s); this is a single published day, not the entire seven-day archive."]
            freshness = "operational seven-day feed"
        meta = provenance(source_url, stamp)
        meta.update({"warnings": warnings, "freshness": freshness})
        if args.command not in {"annual", "trend"}:
            meta.update({"report_day": day, "report_regions": list(selected)})
        dated_rows = data if args.command in {"annual", "trend"} else rows
        if any(row.get("latest_data") for row in dated_rows):
            meta["latest_data"] = max(row["latest_data"] for row in dated_rows if row.get("latest_data"))
        print(json.dumps({"meta": meta, "results": data} if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except nzfetch.RateLimited as exc:
        return emit_error(args.json, 4, str(exc), source_url, stamp, exc.retry_after)
    except nzfetch.Blocked as exc:
        return emit_error(args.json, 4, str(exc), source_url, stamp)
    except nzfetch.FetchError as exc:
        code = 6 if re.search(r"HTTP (?:400|401|404|405|410|422)\b", str(exc), re.I) else 5
        return emit_error(args.json, code, str(exc), source_url, stamp)
    except ValueError as exc:
        return emit_error(args.json, 6, str(exc), source_url, stamp)


if __name__ == "__main__":
    raise SystemExit(main())
