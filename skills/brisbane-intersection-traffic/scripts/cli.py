#!/usr/bin/env python3
"""Keyless Brisbane City Council intersection volumes and signal locations."""
from __future__ import annotations

import argparse
import http.client
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from provenance import add_spatial_arguments, error_envelope, geojson_envelope, provenance, result_envelope

ALLOWED_HOST = "data.brisbane.qld.gov.au"
PUBLISHER = "Brisbane City Council"
USER_AGENT = "thecolab-brisbane-intersection-traffic/1.0 (+https://github.com/thecolab-ai/.skills)"
MAX_LIMIT = 20
DEFAULT_TIMEOUT = 15
MAX_TIMEOUT = 15
MAX_BYTES = 262144
MAX_REDIRECTS = 3
# Each licence string was read from that dataset's own metas.default.license.
VOLUME_DATASET = "traffic-data-at-intersection"
SIGNAL_DATASET = "traffic-management-signal-locations"
VOLUME_LICENCE = "CC BY 4.0"
SIGNAL_LICENCE = "CC BY 4.0"
VOLUME_FIELDS = (
    "dbid",
    "recorded",
    "ct",
    "link_plan",
    "married",
    "ss",
    "tsc",
    "lane",
    "ds1",
    "mf1",
    "rf1",
    "ds2",
    "mf2",
    "rf2",
    "ds3",
    "mf3",
    "rf3",
    "ds4",
    "mf4",
    "rf4",
)
SIGNAL_FIELDS = (
    "objectid",
    "subsystem",
    "tsc",
    "areanum",
    "globalid",
    "geo_shape",
    "geo_point_2d",
)
VOLUME_TEXT = ("dbid", "recorded", "tsc", "lane")
VOLUME_NULLABLE_TEXT = ("ct", "married", "ss", "ds1", "mf1", "rf1", "ds2", "mf2", "rf2", "ds3", "mf3", "rf3", "ds4", "mf4", "rf4")
SIGNAL_TEXT = ("objectid", "tsc", "areanum", "globalid")
RECORDED_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
TSC_VALUE = re.compile(r"^[0-9]{1,8}$")
LANE_VALUE = re.compile(r"^[A-Za-z0-9-]{1,32}$")


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class SkillError(Exception):
    def __init__(self, code: int, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def dataset_source(dataset: str) -> str:
    return f"https://{ALLOWED_HOST}/api/explore/v2.1/catalog/datasets/{dataset}/records"


def source_meta(dataset: str, licence: str, *, latest_data: str | None = None) -> dict[str, str]:
    return provenance(dataset_source(dataset), PUBLISHER, licence=licence, latest_data=latest_data)


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def parse_timeout(value: str) -> float:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise argparse.ArgumentTypeError(f"--timeout must be from 1 to {MAX_TIMEOUT} seconds")
    number = float(value)
    if not 1 <= number <= MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"--timeout must be from 1 to {MAX_TIMEOUT} seconds")
    return number


def parse_tsc(value: str) -> str:
    if not TSC_VALUE.fullmatch(value):
        raise argparse.ArgumentTypeError("--tsc must be 1 to 8 digits")
    return value


def parse_lane(value: str) -> str:
    if not LANE_VALUE.fullmatch(value):
        raise argparse.ArgumentTypeError("--lane must be 1 to 32 letters, digits or hyphens")
    return value


