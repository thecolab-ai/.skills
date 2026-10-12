#!/usr/bin/env python3
"""Bounded reader for Queensland traffic incidents on OpenDataSoft."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from provenance import error_envelope, geojson_envelope, parse_bbox, provenance, result_envelope

ALLOWED_HOST = "queensland.opendatasoft.com"
DATASET_ID = "queensland-traffic-incidents"
DATASET_URL = (
    "https://queensland.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "queensland-traffic-incidents"
)
RECORDS_URL = DATASET_URL + "/records"
USER_AGENT = "thecolab-qld-traffic-incidents/1.0 (public data skill; keyless)"
DEFAULT_PUBLISHER = "Queensland"
EXPECTED_LICENCE = "CC BY 4.0"
TIMEOUT_SECONDS = 15
MAX_LIMIT = 20
MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 2
SELECT_FIELDS = (
    "id,status,incident_category,advicea,adviceb,otheradvice,"
    "roads_main_street,roads_suburb,lga,impact_impact_type,impact_impact_subtype,"
    "event_priority,duration_start,duration_end,last_updated,geo_point_2d,url"
)
FILTER_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z .,'’/&-]{0,79}$")
FIXTURE_ENV = "QLD_TRAFFIC_INCIDENTS_FIXTURE"
TEXT_FIELDS = (
    "status",
    "incident_category",
    "advicea",
    "adviceb",
    "otheradvice",
    "roads_main_street",
    "roads_suburb",
    "lga",
    "impact_impact_type",
    "impact_impact_subtype",
    "event_priority",
    "duration_start",
    "duration_end",
    "last_updated",
    "url",
)


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class SourceFailure(Exception):
    """A typed source or contract failure with a stable exit code."""

    def __init__(self, code: int, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if number < 1 or number > MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def parse_filter(value: str) -> str:
    if not FILTER_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "filters must be 1-80 letters, numbers, spaces or .,'’/&-"
        )
    return value


def quote_odsql(value: str) -> str:
    if not FILTER_PATTERN.fullmatch(value):
        raise SourceFailure(2, "filter text is not safe to send")
    return '"' + value + '"'


def format_coord(value: float) -> str:
    return format(value, ".8f").rstrip("0").rstrip(".")


def build_where(
    *,
    status: str | None,
    category: str | None,
    lga: str | None,
    bbox: tuple[float, float, float, float] | None,
) -> str | None:
    """Build an ODSQL where clause. Box filtering is upstream point-in-box."""
    parts: list[str] = []
    if status:
        parts.append(f"status={quote_odsql(status)}")
    if category:
        parts.append(f"incident_category={quote_odsql(category)}")
    if lga:
        parts.append(f"lga={quote_odsql(lga)}")
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        # in_bbox expects south, west, north, east (latitude, longitude).
        parts.append(
            "in_bbox(geo_point_2d,"
            f"{format_coord(min_lat)},{format_coord(min_lon)},"
            f"{format_coord(max_lat)},{format_coord(max_lon)})"
        )
    if not parts:
        return None
    return " and ".join(parts)


def records_query_url(
    *,
    limit: int,
    status: str | None = None,
    category: str | None = None,
    lga: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> str:
    if limit < 1 or limit > MAX_LIMIT:
        raise SourceFailure(2, f"--limit must be an integer from 1 to {MAX_LIMIT}")
    params = {
        "limit": str(limit),
        "select": SELECT_FIELDS,
        "order_by": "last_updated desc",
    }
    where = build_where(status=status, category=category, lga=lga, bbox=bbox)
    if where:
        params["where"] = where
    return RECORDS_URL + "?" + urllib.parse.urlencode(params)


def assert_official_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != ALLOWED_HOST
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
    ):
        host = parts.hostname or "unknown"
        raise SourceFailure(7, f"redirect to a host outside the allowlist is rejected: {host}")


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects = 0

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.redirects += 1
        if self.redirects > MAX_REDIRECTS:
            raise SourceFailure(7, "redirect to a host outside the allowlist is rejected: too many redirects")
        assert_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_capped(response: Any) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = response.read(65_536)
        if not block:
            break
        total += len(block)
        if total > MAX_BYTES:
            raise SourceFailure(6, "non-JSON or truncated JSON response")
        chunks.append(block)
    return b"".join(chunks)


def loads_strict(body: bytes) -> Any:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFailure(6, "non-JSON or truncated JSON response") from exc

    def reject_constant(constant: str) -> None:
        raise SourceFailure(6, "non-JSON or truncated JSON response")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except SourceFailure:
        raise
    except json.JSONDecodeError as exc:
        raise SourceFailure(6, "non-JSON or truncated JSON response") from exc


def header_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def failure_from_status(status: int, headers: dict[str, str]) -> SourceFailure:
    if status == 429:
        retry_after = headers.get("retry-after")
        cleaned = retry_after.strip() if isinstance(retry_after, str) and retry_after.strip() else None
        return SourceFailure(4, "http 429: rate limited", retry_after=cleaned)
    if status == 503 or status >= 500:
        return SourceFailure(5, f"network error: HTTP {status}")
    if status in {401, 403}:
        return SourceFailure(4, f"http {status}: access blocked")
    return SourceFailure(6, f"unexpected HTTP {status}")


def fetch_bytes(url: str, *, timeout: float = TIMEOUT_SECONDS) -> tuple[int, dict[str, str], bytes]:
    assert_official_url(url)
    handler = AllowlistRedirectHandler()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), handler)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            assert_official_url(final_url)
            status = int(getattr(response, "status", None) or response.getcode())
            headers = header_map(response.headers)
            body = read_capped(response)
    except SourceFailure:
        raise
    except urllib.error.HTTPError as exc:
        headers = header_map(exc.headers)
        try:
            body = exc.read(MAX_BYTES + 1)
        except (TimeoutError, socket.timeout, OSError) as read_error:
            raise SourceFailure(5, "network error: source request failed") from read_error
        if len(body) > MAX_BYTES:
            raise SourceFailure(6, "non-JSON or truncated JSON response") from exc
        raise failure_from_status(int(exc.code), headers) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise SourceFailure(5, "network error: source request timed out") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, SourceFailure):
            raise reason from exc
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
            raise SourceFailure(5, "network error: source request timed out") from exc
        raise SourceFailure(5, "network error: source request failed") from exc
    if status != 200:
        raise failure_from_status(status, headers)
    return status, headers, body


def fetch_json(url: str, *, timeout: float = TIMEOUT_SECONDS) -> Any:
    _status, _headers, body = fetch_bytes(url, timeout=timeout)
    payload = loads_strict(body)
    if not isinstance(payload, dict):
        raise SourceFailure(6, "non-JSON or truncated JSON response")
    return payload


def as_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceFailure(6, f"source schema failure: {label} is missing")
    return value


def as_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceFailure(6, f"source schema failure: {field} must be a string or null")
    return value


def as_coordinate(value: Any, low: float, high: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SourceFailure(6, f"source schema failure: {field} is not a finite coordinate")
    number = float(value)
    if number < low or number > high:
        raise SourceFailure(6, f"source schema failure: {field} is outside WGS84 range")
    return number


def parse_dataset(payload: Any) -> dict[str, str]:
    document = as_mapping(payload, "dataset document")
    if document.get("dataset_id") != DATASET_ID:
        raise SourceFailure(6, "source schema failure: dataset_id is not queensland-traffic-incidents")
    default = as_mapping(as_mapping(document.get("metas"), "metas").get("default"), "metas.default")
    licence = default.get("license")
    licence_url = default.get("license_url")
    if not isinstance(licence, str) or not licence.strip() or not isinstance(licence_url, str):
        raise SourceFailure(4, "dataset licence was not stated; refusing to emit records")
    licence_parts = urllib.parse.urlsplit(licence_url)
    licence_host = licence_parts.hostname or ""
    licence_path = licence_parts.path.rstrip("/")
    official_licence_host = licence_host == "creativecommons.org" or licence_host.endswith(".creativecommons.org")
    if (
        licence != EXPECTED_LICENCE
        or licence_parts.scheme != "https"
        or not official_licence_host
        or licence_path != "/licenses/by/4.0"
    ):
        raise SourceFailure(4, "dataset licence is not CC BY 4.0; refusing to emit records")
    publisher = default.get("publisher")
    if not isinstance(publisher, str) or not publisher.strip():
        raise SourceFailure(6, "source schema failure: publisher is missing")
    info = {"licence": licence, "publisher": publisher.strip()}
    processed = default.get("data_processed")
    if isinstance(processed, str) and processed.strip():
        info["latest_data"] = processed.strip()
    return info


def normalise_record(raw: Any) -> dict[str, Any]:
    record = as_mapping(raw, "incident record")
    identifier = record.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise SourceFailure(6, "source schema failure: incident id is missing")
    for field in TEXT_FIELDS:
        if field in record:
            as_text(record.get(field), field)
    point = record.get("geo_point_2d")
    longitude = None
    latitude = None
    if point is not None:
        point_map = as_mapping(point, "geo_point_2d")
        longitude = as_coordinate(point_map.get("lon"), -180, 180, "longitude")
        latitude = as_coordinate(point_map.get("lat"), -90, 90, "latitude")
    return {
        "id": identifier,
        "status": as_text(record.get("status"), "status"),
        "category": as_text(record.get("incident_category"), "incident_category"),
        "event_subtype": as_text(record.get("advicea"), "advicea"),
        "advice": as_text(record.get("adviceb"), "adviceb"),
        "description": as_text(record.get("otheradvice"), "otheradvice"),
        "road_name": as_text(record.get("roads_main_street"), "roads_main_street"),
        "suburb": as_text(record.get("roads_suburb"), "roads_suburb"),
        "lga": as_text(record.get("lga"), "lga"),
        "impact_type": as_text(record.get("impact_impact_type"), "impact_impact_type"),
        "impact_subtype": as_text(record.get("impact_impact_subtype"), "impact_impact_subtype"),
        "priority": as_text(record.get("event_priority"), "event_priority"),
        "duration_start": as_text(record.get("duration_start"), "duration_start"),
        "duration_end": as_text(record.get("duration_end"), "duration_end"),
        "last_updated": as_text(record.get("last_updated"), "last_updated"),
        "event_url": as_text(record.get("url"), "url"),
        "longitude": longitude,
        "latitude": latitude,
    }


def parse_records(payload: Any, *, limit: int) -> tuple[int, list[dict[str, Any]]]:
    document = as_mapping(payload, "records document")
    total = document.get("total_count")
    results = document.get("results")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise SourceFailure(6, "source schema failure: total_count is missing")
    if not isinstance(results, list):
        raise SourceFailure(6, "source schema failure: results is missing")
    if len(results) > limit or len(results) > MAX_LIMIT:
        raise SourceFailure(6, "source schema failure: response exceeded the requested limit")
    if total == 0 and results:
        raise SourceFailure(6, "source schema failure: empty total_count included records")
    if total < len(results):
        raise SourceFailure(6, "source schema failure: total_count is smaller than results")
    return total, [normalise_record(item) for item in results]


def load_positive_fixture() -> tuple[Any, Any]:
    fixture_dir = skill_root() / "tests" / "fixtures"
    dataset = json.loads((fixture_dir / "dataset-positive.json").read_text(encoding="utf-8"))
    records = json.loads((fixture_dir / "records-positive.json").read_text(encoding="utf-8"))
    return dataset, records


def source_meta(info: dict[str, str] | None, source_url: str) -> dict[str, str]:
    publisher = DEFAULT_PUBLISHER if info is None else info.get("publisher", DEFAULT_PUBLISHER)
    return provenance(
        source_url,
        publisher,
        licence=None if info is None else info.get("licence"),
        latest_data=None if info is None else info.get("latest_data"),
    )


def feature_collection(records: list[dict[str, Any]], meta: dict[str, str]) -> dict[str, Any]:
    features = []
    for record in records:
        longitude = record["longitude"]
        latitude = record["latitude"]
        geometry = None
        if longitude is not None and latitude is not None:
            geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        features.append({"type": "Feature", "geometry": geometry, "properties": record})
    return geojson_envelope(features, meta)


def wants_machine_output(argv: list[str]) -> bool:
    if "--json" in argv:
        return True
    for index, token in enumerate(argv):
        if token == "--format=geojson":
            return True
        if token == "--format" and index + 1 < len(argv) and argv[index + 1] == "geojson":
            return True
    return False


def emit_failure(failure: SourceFailure, meta: dict[str, str], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(
            error_envelope(failure.code, failure.message, meta, retry_after=failure.retry_after),
            indent=2,
            ensure_ascii=False,
        ))
    else:
        message = failure.message
        if failure.retry_after:
            message = f"{message}; retry_after={failure.retry_after}"
        print(f"qld-traffic-incidents: {message}", file=sys.stderr)
    return failure.code


def emit_success(
    records: list[dict[str, Any]],
    *,
    total_count: int,
    meta: dict[str, str],
    output_format: str,
    as_json: bool,
) -> int:
    enriched = dict(meta)
    enriched["total_count"] = str(total_count)
    if output_format == "geojson":
        print(json.dumps(feature_collection(records, enriched), indent=2, ensure_ascii=False))
        return 0
    if as_json:
        print(json.dumps(result_envelope(records, enriched), indent=2, ensure_ascii=False))
        return 0
    licence = enriched.get("licence", "licence not stated")
    latest = enriched.get("latest_data", "not stated")
    print(f"Queensland traffic incidents — {licence}")
    print(f"Publisher: {enriched['publisher']}")
    print(f"Dataset processed: {latest}")
    print(f"Showing {len(records)} of {total_count} (newest last_updated first; not the full incident set)")
    if not records:
        print("No incidents matched.")
        return 0
    for record in records:
        place = ", ".join(part for part in (record["road_name"], record["suburb"]) if part)
        category = record["category"] if record["category"] is not None else "unspecified"
        status = record["status"] if record["status"] is not None else "status not stated"
        updated = record["last_updated"] if record["last_updated"] is not None else "updated time not stated"
        print(f"{record['id']}  {category}  {place or 'location not stated'}  {status}  {updated}")
    return 0


def run_incidents(args: argparse.Namespace) -> int:
    as_json = bool(args.json or args.format == "geojson")
    query_url = records_query_url(
        limit=args.limit,
        status=args.status,
        category=args.category,
        lga=args.lga,
        bbox=args.bbox,
    )
    fixture_mode = os.environ.get(FIXTURE_ENV)
    if fixture_mode is not None and fixture_mode != "positive":
        return emit_failure(
            SourceFailure(2, "QLD_TRAFFIC_INCIDENTS_FIXTURE only accepts the bundled positive fixture"),
            source_meta(None, DATASET_URL),
            as_json=as_json,
        )
    try:
        if fixture_mode == "positive":
            dataset_payload, records_payload = load_positive_fixture()
        else:
            dataset_payload = fetch_json(DATASET_URL, timeout=TIMEOUT_SECONDS)
        info = parse_dataset(dataset_payload)
        if fixture_mode != "positive":
            records_payload = fetch_json(query_url, timeout=TIMEOUT_SECONDS)
        total_count, records = parse_records(records_payload, limit=args.limit)
    except SourceFailure as failure:
        return emit_failure(failure, source_meta(None, DATASET_URL), as_json=as_json)
    return emit_success(
        records,
        total_count=total_count,
        meta=source_meta(info, query_url),
        output_format=args.format,
        as_json=as_json,
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Queensland traffic incidents")
    sub = parser.add_subparsers(dest="command", required=True)
    incidents = sub.add_parser("incidents", help="read a bounded window of Queensland traffic incidents")
    incidents.add_argument("--limit", type=parse_limit, required=True, help=f"records to return, from 1 to {MAX_LIMIT}")
    incidents.add_argument("--status", type=parse_filter, help="exact incident status, such as Published")
    incidents.add_argument("--category", type=parse_filter, help="exact incident category, such as Hazard")
    incidents.add_argument("--lga", type=parse_filter, help="exact local government area name")
    incidents.add_argument("--bbox", type=parse_bbox, metavar="minLon,minLat,maxLon,maxLat", help="keep incidents whose published point lies inside this WGS84 box")
    incidents.add_argument("--format", choices=("json", "geojson"), default="json", help="json envelope or GeoJSON; geojson is machine-readable")
    incidents.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        if wants_machine_output(argv):
            print(json.dumps(
                error_envelope(2, str(exc), source_meta(None, DATASET_URL)),
                indent=2,
                ensure_ascii=False,
            ))
        else:
            parser.print_usage(sys.stderr)
            print(f"qld-traffic-incidents: {exc}", file=sys.stderr)
        return 2
    if args.command == "incidents":
        return run_incidents(args)
    return emit_failure(
        SourceFailure(7, "unsupported operation"),
        source_meta(None, DATASET_URL),
        as_json=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
