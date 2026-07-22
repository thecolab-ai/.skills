#!/usr/bin/env python3
"""Query Wellington Water (Tiaki Wai) public network fault and job records.

Reads the public ArcGIS feature layer behind Tiaki Wai's network-status map:
current drinking water, wastewater, and stormwater faults and repair jobs for
Wellington, Hutt, Upper Hutt, and Porirua. Read-only, no authentication.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

LAYER = (
    "https://services7.arcgis.com/2ECs938g489DMWjt/arcgis/rest/services/"
    "Job_Status_Public_View/FeatureServer/5"
)
SOURCE_NAME = "Wellington Water (Tiaki Wai) public job status layer"
SOURCE_PAGE = "https://www.tiakiwai.co.nz/faults-and-outages/see-outages/network-status"
NZ_TZ = ZoneInfo("Pacific/Auckland")

COUNCILS = {"wcc": "WCC", "hcc": "HCC", "uhcc": "UHCC", "pcc": "PCC"}
WATER_TYPES = {
    "drinking": "Potable Water",
    "storm": "Storm Water",
    "waste": "Waste Water",
}
# Upstream marks some rows Do Not Display; suppressing them is part of the
# source's own publication contract, so they are always excluded.
HIDDEN_STATUS = "Do Not Display"
RESOLVED_STATUS = "Resolved"


def die(message: str, code: int = 1) -> None:
    print(f"tiakiwai-water-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def query_layer(params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    url = LAYER + "/query?" + urllib.parse.urlencode(params)
    try:
        data = nzfetch.fetch_json(url, timeout=30)
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    if isinstance(data, dict) and data.get("error"):
        detail = data["error"].get("message") or json.dumps(data["error"])[:200]
        die(f"ArcGIS error: {detail}", 5)
    return data, url


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_where(args: argparse.Namespace) -> str:
    clauses = [f"StatusDescription <> {sql_quote(HIDDEN_STATUS)}"]
    if not getattr(args, "include_resolved", False):
        clauses.append(f"StatusDescription <> {sql_quote(RESOLVED_STATUS)}")
    if getattr(args, "council", None):
        clauses.append(f"councilid = {sql_quote(COUNCILS[args.council])}")
    if getattr(args, "water_type", None):
        clauses.append(f"watertype = {sql_quote(WATER_TYPES[args.water_type])}")
    if getattr(args, "search", None):
        needle = sql_quote("%" + args.search.upper() + "%")
        clauses.append(f"(UPPER(description) LIKE {needle} OR UPPER(wsadd_formattedaddress) LIKE {needle})")
    return " AND ".join(clauses)


def epoch_to_nz(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).astimezone(NZ_TZ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def normalise_job(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    return {
        "job_number": props.get("wonum"),
        "council_ref": props.get("externalrefid"),
        "council": props.get("councilid"),
        "water_type": props.get("watertype"),
        "status": props.get("StatusDescription"),
        "job_type": props.get("wtypedesc") or props.get("type"),
        "priority": props.get("priority"),
        "description": props.get("description"),
        "category": props.get("comm_description"),
        "address": props.get("wsadd_formattedaddress"),
        "reported_at": epoch_to_nz(props.get("reportdate")),
        "work_started_at": epoch_to_nz(props.get("actstart")),
        "completed_at": epoch_to_nz(props.get("compdate")),
        "longitude": coords[0] if isinstance(coords, list) and len(coords) > 0 else None,
        "latitude": coords[1] if isinstance(coords, list) and len(coords) > 1 else None,
    }


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_faults(args: argparse.Namespace) -> None:
    where = build_where(args)
    data, url = query_layer(
        {
            "where": where,
            "outFields": "*",
            "orderByFields": "reportdate DESC",
            "resultRecordCount": args.limit,
            "outSR": "4326",
            "f": "geojson",
        }
    )
    features = data.get("features")
    if features is None:
        die(f"source schema failure: layer query returned no features array: {str(data)[:200]}", 6)
    jobs = [normalise_job(f) for f in features]
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    payload = {
        "kind": "faults",
        "source": SOURCE_NAME,
        "source_url": url,
        "source_page": SOURCE_PAGE,
        "where": where,
        "timezone": "Pacific/Auckland",
        "count": len(jobs),
        "truncated": truncated,
        "note": "open jobs only unless --include-resolved; rows the source marks Do Not Display are always excluded",
        "faults": jobs,
    }
    lines = [f"Tiaki Wai open jobs: {len(jobs)} shown" + (" (truncated; add filters)" if truncated else "")]
    for j in jobs:
        lines.append(
            f"- [{j['council']}/{j['water_type']}] {j['description']} — {j['status']}, priority {j['priority']}, reported {j['reported_at']} ({j['job_number']})"
        )
    emit(payload, args.json, lines)


def cmd_fault(args: argparse.Namespace) -> None:
    if not args.job_number.isdigit():
        die(f"invalid job number {args.job_number!r}: expected digits (the wonum from faults output)", 2)
    data, url = query_layer(
        {
            "where": f"wonum = {sql_quote(args.job_number)}",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    features = data.get("features")
    if features is None:
        die(f"source schema failure: layer query returned no features array: {str(data)[:200]}", 6)
    if not features:
        die(f"no job found with number {args.job_number}; it may have aged off the public layer", 2)
    payload = {
        "kind": "fault",
        "source": SOURCE_NAME,
        "source_url": url,
        "timezone": "Pacific/Auckland",
        "fault": normalise_job(features[0]),
        "raw_properties": (features[0].get("properties") or {}),
    }
    j = payload["fault"]
    emit(
        payload,
        args.json,
        [
            f"{j['job_number']} [{j['council']}/{j['water_type']}] {j['description']}",
            f"  status: {j['status']} | priority: {j['priority']} | type: {j['job_type']}",
            f"  address: {j['address']}",
            f"  reported: {j['reported_at']} | started: {j['work_started_at']} | completed: {j['completed_at']}",
        ],
    )


def cmd_summary(args: argparse.Namespace) -> None:
    where = build_where(args)
    data, url = query_layer(
        {
            "where": where,
            "groupByFieldsForStatistics": "councilid,watertype",
            "outStatistics": json.dumps(
                [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "job_count"}]
            ),
            "f": "json",
        }
    )
    features = data.get("features")
    if features is None:
        die(f"source schema failure: statistics query returned no features array: {str(data)[:200]}", 6)
    rows = sorted(
        (
            {
                "council": f.get("attributes", {}).get("councilid"),
                "water_type": f.get("attributes", {}).get("watertype"),
                "open_jobs": f.get("attributes", {}).get("job_count"),
            }
            for f in features
        ),
        key=lambda r: -(r["open_jobs"] or 0),
    )
    payload = {
        "kind": "summary",
        "source": SOURCE_NAME,
        "source_url": url,
        "where": where,
        "total_open_jobs": sum(r["open_jobs"] or 0 for r in rows),
        "by_council_and_type": rows,
    }
    lines = [f"Tiaki Wai open jobs by council and water type (total {payload['total_open_jobs']}):"]
    for r in rows:
        lines.append(f"- {r['council']} {r['water_type']}: {r['open_jobs']}")
    emit(payload, args.json, lines)


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def main() -> None:
    parser = argparse.ArgumentParser(description="Wellington Water (Tiaki Wai) public fault and job status")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("faults", help="list open water/wastewater/stormwater jobs, newest first")
    s.add_argument("--council", choices=sorted(COUNCILS), help="filter to one council area")
    s.add_argument("--water-type", choices=sorted(WATER_TYPES), help="drinking, storm, or waste")
    s.add_argument("--search", help="case-insensitive text match on description or address")
    s.add_argument("--include-resolved", action="store_true", help="also include recently resolved jobs")
    s.add_argument("--limit", type=positive_int(2000), default=50, help="maximum jobs (default 50)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_faults)

    s = sub.add_parser("fault", help="one job by its job number (wonum)")
    s.add_argument("job_number", help="job number from faults output")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_fault)

    s = sub.add_parser("summary", help="open-job counts by council and water type")
    s.add_argument("--council", choices=sorted(COUNCILS), help="filter to one council area")
    s.add_argument("--water-type", choices=sorted(WATER_TYPES), help="drinking, storm, or waste")
    s.add_argument("--include-resolved", action="store_true", help="also count recently resolved jobs")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