def format_coord(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    if text in {"", "-"}:
        raise SkillError(2, "bounding-box coordinate is not representable")
    return text


def volume_where(tsc: str | None, lane: str | None) -> str | None:
    parts: list[str] = []
    if tsc:
        parts.append(f'tsc="{tsc}"')
    if lane:
        parts.append(f'lane="{lane}"')
    return " and ".join(parts) or None


def signal_where(tsc: str | None, bbox: tuple[float, float, float, float] | None) -> str | None:
    """ODS in_bbox takes latitude then longitude. The CLI bbox is lon,lat order."""
    parts: list[str] = []
    if tsc:
        parts.append(f'tsc="{tsc}"')
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        parts.append(
            "in_bbox(geo_point_2d,"
            f"{format_coord(min_lat)},{format_coord(min_lon)},"
            f"{format_coord(max_lat)},{format_coord(max_lon)})"
        )
    return " and ".join(parts) or None


def check_public_url(url: str, *, redirect: bool) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    message = "redirect to a host outside the allowlist is rejected" if redirect else "request URL is not allowlisted"
    if parsed.username or parsed.password or parsed.scheme != "https" or host != ALLOWED_HOST:
        raise SkillError(4, message)
    allowed = {
        f"/api/explore/v2.1/catalog/datasets/{VOLUME_DATASET}/records",
        f"/api/explore/v2.1/catalog/datasets/{SIGNAL_DATASET}/records",
    }
    if parsed.path not in allowed or "/exports" in parsed.path or parsed.path.endswith("/download"):
        raise SkillError(4, "request path is not an allowlisted records endpoint")


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        check_public_url(newurl, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    value = headers.get(name) if hasattr(headers, "get") else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_fixture(path: str) -> tuple[int, dict[str, str], bytes]:
    if "://" in path:
        raise SkillError(2, "--fixture must be a local file, not a URL")
    fixture = Path(path)
    try:
        raw = fixture.read_bytes()
    except OSError as exc:
        raise SkillError(2, f"--fixture could not be read: {exc.strerror or exc}") from exc
    if len(raw) > MAX_BYTES:
        raise SkillError(6, "truncated fixture exceeds the byte cap")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SkillError(2, f"--fixture is not a JSON object: {exc}") from exc
    if not isinstance(payload, dict):
        raise SkillError(2, "--fixture must be a JSON object")
    status = payload.get("http_status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise SkillError(2, "--fixture http_status must be an integer")
    header_payload = payload.get("headers") or {}
    if not isinstance(header_payload, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in header_payload.items()):
        raise SkillError(2, "--fixture headers must be an object of strings")
    body = payload.get("body")
    if isinstance(body, dict):
        encoded = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        encoded = body.encode("utf-8")
    else:
        raise SkillError(2, "--fixture body must be a string or object")
    return status, {key: value for key, value in header_payload.items()}, encoded


def fetch_bytes(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    check_public_url(url, redirect=False)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(_AllowlistRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            headers = {key: value for key, value in response.headers.items()}
            chunks: list[bytes] = []
            total = 0
            while True:
                block = response.read(8192)
                if not block:
                    break
                total += len(block)
                if total > MAX_BYTES:
                    raise SkillError(6, "truncated JSON response exceeds the byte cap")
                chunks.append(block)
            return status, headers, b"".join(chunks)
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        retry_after = _header(exc.headers, "Retry-After")
        body = exc.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise SkillError(6, "truncated JSON response exceeds the byte cap") from exc
        return int(exc.code), {"Retry-After": retry_after} if retry_after else {}, body
    except TimeoutError as exc:
        raise SkillError(5, "network error: source request timed out") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower():
            raise SkillError(5, "network error: source request timed out") from exc
        raise SkillError(5, f"network error: {reason}") from exc
    except http.client.IncompleteRead as exc:
        raise SkillError(6, "truncated JSON response") from exc
    except OSError as exc:
        raise SkillError(5, f"network error: {exc}") from exc


def decode_payload(status: int, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    retry_after = _header(headers, "Retry-After")
    if status == 429:
        raise SkillError(4, "HTTP 429: rate limited", retry_after=retry_after)
    if status == 400:
        raise SkillError(6, "HTTP 400: source rejected the query")
    if status in {500, 502, 503, 504}:
        raise SkillError(5, f"HTTP {status}: upstream unavailable")
    if status == 403:
        raise SkillError(4, "HTTP 403: access blocked")
    if status != 200:
        raise SkillError(5, f"HTTP {status}: upstream unavailable")
    try:
        text = body.decode("utf-8")
    except UnicodeError as exc:
        raise SkillError(6, "non-JSON response") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillError(6, "non-JSON or truncated JSON response") from exc
    if not isinstance(payload, dict):
        raise SkillError(6, "source response was not a JSON object")
    if "error_code" in payload or "results" not in payload or "total_count" not in payload:
        raise SkillError(6, "source response did not contain total_count and results")
    total = payload["total_count"]
    results = payload["results"]
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise SkillError(6, "source total_count was not a non-negative integer")
    if not isinstance(results, list):
        raise SkillError(6, "source results was not an array")
    if len(results) > total:
        raise SkillError(6, "source returned more rows than total_count")
    return payload


def _require_keys(record: Any, fields: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise SkillError(6, f"{label} record was not an object")
    missing = [field for field in fields if field not in record]
    extra = [field for field in record if field not in fields]
    if missing or extra:
        detail = ", ".join(missing or extra)
        kind = "missing" if missing else "unexpected"
        raise SkillError(6, f"{label} record {kind} fields: {detail}")
    return record


def _text(record: dict[str, Any], field: str, *, nullable: bool) -> None:
    value = record[field]
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise SkillError(6, f"{field} was not a string")


def _integer(record: dict[str, Any], field: str) -> None:
    value = record[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SkillError(6, f"{field} was not an integer")


def _coordinate(value: Any, low: float, high: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SkillError(6, f"{label} was not a finite coordinate")
    number = float(value)
    if not low <= number <= high:
        raise SkillError(6, f"{label} was outside the WGS84 range")
    return number


def parse_recorded(value: str) -> datetime:
    if not isinstance(value, str) or not RECORDED_TIME.fullmatch(value):
        raise SkillError(6, "recorded was not a source timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SkillError(6, "recorded timestamp had no timezone")
    return parsed


def normalise_volume(record: Any) -> dict[str, Any]:
    payload = _require_keys(record, VOLUME_FIELDS, "volume")
    for field in VOLUME_TEXT:
        _text(payload, field, nullable=False)
    for field in VOLUME_NULLABLE_TEXT:
        _text(payload, field, nullable=True)
    _integer(payload, "link_plan")
    parse_recorded(payload["recorded"])
    return {field: payload[field] for field in VOLUME_FIELDS}


def _point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, dict):
        raise SkillError(6, f"{label} was not an object")
    lon = _coordinate(value.get("lon"), -180, 180, f"{label} longitude")
    lat = _coordinate(value.get("lat"), -90, 90, f"{label} latitude")
    return lon, lat


def normalise_signal(record: Any) -> dict[str, Any]:
    payload = _require_keys(record, SIGNAL_FIELDS, "signal")
    for field in SIGNAL_TEXT:
        _text(payload, field, nullable=False)
    _integer(payload, "subsystem")
    lon, lat = _point(payload["geo_point_2d"], "geo_point_2d")
    shape = payload["geo_shape"]
    if not isinstance(shape, dict) or shape.get("type") != "Feature":
        raise SkillError(6, "geo_shape was not a Feature")
    geometry = shape.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise SkillError(6, "geo_shape geometry was not a Point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        raise SkillError(6, "geo_shape coordinates were not a longitude/latitude pair")
    shape_lon = _coordinate(coordinates[0], -180, 180, "geo_shape longitude")
    shape_lat = _coordinate(coordinates[1], -90, 90, "geo_shape latitude")
    if abs(shape_lon - lon) > 1e-5 or abs(shape_lat - lat) > 1e-5:
        raise SkillError(6, "geo_shape and geo_point_2d coordinates disagree")
    return {field: payload[field] for field in SIGNAL_FIELDS}


def parse_records(payload: dict[str, Any], limit: int, normalise: Any) -> tuple[list[dict[str, Any]], int]:
    results = payload["results"]
    total = int(payload["total_count"])
    if len(results) > limit:
        raise SkillError(6, "source returned more rows than the requested limit")
    if total == 0 and results:
        raise SkillError(6, "source reported no rows but returned records")
    if total > 0 and not results:
        raise SkillError(6, "source reported rows but returned none")
    return [normalise(record) for record in results], total


def latest_recorded(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return None
    chosen = max(records, key=lambda record: parse_recorded(record["recorded"]))
    newest = parse_recorded(chosen["recorded"])
    first = parse_recorded(records[0]["recorded"])
    previous = first
    for record in records[1:]:
        current = parse_recorded(record["recorded"])
        if current > previous:
            raise SkillError(6, "volume rows were not in recorded descending order")
        previous = current
    if newest > first:
        raise SkillError(6, "newest recorded timestamp was not the first row")
    return str(chosen["recorded"])


def build_url(dataset: str, limit: int, where: str | None, *, order_by: str | None) -> str:
    params = [("limit", str(limit))]
    if where:
        params.append(("where", where))
    if order_by:
        params.append(("order_by", order_by))
    return dataset_source(dataset) + "?" + urllib.parse.urlencode(params)


def retrieve(url: str, timeout: float, fixture: str | None) -> tuple[int, dict[str, str], bytes]:
    if fixture:
        return load_fixture(fixture)
    status, headers, body = fetch_bytes(url, timeout)
    if len(body) > MAX_BYTES:
        raise SkillError(6, "truncated JSON response exceeds the byte cap")
    return status, headers, body


def wants_machine(args: argparse.Namespace) -> bool:
    return bool(args.json or getattr(args, "format", "json") == "geojson")


def emit_success(args: argparse.Namespace, results: list[dict[str, Any]], meta: dict[str, Any], total_count: int) -> int:
    meta = {**meta, "total_count": total_count}
    if getattr(args, "format", "json") == "geojson":
        features = []
        for record in results:
            point = record["geo_point_2d"]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [point["lon"], point["lat"]],
                    },
                    "properties": {
                        "objectid": record["objectid"],
                        "subsystem": record["subsystem"],
                        "tsc": record["tsc"],
                        "areanum": record["areanum"],
                        "globalid": record["globalid"],
                    },
                }
            )
        print(json.dumps(geojson_envelope(features, meta), indent=2, ensure_ascii=False))
        return 0
    if args.json:
        print(json.dumps(result_envelope(results, meta), indent=2, ensure_ascii=False))
        return 0
    print(f"{PUBLISHER}  {meta['licence']}  returned {len(results)} of {total_count}")
    for record in results:
        if "recorded" in record:
            print(
                f"tsc {record['tsc']}  lane {record['lane']}  recorded {record['recorded']}  "
                f"ds1 {record['ds1'] if record['ds1'] is not None else 'not reported'}  "
                f"mf1 {record['mf1'] if record['mf1'] is not None else 'not reported'}"
            )
        else:
            point = record["geo_point_2d"]
            print(f"tsc {record['tsc']}  area {record['areanum']}  lon {point['lon']}  lat {point['lat']}")
    return 0


def argv_wants_machine(argv: list[str]) -> bool:
    if "--json" in argv:
        return True
    for index, token in enumerate(argv):
        if token == "--format" and index + 1 < len(argv) and argv[index + 1] == "geojson":
            return True
        if token.startswith("--format=geojson"):
            return True
    return False


def dataset_for(argv: list[str], args: argparse.Namespace | None) -> tuple[str, str]:
    command = getattr(args, "command", None) if args is not None else None
    if command == "signals" or "signals" in argv:
        return SIGNAL_DATASET, SIGNAL_LICENCE
    return VOLUME_DATASET, VOLUME_LICENCE


def emit_failure(argv: list[str], args: argparse.Namespace | None, code: int, message: str, *, retry_after: str | None = None) -> int:
    dataset, licence = dataset_for(argv, args)
    machine = argv_wants_machine(argv) or (args is not None and wants_machine(args))
    if machine:
        print(json.dumps(error_envelope(code, message, source_meta(dataset, licence), retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"brisbane-intersection-traffic: {message}", file=sys.stderr)
    return code


def run_volumes(args: argparse.Namespace) -> int:
    where = volume_where(args.tsc, args.lane)
    url = build_url(VOLUME_DATASET, args.limit, where, order_by="recorded desc")
    status, headers, body = retrieve(url, args.timeout, args.fixture)
    payload = decode_payload(status, headers, body)
    records, total = parse_records(payload, args.limit, normalise_volume)
    meta = source_meta(VOLUME_DATASET, VOLUME_LICENCE, latest_data=latest_recorded(records))
    return emit_success(args, records, meta, total)


def run_signals(args: argparse.Namespace) -> int:
    where = signal_where(args.tsc, args.bbox)
    url = build_url(SIGNAL_DATASET, args.limit, where, order_by=None)
    status, headers, body = retrieve(url, args.timeout, args.fixture)
    payload = decode_payload(status, headers, body)
    records, total = parse_records(payload, args.limit, normalise_signal)
    if args.bbox:
        min_lon, min_lat, max_lon, max_lat = args.bbox
        for record in records:
            point = record["geo_point_2d"]
            lon = float(point["lon"])
            lat = float(point["lat"])
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                raise SkillError(6, "signal point fell outside the requested bounding box")
    meta = source_meta(SIGNAL_DATASET, SIGNAL_LICENCE)
    return emit_success(args, records, meta, total)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="brisbane-intersection-traffic", description="Brisbane City Council intersection volumes and signal locations")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)
    volumes = sub.add_parser("volumes", help="lane volume and occupancy at BCC signalised intersections")
    signals = sub.add_parser("signals", help="BCC traffic-signal point locations")
    for command in (volumes, signals):
        command.add_argument("--limit", type=parse_limit, required=True, help=f"rows to return, from 1 to {MAX_LIMIT}")
        command.add_argument("--tsc", type=parse_tsc, help="traffic signal controller site id")
        command.add_argument("--timeout", type=parse_timeout, default=DEFAULT_TIMEOUT, help=f"seconds, from 1 to {MAX_TIMEOUT}")
        command.add_argument("--fixture", help="local response fixture; skips the network")
        command.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    volumes.add_argument("--lane", type=parse_lane, help="strategic approach or lane id")
    add_spatial_arguments(signals)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        if args.command == "volumes":
            return run_volumes(args)
        if args.command == "signals":
            return run_signals(args)
        raise SkillError(7, "unsupported command")
    except InputError as exc:
        return emit_failure(argv, args, 2, str(exc))
    except SkillError as exc:
        return emit_failure(argv, args, exc.code, str(exc), retry_after=exc.retry_after)


if __name__ == "__main__":
    raise SystemExit(main())
