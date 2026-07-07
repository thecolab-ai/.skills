#!/usr/bin/env python3
"""Read-only CLI for NZTA/Waka Kotahi Crash Analysis System public data.

Uses public no-key ArcGIS FeatureServer and data.govt.nz CKAN metadata. The
public layer exposes crash year rather than exact crash date, so date flags are
converted to bounded calendar-year filters and reported with a caveat.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

ARCGIS_LAYER = (
    "https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/"
    "CAS_Data_Public/FeatureServer/0"
)
ARCGIS_QUERY = ARCGIS_LAYER + "/query"
ARCGIS_HUB_DATASET = (
    "https://opendata-nzta.opendata.arcgis.com/datasets/"
    "NZTA::crash-analysis-system-cas-data-1/about"
)
CKAN_BASE = "https://catalogue.data.govt.nz"
CKAN_DATASET = "crash-analysis-system-cas-data5"
CKAN_PACKAGE_URL = CKAN_BASE + "/api/3/action/package_show"
CSV_URL = (
    "https://opendata-nzta.opendata.arcgis.com/api/download/v1/items/"
    "8d684f1841fa4dbea6afaefc8a1ba0fc/csv?layers=0"
)

UA = "nzta-crash-data-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
TIMEOUT = 10
PAGE_SIZE = 2000
DEFAULT_LIMIT = 50
MAX_LIMIT = 5000
DEFAULT_SCAN_CAP = 100000

SEVERITY_VALUES = {
    "fatal": "Fatal Crash",
    "serious": "Serious Crash",
    "minor": "Minor Crash",
    "non-injury": "Non-Injury Crash",
}

CRASH_FIELDS = [
    "OBJECTID",
    "crashYear",
    "crashFinancialYear",
    "crashSeverity",
    "region",
    "tlaName",
    "crashLocation1",
    "crashLocation2",
    "crashSHDescription",
    "fatalCount",
    "seriousInjuryCount",
    "minorInjuryCount",
    "weatherA",
    "weatherB",
    "roadSurface",
    "light",
    "streetLight",
    "speedLimit",
    "urban",
    "bicycle",
    "pedestrian",
    "motorcycle",
    "truck",
    "bus",
]

FACTOR_GROUPS = {
    "road_users_and_vehicle_types": [
        ("bicycle", "Bicycle"),
        ("pedestrian", "Pedestrian"),
        ("motorcycle", "Motorcycle"),
        ("moped", "Moped"),
        ("truck", "Truck"),
        ("bus", "Bus"),
        ("schoolBus", "School bus"),
        ("train", "Train"),
        ("carStationWagon", "Car/station wagon"),
        ("suv", "SUV"),
        ("vanOrUtility", "Van or utility"),
    ],
    "roadside_objects_and_hazards": [
        ("bridge", "Bridge"),
        ("cliffBank", "Cliff bank"),
        ("debris", "Debris"),
        ("ditch", "Ditch"),
        ("fence", "Fence"),
        ("guardRail", "Guard rail"),
        ("houseOrBuilding", "House or building"),
        ("kerb", "Kerb"),
        ("objectThrownOrDropped", "Object thrown or dropped"),
        ("otherObject", "Other object"),
        ("overBank", "Over bank"),
        ("parkedVehicle", "Parked vehicle"),
        ("postOrPole", "Post or pole"),
        ("strayAnimal", "Stray animal"),
        ("trafficIsland", "Traffic island"),
        ("trafficSign", "Traffic sign"),
        ("tree", "Tree"),
        ("waterRiver", "Water/river"),
    ],
    "environment_indicators": [
        ("roadworks", "Road works"),
        ("slipOrFlood", "Slip or flood"),
        ("intersection", "Intersection"),
    ],
}

CATEGORICAL_FACTORS = [
    ("weatherA", "weather_primary"),
    ("weatherB", "weather_secondary"),
    ("light", "light"),
    ("roadSurface", "road_surface"),
    ("urban", "urban_open_road"),
    ("speedLimit", "speed_limit"),
]

DATE_PRECISION_NOTE = (
    "The public CAS FeatureServer exposes crashYear and crashFinancialYear, "
    "not an exact crash date. --from/--to are applied as calendar-year bounds."
)
LAG_NOTE = (
    "CAS is updated monthly. Fatal crashes are usually available within about "
    "1 working day; serious and minor injury crashes may lag by about 4 weeks, "
    "so recent-period DSI/minor counts can be incomplete."
)
FACTOR_CAVEAT = (
    "The public CAS layer does not expose detailed driver contributing-factor "
    "codes such as alcohol/drugs, speed as a cause, or fatigue. The factors "
    "command aggregates the public crash-level indicator fields that are "
    "available."
)


class DataError(Exception):
    """Raised for expected upstream or input failures."""


def die(message: str, code: int = 1) -> None:
    print(f"nzta-crash-data-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    method: str = "GET",
    timeout: int = TIMEOUT,
) -> dict[str, Any]:
    target = url
    data = None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if params:
        encoded = urllib.parse.urlencode(params).encode("utf-8")
        if method == "POST":
            data = encoded
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            target = url + ("&" if "?" in url else "?") + encoded.decode("utf-8")
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            target, timeout=timeout, accept="application/json", headers=headers, data=data
        )
    except nzfetch.Blocked as exc:
        raise DataError(f"network error: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise DataError(str(exc)) from exc
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise DataError(f"invalid JSON from {url}: {exc}") from exc


def request_csv_rows(scan_cap: int) -> tuple[list[dict[str, str]], bool]:
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            CSV_URL, timeout=TIMEOUT, accept="text/csv", headers={"User-Agent": UA}
        )
    except nzfetch.Blocked as exc:
        raise DataError(f"network error downloading CKAN/ArcGIS CSV mirror: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise DataError(f"error downloading CKAN/ArcGIS CSV mirror: {exc}") from exc
    rows: list[dict[str, str]] = []
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace")))
        for index, row in enumerate(reader, start=1):
            if index > scan_cap:
                return rows, True
            rows.append(row)
    except csv.Error as exc:
        raise DataError(f"invalid CSV from CKAN/ArcGIS mirror: {exc}") from exc
    return rows, False


def ckan_package() -> dict[str, Any]:
    data = request_json(CKAN_PACKAGE_URL, {"id": CKAN_DATASET})
    if not data.get("success"):
        raise DataError(f"CKAN package_show returned success=false: {data.get('error')}")
    return data.get("result") or {}


def arcgis_query(params: dict[str, Any]) -> dict[str, Any]:
    merged = {"f": "json", "returnGeometry": "false"}
    merged.update(params)
    data = request_json(ARCGIS_QUERY, merged, method="POST")
    if isinstance(data.get("error"), dict):
        err = data["error"]
        message = err.get("message") or "ArcGIS query error"
        details = "; ".join(str(d) for d in err.get("details") or [])
        raise DataError(f"ArcGIS query failed: {message}{': ' + details if details else ''}")
    return data


def emit(payload: dict[str, Any], json_flag: bool, renderer: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        renderer(payload)


def parse_date(value: str | None, flag: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        die(f"invalid date for {flag}: {value}; expected YYYY-MM-DD")


def date_window(args: argparse.Namespace) -> tuple[dt.date, dt.date, int, int, bool]:
    end = parse_date(getattr(args, "date_to", None), "--to") or dt.date.today()
    defaulted_start = not bool(getattr(args, "date_from", None))
    start = parse_date(getattr(args, "date_from", None), "--from")
    if start is None:
        start = dt.date(max(2000, end.year - 1), 1, 1)
    if start > end:
        die(f"invalid date window: --from {start.isoformat()} is after --to {end.isoformat()}")
    return start, end, start.year, end.year, defaulted_start


def bounded_limit(value: int) -> int:
    if value < 1:
        die("--limit must be at least 1")
    if value > MAX_LIMIT:
        die(f"--limit must be {MAX_LIMIT} or less to avoid unbounded CAS downloads")
    return value


def sql_string(value: str) -> str:
    return value.replace("'", "''")


def region_where(region: str | None) -> str | None:
    if not region:
        return None
    cleaned = re.sub(r"\s+", " ", region.strip())
    if not cleaned:
        return None
    if len(cleaned) > 80:
        die("--region is too long")
    value = sql_string(cleaned)
    return f"(region LIKE '%{value}%' OR tlaName LIKE '%{value}%')"


def build_where(
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    year: int | None = None,
    severity: str | None = None,
    region: str | None = None,
) -> str:
    parts = []
    if year is not None:
        parts.append(f"crashYear = {int(year)}")
    else:
        if start_year is not None:
            parts.append(f"crashYear >= {int(start_year)}")
        if end_year is not None:
            parts.append(f"crashYear <= {int(end_year)}")
    if severity:
        parts.append(f"crashSeverity = '{sql_string(SEVERITY_VALUES[severity])}'")
    region_part = region_where(region)
    if region_part:
        parts.append(region_part)
    return " AND ".join(parts) if parts else "1=1"


def crash_count(where: str) -> int:
    data = arcgis_query({"where": where, "returnCountOnly": "true"})
    return int(data.get("count") or 0)


def arcgis_stats(where: str, stats: list[dict[str, str]], **extra: Any) -> list[dict[str, Any]]:
    params = {
        "where": where,
        "outStatistics": json.dumps(stats, separators=(",", ":")),
    }
    params.update({k: v for k, v in extra.items() if v is not None})
    data = arcgis_query(params)
    return [feature.get("attributes") or {} for feature in data.get("features") or []]


def paged_crashes(where: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    total = crash_count(where)
    records: list[dict[str, Any]] = []
    offset = 0
    while len(records) < limit and offset < total:
        page_size = min(PAGE_SIZE, limit - len(records))
        data = arcgis_query(
            {
                "where": where,
                "outFields": ",".join(CRASH_FIELDS),
                "orderByFields": "crashYear DESC, OBJECTID DESC",
                "resultOffset": str(offset),
                "resultRecordCount": str(page_size),
            }
        )
        features = data.get("features") or []
        if not features:
            break
        for feature in features:
            records.append(clean_crash_record(feature.get("attributes") or {}))
        offset += len(features)
    return total, records


def clean_crash_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "object_id": as_int(row.get("OBJECTID")),
        "year": as_int(row.get("crashYear")),
        "financial_year": row.get("crashFinancialYear"),
        "severity": row.get("crashSeverity"),
        "region": row.get("region"),
        "tla": row.get("tlaName"),
        "location": compact_join(row.get("crashLocation1"), row.get("crashLocation2")),
        "state_highway": row.get("crashSHDescription"),
        "fatalities": as_int(row.get("fatalCount")),
        "serious_injuries": as_int(row.get("seriousInjuryCount")),
        "minor_injuries": as_int(row.get("minorInjuryCount")),
        "weather": compact_join(row.get("weatherA"), row.get("weatherB")),
        "road_surface": row.get("roadSurface"),
        "light": row.get("light"),
        "street_light": row.get("streetLight"),
        "speed_limit": as_int(row.get("speedLimit")),
        "urban": row.get("urban"),
        "road_user_indicators": {
            "bicycle": as_int(row.get("bicycle")),
            "pedestrian": as_int(row.get("pedestrian")),
            "motorcycle": as_int(row.get("motorcycle")),
            "truck": as_int(row.get("truck")),
            "bus": as_int(row.get("bus")),
        },
    }


def compact_join(*parts: Any) -> str | None:
    values = [str(part).strip() for part in parts if part not in (None, "", "Null")]
    return " / ".join(values) if values else None


def as_int(value: Any) -> int | None:
    if value in (None, "", "Null"):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def probe_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    try:
        layer = request_json(ARCGIS_LAYER, {"f": "json"})
        if isinstance(layer.get("error"), dict):
            raise DataError(layer["error"].get("message") or "ArcGIS metadata error")
        sources.append(
            {
                "name": "ArcGIS FeatureServer",
                "kind": "feature_service",
                "reachable": True,
                "url": ARCGIS_LAYER,
                "dataset_url": ARCGIS_HUB_DATASET,
                "layer_name": layer.get("name"),
                "max_record_count": layer.get("maxRecordCount"),
                "fields": len(layer.get("fields") or []),
                "object_id_field": layer.get("objectIdField"),
            }
        )
    except DataError as exc:
        sources.append(
            {
                "name": "ArcGIS FeatureServer",
                "kind": "feature_service",
                "reachable": False,
                "url": ARCGIS_LAYER,
                "dataset_url": ARCGIS_HUB_DATASET,
                "error": str(exc),
            }
        )
    try:
        pkg = ckan_package()
        resources = [
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "format": resource.get("format"),
                "url": resource.get("url"),
            }
            for resource in pkg.get("resources") or []
        ]
        sources.append(
            {
                "name": "data.govt.nz CKAN mirror",
                "kind": "ckan_package",
                "reachable": True,
                "url": f"{CKAN_BASE}/dataset/{CKAN_DATASET}",
                "package_id": pkg.get("name"),
                "title": pkg.get("title"),
                "metadata_modified": pkg.get("metadata_modified"),
                "resources": resources,
            }
        )
    except DataError as exc:
        sources.append(
            {
                "name": "data.govt.nz CKAN mirror",
                "kind": "ckan_package",
                "reachable": False,
                "url": f"{CKAN_BASE}/dataset/{CKAN_DATASET}",
                "error": str(exc),
            }
        )
    return sources


def cmd_datasets(args: argparse.Namespace) -> None:
    sources = probe_sources()
    reachable = [source for source in sources if source.get("reachable")]
    if not reachable:
        die("both ArcGIS FeatureServer and CKAN mirror are unreachable")
    payload = {
        "kind": "datasets",
        "selected_data_source": "ArcGIS FeatureServer" if sources[0].get("reachable") else reachable[0]["name"],
        "sources": sources,
        "notes": [
            "Use the ArcGIS FeatureServer for bounded queries and pagination.",
            "Use CKAN/data.govt.nz for catalogue metadata and downloadable mirror resources.",
            DATE_PRECISION_NOTE,
            LAG_NOTE,
        ],
    }
    emit(payload, args.json, render_datasets)


def render_datasets(payload: dict[str, Any]) -> None:
    print("NZTA/Waka Kotahi Crash Analysis System public data")
    print(f"Selected data source: {payload['selected_data_source']}")
    for source in payload["sources"]:
        status = "reachable" if source.get("reachable") else "unreachable"
        print(f"\n- {source['name']}: {status}")
        print(f"  url: {source['url']}")
        if source.get("error"):
            print(f"  error: {source['error']}")
        if source.get("metadata_modified"):
            print(f"  metadata modified: {source['metadata_modified']}")
        if source.get("fields"):
            print(f"  fields: {source['fields']} | max page size: {source.get('max_record_count')}")
    print("\nNotes:")
    for note in payload["notes"]:
        print(f"- {note}")


def cmd_crashes(args: argparse.Namespace) -> None:
    limit = bounded_limit(args.limit)
    start, end, start_year, end_year, defaulted_start = date_window(args)
    where = build_where(
        start_year=start_year,
        end_year=end_year,
        severity=args.severity,
        region=args.region,
    )
    notes = [DATE_PRECISION_NOTE]
    if defaulted_start:
        notes.append("Default window is bounded to the last two calendar years.")
    if end >= dt.date.today() - dt.timedelta(days=35):
        notes.append(LAG_NOTE)
    try:
        if args.source == "csv":
            total, records, csv_notes = csv_crashes(args, start_year, end_year, limit)
            notes.extend(csv_notes)
            source = "CKAN/ArcGIS CSV mirror"
        else:
            total, records = paged_crashes(where, limit)
            source = "ArcGIS FeatureServer"
    except DataError as exc:
        if args.source == "arcgis":
            raise
        total, records, csv_notes = csv_crashes(args, start_year, end_year, limit)
        notes.append(f"ArcGIS query failed, fell back to capped CSV mirror scan: {exc}")
        notes.extend(csv_notes)
        source = "CKAN/ArcGIS CSV mirror"
    payload = {
        "kind": "crashes",
        "source": source,
        "where": where if source == "ArcGIS FeatureServer" else None,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "year_bounds": {"from": start_year, "to": end_year},
        "region": args.region,
        "severity": args.severity,
        "total_matching": total,
        "returned": len(records),
        "limit": limit,
        "records": records,
        "notes": notes,
    }
    emit(payload, args.json, render_crashes)


def render_crashes(payload: dict[str, Any]) -> None:
    print("CAS crash records")
    print(f"Source: {payload['source']}")
    print(f"Window: {payload['date_from']} to {payload['date_to']} (years {payload['year_bounds']['from']}-{payload['year_bounds']['to']})")
    if payload.get("region"):
        print(f"Region/TLA filter: {payload['region']}")
    if payload.get("severity"):
        print(f"Severity: {payload['severity']}")
    print(f"Total matching: {payload['total_matching']} | returned: {payload['returned']} of limit {payload['limit']}")
    for record in payload["records"]:
        injury = (
            f"fatalities={record.get('fatalities') or 0}, "
            f"serious={record.get('serious_injuries') or 0}, "
            f"minor={record.get('minor_injuries') or 0}"
        )
        print(
            f"- {record.get('year')} {record.get('severity')} | "
            f"{record.get('region') or '-'} / {record.get('tla') or '-'} | "
            f"{record.get('location') or '-'} | {injury}"
        )
    if payload["notes"]:
        print("\nNotes:")
        for note in payload["notes"]:
            print(f"- {note}")


def cmd_road_toll(args: argparse.Namespace) -> None:
    year = args.year
    if year < 2000:
        die("--year must be 2000 or later for the public CAS open-data layer")
    where = build_where(year=year, severity="fatal")
    notes = [DATE_PRECISION_NOTE]
    if year == dt.date.today().year:
        notes.append("This is a running current-year total from the latest public CAS layer.")
        notes.append(LAG_NOTE)
    try:
        if args.source == "csv":
            payload = csv_road_toll(args, year, notes)
        else:
            stats = [
                {"statisticType": "sum", "onStatisticField": "fatalCount", "outStatisticFieldName": "fatalities"},
                {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "fatal_crashes"},
                {"statisticType": "sum", "onStatisticField": "seriousInjuryCount", "outStatisticFieldName": "serious_injuries"},
                {"statisticType": "sum", "onStatisticField": "minorInjuryCount", "outStatisticFieldName": "minor_injuries"},
            ]
            attrs = (arcgis_stats(where, stats) or [{}])[0]
            payload = {
                "kind": "road-toll",
                "source": "ArcGIS FeatureServer",
                "where": where,
                "year": year,
                "fatalities": int(attrs.get("fatalities") or 0),
                "fatal_crashes": int(attrs.get("fatal_crashes") or 0),
                "serious_injuries_in_fatal_crashes": int(attrs.get("serious_injuries") or 0),
                "minor_injuries_in_fatal_crashes": int(attrs.get("minor_injuries") or 0),
                "current_year_to_date": year == dt.date.today().year,
                "notes": notes,
            }
    except DataError as exc:
        if args.source == "arcgis":
            raise
        notes.append(f"ArcGIS query failed, fell back to capped CSV mirror scan: {exc}")
        payload = csv_road_toll(args, year, notes)
    emit(payload, args.json, render_road_toll)


def render_road_toll(payload: dict[str, Any]) -> None:
    suffix = " (current year to date)" if payload.get("current_year_to_date") else ""
    print(f"CAS road toll {payload['year']}{suffix}")
    print(f"Source: {payload['source']}")
    print(f"Fatalities: {payload['fatalities']}")
    print(f"Fatal crashes: {payload['fatal_crashes']}")
    print(f"Serious injuries in fatal crashes: {payload['serious_injuries_in_fatal_crashes']}")
    if payload.get("notes"):
        print("\nNotes:")
        for note in payload["notes"]:
            print(f"- {note}")


def cmd_factors(args: argparse.Namespace) -> None:
    start, end, start_year, end_year, defaulted_start = date_window(args)
    where = build_where(start_year=start_year, end_year=end_year, region=args.region)
    notes = [DATE_PRECISION_NOTE, FACTOR_CAVEAT]
    if defaulted_start:
        notes.append("Default window is bounded to the last two calendar years.")
    if end >= dt.date.today() - dt.timedelta(days=35):
        notes.append(LAG_NOTE)
    try:
        if args.source == "csv":
            payload = csv_factors(args, start, end, start_year, end_year, notes)
        else:
            count = crash_count(where)
            numeric_stats = [
                {"statisticType": "sum", "onStatisticField": field, "outStatisticFieldName": f"{field}_sum"}
                for fields in FACTOR_GROUPS.values()
                for field, _label in fields
            ]
            attrs = (arcgis_stats(where, numeric_stats) or [{}])[0]
            groups = {
                group: [
                    {
                        "field": field,
                        "label": label,
                        "crashes_or_units": int(attrs.get(f"{field}_sum") or 0),
                    }
                    for field, label in fields
                    if int(attrs.get(f"{field}_sum") or 0) > 0
                ]
                for group, fields in FACTOR_GROUPS.items()
            }
            categories = {
                output_name: grouped_counts(where, field, args.top)
                for field, output_name in CATEGORICAL_FACTORS
            }
            payload = {
                "kind": "factors",
                "source": "ArcGIS FeatureServer",
                "where": where,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "year_bounds": {"from": start_year, "to": end_year},
                "region": args.region,
                "crash_count": count,
                "indicator_groups": groups,
                "categorical_distributions": categories,
                "notes": notes,
            }
    except DataError as exc:
        if args.source == "arcgis":
            raise
        notes.append(f"ArcGIS query failed, fell back to capped CSV mirror scan: {exc}")
        payload = csv_factors(args, start, end, start_year, end_year, notes)
    emit(payload, args.json, render_factors)


def grouped_counts(where: str, field: str, limit: int) -> list[dict[str, Any]]:
    stats = [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "crash_count"}]
    rows = arcgis_stats(
        where,
        stats,
        groupByFieldsForStatistics=field,
        orderByFields="crash_count DESC",
        resultRecordCount=str(limit),
    )
    values = []
    for row in rows:
        value = row.get(field)
        if value in (None, "", "Null"):
            value = "Unknown"
        values.append({"value": value, "crashes": int(row.get("crash_count") or 0)})
    return values


def render_factors(payload: dict[str, Any]) -> None:
    print("CAS public indicator aggregation")
    print(f"Source: {payload['source']}")
    print(f"Window: {payload['date_from']} to {payload['date_to']} (years {payload['year_bounds']['from']}-{payload['year_bounds']['to']})")
    if payload.get("region"):
        print(f"Region/TLA filter: {payload['region']}")
    print(f"Crashes in scope: {payload['crash_count']}")
    for group, rows in payload["indicator_groups"].items():
        print(f"\n{group.replace('_', ' ').title()}:")
        if not rows:
            print("- no public indicators counted")
        for row in rows[:12]:
            print(f"- {row['label']}: {row['crashes_or_units']}")
    print("\nCategorical distributions:")
    for name, rows in payload["categorical_distributions"].items():
        print(f"- {name}: " + ", ".join(f"{row['value']} ({row['crashes']})" for row in rows[:6]))
    if payload.get("notes"):
        print("\nNotes:")
        for note in payload["notes"]:
            print(f"- {note}")


def csv_matches(row: dict[str, str], start_year: int, end_year: int, severity: str | None, region: str | None) -> bool:
    year = as_int(row.get("crashYear"))
    if year is None or year < start_year or year > end_year:
        return False
    if severity and row.get("crashSeverity") != SEVERITY_VALUES[severity]:
        return False
    if region:
        needle = region.lower()
        if needle not in (row.get("region") or "").lower() and needle not in (row.get("tlaName") or "").lower():
            return False
    return True


def csv_crashes(
    args: argparse.Namespace,
    start_year: int,
    end_year: int,
    limit: int,
) -> tuple[int | None, list[dict[str, Any]], list[str]]:
    rows, capped = request_csv_rows(args.scan_cap)
    matched = []
    for row in rows:
        if csv_matches(row, start_year, end_year, args.severity, args.region):
            matched.append(clean_crash_record(row))
            if len(matched) >= limit:
                break
    notes = [f"CSV mirror fallback scanned at most {args.scan_cap} rows to avoid a full-history download."]
    if capped:
        notes.append("CSV scan cap was reached; total_matching is only matched rows seen before the cap.")
    return len(matched) if capped else None, matched, notes


def csv_road_toll(args: argparse.Namespace, year: int, notes: list[str]) -> dict[str, Any]:
    rows, capped = request_csv_rows(args.scan_cap)
    if capped:
        raise DataError("CSV fallback scan cap reached before a complete yearly toll could be calculated")
    fatal_crashes = 0
    fatalities = 0
    serious = 0
    minor = 0
    for row in rows:
        if as_int(row.get("crashYear")) == year and row.get("crashSeverity") == "Fatal Crash":
            fatal_crashes += 1
            fatalities += as_int(row.get("fatalCount")) or 0
            serious += as_int(row.get("seriousInjuryCount")) or 0
            minor += as_int(row.get("minorInjuryCount")) or 0
    notes = list(notes)
    notes.append("Calculated from the CKAN/ArcGIS CSV mirror after scanning the complete downloaded file.")
    return {
        "kind": "road-toll",
        "source": "CKAN/ArcGIS CSV mirror",
        "where": None,
        "year": year,
        "fatalities": fatalities,
        "fatal_crashes": fatal_crashes,
        "serious_injuries_in_fatal_crashes": serious,
        "minor_injuries_in_fatal_crashes": minor,
        "current_year_to_date": year == dt.date.today().year,
        "notes": notes,
    }


def csv_factors(
    args: argparse.Namespace,
    start: dt.date,
    end: dt.date,
    start_year: int,
    end_year: int,
    notes: list[str],
) -> dict[str, Any]:
    rows, capped = request_csv_rows(args.scan_cap)
    scoped = [
        row for row in rows if csv_matches(row, start_year, end_year, None, args.region)
    ]
    groups = {}
    for group, fields in FACTOR_GROUPS.items():
        group_rows = []
        for field, label in fields:
            total = sum(as_int(row.get(field)) or 0 for row in scoped)
            if total:
                group_rows.append({"field": field, "label": label, "crashes_or_units": total})
        groups[group] = group_rows
    categories = {}
    for field, output_name in CATEGORICAL_FACTORS:
        counts: dict[str, int] = {}
        for row in scoped:
            value = row.get(field) or "Unknown"
            if value == "Null":
                value = "Unknown"
            counts[value] = counts.get(value, 0) + 1
        categories[output_name] = [
            {"value": value, "crashes": count}
            for value, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[: args.top]
        ]
    notes = list(notes)
    notes.append(f"CSV mirror fallback scanned at most {args.scan_cap} rows to avoid a full-history download.")
    if capped:
        notes.append("CSV scan cap was reached; factor counts are partial.")
    return {
        "kind": "factors",
        "source": "CKAN/ArcGIS CSV mirror",
        "where": None,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "year_bounds": {"from": start_year, "to": end_year},
        "region": args.region,
        "crash_count": len(scoped),
        "indicator_groups": groups,
        "categorical_distributions": categories,
        "notes": notes,
    }


def add_common_data_args(parser: argparse.ArgumentParser, *, include_window: bool = True) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--source",
        choices=("auto", "arcgis", "csv"),
        default="auto",
        help="data source preference; auto uses ArcGIS and falls back to capped CSV scan",
    )
    parser.add_argument(
        "--scan-cap",
        type=int,
        default=DEFAULT_SCAN_CAP,
        help="maximum CSV rows to scan if the capped mirror fallback is used",
    )
    if include_window:
        parser.add_argument("--from", dest="date_from", help="start date YYYY-MM-DD; applied as a crashYear bound")
        parser.add_argument("--to", dest="date_to", help="end date YYYY-MM-DD; applied as a crashYear bound")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nzta-crash-data-nz",
        description="Query NZTA/Waka Kotahi public CAS crash statistics.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    datasets = sub.add_parser("datasets", help="show ArcGIS and CKAN source status")
    datasets.add_argument("--json", action="store_true", help="print machine-readable JSON")
    datasets.set_defaults(func=cmd_datasets)

    crashes = sub.add_parser("crashes", help="list bounded CAS crash records")
    add_common_data_args(crashes)
    crashes.add_argument("--region", help="region or TLA name substring, e.g. Auckland or Wellington")
    crashes.add_argument("--severity", choices=tuple(SEVERITY_VALUES), help="crash severity")
    crashes.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"records to return, max {MAX_LIMIT}")
    crashes.set_defaults(func=cmd_crashes)

    road_toll = sub.add_parser("road-toll", help="summarise yearly fatalities and fatal crashes")
    add_common_data_args(road_toll, include_window=False)
    road_toll.add_argument("--year", type=int, required=True, help="calendar year, 2000 or later")
    road_toll.set_defaults(func=cmd_road_toll)

    factors = sub.add_parser("factors", help="aggregate public crash indicator fields")
    add_common_data_args(factors)
    factors.add_argument("--region", help="region or TLA name substring, e.g. Auckland or Wellington")
    factors.add_argument("--top", type=int, default=8, help="top values for categorical distributions")
    factors.set_defaults(func=cmd_factors)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "scan_cap", DEFAULT_SCAN_CAP) < 1:
        die("--scan-cap must be at least 1")
    if getattr(args, "top", 1) < 1:
        die("--top must be at least 1")
    try:
        args.func(args)
    except DataError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
