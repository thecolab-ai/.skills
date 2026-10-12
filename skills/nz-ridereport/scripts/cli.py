#!/usr/bin/env python3
"""Keyless Auckland Ride Report aggregate micromobility metrics."""
from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from provenance import error_envelope, provenance, result_envelope

PAGE_HOST = "public.ridereport.com"
API_HOST = "api.ridereport.com"
EXPORT_HOST = "public-data-exports-production.s3-us-west-2.amazonaws.com"
ALLOWED_HOSTS = frozenset({PAGE_HOST, API_HOST, EXPORT_HOST})
PAGE_URL = "https://public.ridereport.com/auckland"
SETTINGS_URL = "https://api.ridereport.com/public/settings?slug=auckland&environment=production"
PUBLISHER = "Ride Report"
LICENCE = (
    "Data may be used with a link to public.ridereport.com and attribution to Ride Report."
)
USER_AGENT = "TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills)"
TIMEOUT_SECONDS = 10
MAX_PAGE_BYTES = 262144
MAX_SETTINGS_BYTES = 65536
MAX_METRICS_BYTES = 1048576
MAX_SERIES_LIMIT = 92
DEFAULT_SERIES_LIMIT = 31
MAX_JSON_DEPTH = 12
MAX_REDIRECTS = 2
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,40}$")
FIXTURE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")
DATE_TOKEN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RETRY_AFTER = re.compile(r"^[0-9]{1,6}$")
NEXT_DATA_START = '<script id="__NEXT_DATA__" type="application/json">'
SERIES_FIELDS = {
    "trips": "tripsPerDay",
    "duration": "tripDuration",
    "distance": "tripDistancePerDay",
    "vehicles": "meanActiveVehiclesPerDay",
    "utilisation": "tripsPerVehiclePerDay",
}
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
ACTIVE_FIXTURE: dict[str, Any] | None = None


class InputError(ValueError):
    """Caller input that must be a JSON invalid_input error, not a traceback."""


class BlockedError(Exception):
    def __init__(self, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamError(Exception):
    pass


class SchemaError(Exception):
    pass


class UnsafeError(Exception):
    pass


class MissingExport(Exception):
    """S3 returns 403 or 404 when a public export object is absent."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def source_meta(url: str, *, latest_data: str | None = None) -> dict[str, str]:
    return provenance(url, PUBLISHER, licence=LICENCE, latest_data=latest_data)


def json_requested(argv: list[str] | None) -> bool:
    source = sys.argv[1:] if argv is None else argv
    return "--json" in source


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 92")
    number = int(value)
    if not 1 <= number <= MAX_SERIES_LIMIT:
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 92")
    return number


def validate_outbound_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or host not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
        or any(part == ".." for part in parsed.path.split("/"))
    ):
        raise UnsafeError("refusing a request outside the Ride Report allowlist")
    if host == PAGE_HOST:
        if parsed.path != "/auckland" or parsed.query:
            raise UnsafeError("refusing a dashboard URL other than /auckland")
    elif host == API_HOST:
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path != "/public/settings" or query.get("slug") != ["auckland"] or query.get("environment") != ["production"]:
            raise UnsafeError("refusing a settings URL other than the Auckland production read")
    elif host == EXPORT_HOST:
        parts = [part for part in parsed.path.split("/") if part]
        if (
            len(parts) != 5
            or parts[0] != "auckland"
            or parts[1] != "data-export"
            or parts[4] != "trip_metrics.json"
            or not TOKEN.fullmatch(parts[2])
            or not TOKEN.fullmatch(parts[3])
            or parsed.query
        ):
            raise UnsafeError("refusing an export outside Auckland trip_metrics.json")


def metrics_url(vehicle: str, period: str) -> str:
    if not TOKEN.fullmatch(vehicle) or not TOKEN.fullmatch(period):
        raise InputError("vehicle and period must be single published catalogue tokens")
    return f"https://{EXPORT_HOST}/auckland/data-export/{vehicle}/{period}/trip_metrics.json"


class _PinnedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.hops = 0

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> urllib.request.Request | None:
        self.hops += 1
        if self.hops > MAX_REDIRECTS:
            raise UnsafeError("refusing more than two redirects")
        validate_outbound_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def decode_body(raw: bytes, content_encoding: str, max_bytes: int) -> bytes:
    encoding = (content_encoding or "").lower()
    if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
                decoded = handle.read(max_bytes + 1)
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise SchemaError("compressed response could not be read") from exc
    else:
        decoded = raw
    if len(decoded) > max_bytes:
        raise UpstreamError("response exceeded the size cap")
    return decoded


def _fixture_bytes(url: str, max_bytes: int) -> tuple[int, bytes, str]:
    if ACTIVE_FIXTURE is None:
        raise UnsafeError("fixture transport was not loaded")
    validate_outbound_url(url)
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host == PAGE_HOST:
        page = ACTIVE_FIXTURE.get("page_html")
        if not isinstance(page, str):
            raise SchemaError("fixture page_html was not a string")
        body = page.encode("utf-8")
    elif host == API_HOST:
        settings = ACTIVE_FIXTURE.get("settings")
        if not isinstance(settings, dict):
            raise SchemaError("fixture settings was not an object")
        body = json.dumps(settings).encode("utf-8")
    elif host == EXPORT_HOST:
        redirect_url = ACTIVE_FIXTURE.get("redirect_url")
        if isinstance(redirect_url, str):
            validate_outbound_url(redirect_url)
        status = ACTIVE_FIXTURE.get("metrics_status", 200)
        if status == "timeout":
            raise UpstreamError("network error: source request timed out")
        if status in (403, 404):
            raise MissingExport(f"HTTP {status}")
        if status == 429:
            retry = ACTIVE_FIXTURE.get("retry_after")
            retry_after = retry if isinstance(retry, str) and RETRY_AFTER.fullmatch(retry) else None
            raise BlockedError("network error: rate_limited", retry_after=retry_after)
        if isinstance(status, int) and status >= 500:
            raise UpstreamError(f"network error: HTTP {status}")
        if status != 200:
            raise UpstreamError(f"network error: HTTP {status}")
        raw = ACTIVE_FIXTURE.get("metrics_raw")
        if isinstance(raw, str):
            body = raw.encode("utf-8")
        else:
            metrics = ACTIVE_FIXTURE.get("metrics")
            if not isinstance(metrics, dict):
                raise SchemaError("fixture metrics was not an object")
            body = json.dumps(metrics).encode("utf-8")
    else:
        raise UnsafeError("refusing a request outside the Ride Report allowlist")
    if len(body) > max_bytes:
        raise UpstreamError("response exceeded the size cap")
    return 200, body, url


def fetch_bytes(url: str, *, timeout: int, max_bytes: int, absent_is_missing: bool = False) -> tuple[int, bytes, str]:
    validate_outbound_url(url)
    if ACTIVE_FIXTURE is not None:
        return _fixture_bytes(url, max_bytes)
    if timeout != TIMEOUT_SECONDS:
        raise InputError("timeout must stay at the 10 second command bound")
    opener = urllib.request.build_opener(_PinnedRedirects())
    request = urllib.request.Request(url, headers={"Accept": "application/json,text/html;q=0.9", "User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            validate_outbound_url(final_url)
            encoded = response.read(max_bytes + 1)
            encoding = response.headers.get("Content-Encoding") or ""
            status = getattr(response, "status", 200)
    except MissingExport:
        raise
    except UnsafeError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404) and absent_is_missing:
            raise MissingExport(f"HTTP {exc.code}") from exc
        if exc.code == 429:
            header = exc.headers.get("Retry-After") if exc.headers is not None else None
            retry_after = header.strip() if isinstance(header, str) and RETRY_AFTER.fullmatch(header.strip()) else None
            raise BlockedError("network error: rate_limited", retry_after=retry_after) from exc
        if exc.code in (403, 406, 451):
            raise BlockedError(f"network error: HTTP {exc.code}") from exc
        raise UpstreamError(f"network error: HTTP {exc.code}") from exc
    except TimeoutError as exc:
        raise UpstreamError("network error: source request timed out") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (UnsafeError, SchemaError, UpstreamError, BlockedError)):
            raise reason from exc
        text = str(reason)
        if "timed out" in text.lower():
            raise UpstreamError("network error: source request timed out") from exc
        raise UpstreamError(f"network error: {text}") from exc
    body = decode_body(encoded, encoding, max_bytes)
    return status, body, final_url


def json_nesting_depth(text: str) -> int:
    depth = 0
    maximum = 0
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            maximum = max(maximum, depth)
            if maximum > MAX_JSON_DEPTH:
                return maximum
        elif char in "}]":
            depth = max(0, depth - 1)
    return maximum


def parse_json_bytes(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise SchemaError("upstream JSON was not UTF-8") from exc
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (RecursionError, ValueError) as exc:
        raise SchemaError("upstream returned malformed JSON") from exc


def load_fixture(name: str) -> dict[str, Any]:
    if not FIXTURE_NAME.fullmatch(name):
        raise InputError("fixture name is not a catalogue fixture")
    path = (FIXTURES / f"{name}.json").resolve()
    if path.parent != FIXTURES.resolve() or not path.is_file():
        raise InputError("fixture name is not a catalogue fixture")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError("fixture JSON could not be read") from exc
    if not isinstance(payload, dict):
        raise SchemaError("fixture JSON was not an object")
    return payload


def finite_number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
        raise SchemaError(f"{name} was not a finite number")
    return value


def optional_number(payload: dict[str, Any], key: str, name: str) -> int | float | None:
    if key not in payload or payload[key] is None:
        return None
    return finite_number(payload[key], name)


def parse_catalogue(page_html: str) -> dict[str, list[dict[str, str]]]:
    start = page_html.find(NEXT_DATA_START)
    if start < 0:
        raise SchemaError("dashboard page did not contain its published catalogue")
    start += len(NEXT_DATA_START)
    end = page_html.find("</script>", start)
    if end < 0:
        raise SchemaError("dashboard page catalogue was truncated")
    payload = parse_json_bytes(page_html[start:end].encode("utf-8"))
    if not isinstance(payload, dict):
        raise SchemaError("dashboard catalogue was not an object")
    page_props = payload.get("props", {})
    if not isinstance(page_props, dict):
        raise SchemaError("dashboard catalogue props were not an object")
    page_props = page_props.get("pageProps", {})
    if not isinstance(page_props, dict):
        raise SchemaError("dashboard catalogue pageProps were not an object")
    periods = page_props.get("timePeriodsAvailableByVehicleClass")
    if not isinstance(periods, dict) or not periods:
        raise SchemaError("dashboard catalogue did not list vehicle periods")
    catalogue: dict[str, list[dict[str, str]]] = {}
    for vehicle, items in periods.items():
        if not isinstance(vehicle, str) or not TOKEN.fullmatch(vehicle):
            raise SchemaError("dashboard catalogue contained an unsafe vehicle token")
        if not isinstance(items, list) or not items or len(items) > 40:
            raise SchemaError("dashboard catalogue period list was empty or too long")
        parsed_items: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                raise SchemaError("dashboard catalogue period was not an object")
            key = item.get("key")
            label = item.get("name")
            if not isinstance(key, str) or not TOKEN.fullmatch(key) or key in seen:
                raise SchemaError("dashboard catalogue period key was not usable")
            if not isinstance(label, str) or not label.strip() or len(label) > 40:
                raise SchemaError("dashboard catalogue period name was not usable")
            seen.add(key)
            parsed_items.append({"key": key, "name": label.strip()})
        catalogue[vehicle] = parsed_items
    return catalogue


def parse_settings(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchemaError("settings response was not an object")
    name = payload.get("name")
    population = payload.get("population")
    operators = payload.get("currently_active_operators")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise SchemaError("settings name was not usable")
    if isinstance(population, bool) or not isinstance(population, int) or not 0 < population <= 20000000:
        raise SchemaError("settings population was not a positive integer")
    if not isinstance(operators, list) or not 0 < len(operators) <= 12:
        raise SchemaError("settings operators were not a short list")
    if not all(isinstance(item, str) and item.strip() and len(item) <= 80 for item in operators):
        raise SchemaError("settings operator name was not usable")
    record: dict[str, Any] = {
        "slug": "auckland",
        "name": name.strip(),
        "population": population,
        "operators": [item.strip() for item in operators],
        "dashboard_url": PAGE_URL,
        "settings_url": SETTINGS_URL,
    }
    measurement = payload.get("measurement_system")
    if isinstance(measurement, str) and measurement in {"metric", "imperial"}:
        record["measurement_system"] = measurement
    earliest = payload.get("earliest_available_metrics")
    if isinstance(earliest, str) and DATE_TOKEN.fullmatch(earliest):
        record["earliest_available_metrics"] = earliest
    bounds = payload.get("max_bounds")
    if isinstance(bounds, list) and len(bounds) == 4:
        numbers = [finite_number(item, "max_bounds") for item in bounds]
        min_lon, min_lat, max_lon, max_lat = numbers
        if -180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90:
            record["max_bounds"] = [min_lon, min_lat, max_lon, max_lat]
    return record


def nested_stat(payload: dict[str, Any], series_key: str, stat: str) -> int | float | None:
    block = payload.get(series_key)
    if not isinstance(block, dict) or stat not in block or block[stat] is None:
        return None
    return finite_number(block[stat], f"{series_key}.{stat}")


def last_observation_day(payload: dict[str, Any]) -> str | None:
    block = payload.get("tripsPerDay")
    if not isinstance(block, dict):
        return None
    buckets = block.get("dataBuckets")
    if not isinstance(buckets, list) or not buckets:
        return None
    last = buckets[-1]
    if not isinstance(last, dict):
        return None
    value = last.get("xValue")
    if isinstance(value, str) and DATE_TOKEN.fullmatch(value):
        return value
    return None


def parse_series(payload: dict[str, Any], series_name: str, limit: int) -> tuple[list[dict[str, Any]], bool]:
    field = SERIES_FIELDS[series_name]
    block = payload.get(field)
    if not isinstance(block, dict):
        raise SchemaError(f"{field} was not an object")
    buckets = block.get("dataBuckets")
    if not isinstance(buckets, list):
        raise SchemaError(f"{field}.dataBuckets was not a list")
    x_unit = block.get("xUnit")
    y_unit = block.get("yUnit")
    if x_unit is not None and (not isinstance(x_unit, str) or len(x_unit) > 40):
        raise SchemaError(f"{field}.xUnit was not usable")
    if y_unit is not None and (not isinstance(y_unit, str) or len(y_unit) > 40):
        raise SchemaError(f"{field}.yUnit was not usable")
    points: list[dict[str, Any]] = []
    for bucket in buckets[:limit]:
        if not isinstance(bucket, dict):
            raise SchemaError(f"{field} bucket was not an object")
        x_value = bucket.get("xValue")
        y_value = bucket.get("yValue")
        if not isinstance(x_value, str) or not x_value.strip() or len(x_value) > 40:
            raise SchemaError(f"{field} bucket label was not usable")
        point: dict[str, Any] = {"x": x_value, "y": finite_number(y_value, f"{field}.yValue")}
        if isinstance(x_unit, str):
            point["x_unit"] = x_unit
        if isinstance(y_unit, str):
            point["y_unit"] = y_unit
        if "percentageOfTotal" in bucket and bucket["percentageOfTotal"] is not None:
            point["percentage_of_total"] = finite_number(bucket["percentageOfTotal"], f"{field}.percentageOfTotal")
        points.append(point)
    return points, len(buckets) > limit


def parse_metrics(payload: Any, *, vehicle: str, period: str, label: str, series_name: str | None, limit: int) -> tuple[dict[str, Any], list[str], str | None]:
    if not isinstance(payload, dict):
        raise SchemaError("metrics response was not an object")
    total = payload.get("totalTripCount")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise SchemaError("totalTripCount was not a non-negative integer")
    average_trips = finite_number(payload.get("averageTripsPerDay"), "averageTripsPerDay")
    speed = finite_number(payload.get("averageTripSpeedMetersPerSecond"), "averageTripSpeedMetersPerSecond")
    if speed < 0:
        raise SchemaError("averageTripSpeedMetersPerSecond was negative")
    record: dict[str, Any] = {
        "slug": "auckland",
        "vehicle": vehicle,
        "period": period,
        "period_label": label,
        "total_trip_count": total,
        "average_trips_per_day": average_trips,
        "average_trip_speed_metres_per_second": speed,
        "dashboard_url": PAGE_URL,
    }
    optional = {
        "mean_trip_duration_minutes": nested_stat(payload, "tripDuration", "average"),
        "median_trip_duration_minutes": nested_stat(payload, "tripDuration", "median"),
        "mean_distance_kilometres_per_day": nested_stat(payload, "tripDistancePerDay", "average"),
        "total_distance_kilometres": nested_stat(payload, "tripDistancePerDay", "sumTotal"),
        "mean_active_vehicles_per_day": nested_stat(payload, "meanActiveVehiclesPerDay", "average"),
        "mean_trips_per_vehicle_per_day": nested_stat(payload, "tripsPerVehiclePerDay", "average"),
    }
    warnings: list[str] = []
    for key, value in optional.items():
        if value is not None:
            record[key] = value
    if series_name:
        points, truncated = parse_series(payload, series_name, limit)
        record["series_name"] = series_name
        record["series"] = points
        if truncated:
            warnings.append(f"series truncated to {limit} source-order buckets")
    return record, warnings, last_observation_day(payload)


def fetch_catalogue() -> dict[str, list[dict[str, str]]]:
    _status, body, _final = fetch_bytes(PAGE_URL, timeout=TIMEOUT_SECONDS, max_bytes=MAX_PAGE_BYTES)
    try:
        page = body.decode("utf-8")
    except UnicodeError as exc:
        raise SchemaError("dashboard page was not UTF-8") from exc
    return parse_catalogue(page)


def command_dashboard() -> dict[str, Any]:
    catalogue = fetch_catalogue()
    _status, body, _final = fetch_bytes(SETTINGS_URL, timeout=TIMEOUT_SECONDS, max_bytes=MAX_SETTINGS_BYTES)
    record = parse_settings(parse_json_bytes(body))
    record["vehicles"] = [
        {"vehicle": vehicle, "periods": items}
        for vehicle, items in catalogue.items()
    ]
    return result_envelope([record], source_meta(PAGE_URL))


def command_metrics(vehicle: str, period: str, series_name: str | None, limit: int | None) -> dict[str, Any]:
    if limit is not None and series_name is None:
        raise InputError("--limit applies only with --series")
    url = metrics_url(vehicle, period)
    catalogue = fetch_catalogue()
    items = catalogue.get(vehicle)
    if items is None:
        raise InputError(f"vehicle {vehicle} is not in the published Auckland catalogue")
    match = next((item for item in items if item["key"] == period), None)
    if match is None:
        raise InputError(f"period {period} is not published for vehicle {vehicle}")
    try:
        _status, body, final_url = fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            max_bytes=MAX_METRICS_BYTES,
            absent_is_missing=True,
        )
    except MissingExport:
        envelope = result_envelope([], source_meta(url))
        envelope["warnings"] = ["no_export: no public aggregate export for this vehicle and period"]
        return envelope
    record, warnings, latest = parse_metrics(
        parse_json_bytes(body),
        vehicle=vehicle,
        period=period,
        label=match["name"],
        series_name=series_name,
        limit=limit if limit is not None else DEFAULT_SERIES_LIMIT,
    )
    if final_url != url:
        raise UnsafeError("export URL changed during retrieval")
    envelope = result_envelope([record], source_meta(url, latest_data=latest))
    if warnings:
        envelope["warnings"] = warnings
    return envelope


def human_number(value: int | float) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.2f}"


def render_dashboard(payload: dict[str, Any]) -> str:
    record = payload["results"][0]
    lines = [
        record["name"],
        f"Population: {human_number(record['population'])}",
        "Operators: " + ", ".join(record["operators"]),
        "Publisher: Ride Report",
        f"Licence: {LICENCE}",
        f"Dashboard: {PAGE_URL}",
    ]
    if record.get("earliest_available_metrics"):
        lines.append(f"Earliest metrics day: {record['earliest_available_metrics']}")
    for vehicle in record["vehicles"]:
        periods = vehicle["periods"]
        preview = ", ".join(item["key"] for item in periods[:4])
        if len(periods) > 4:
            preview += f", … ({len(periods)} periods)"
        lines.append(f"{vehicle['vehicle']}: {preview}")
    return "\n".join(lines)


def render_metrics(payload: dict[str, Any]) -> str:
    if not payload["results"]:
        return "\n".join(
            [
                "No public aggregate export for this Auckland vehicle and period.",
                "Publisher: Ride Report",
                f"Licence: {LICENCE}",
                f"Dashboard: {PAGE_URL}",
            ]
        )
    record = payload["results"][0]
    lines = [
        f"Auckland {record['vehicle']} {record['period_label']}",
        f"Total trips: {human_number(record['total_trip_count'])}",
        f"Average trips per day: {human_number(record['average_trips_per_day'])}",
        f"Average trip speed: {human_number(record['average_trip_speed_metres_per_second'])} metres per second",
    ]
    labelled = (
        ("mean_trip_duration_minutes", "Mean trip duration (minutes)"),
        ("median_trip_duration_minutes", "Median trip duration (minutes)"),
        ("mean_distance_kilometres_per_day", "Mean distance per day (kilometres)"),
        ("total_distance_kilometres", "Total distance (kilometres)"),
        ("mean_active_vehicles_per_day", "Mean active vehicles per day"),
        ("mean_trips_per_vehicle_per_day", "Mean trips per vehicle per day"),
    )
    for key, label in labelled:
        if key in record:
            lines.append(f"{label}: {human_number(record[key])}")
    if "series" in record:
        lines.append(f"Series {record['series_name']}: {len(record['series'])} buckets")
    for warning in payload.get("warnings", []):
        lines.append(f"Warning: {warning}")
    lines.extend(
        [
            "Publisher: Ride Report",
            f"Licence: {LICENCE}",
            f"Dashboard: {PAGE_URL}",
        ]
    )
    return "\n".join(lines)


def emit(payload: dict[str, Any], *, as_json: bool, human: str, failed: bool = False) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        sys.stdout.write("\n")
        return
    print(human, file=sys.stderr if failed else sys.stdout)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Read Auckland Ride Report public aggregate micromobility metrics")
    commands = parser.add_subparsers(dest="command", required=True)
    dashboard = commands.add_parser("dashboard", help="show the published Auckland catalogue and agency summary")
    dashboard.add_argument("--json", action="store_true", help="emit the provenance JSON envelope")
    dashboard.add_argument("--fixture", help=argparse.SUPPRESS)
    metrics = commands.add_parser("metrics", help="read one published aggregate trip-metrics export")
    metrics.add_argument("--vehicle", required=True, help="published vehicle token, such as scooter")
    metrics.add_argument("--period", required=True, help="published period token, such as 2026-Q3 or all")
    metrics.add_argument("--series", choices=tuple(SERIES_FIELDS), help="include one bounded source-order series")
    metrics.add_argument("--limit", type=parse_limit, help="series buckets to keep, from 1 to 92; default 31")
    metrics.add_argument("--json", action="store_true", help="emit the provenance JSON envelope")
    metrics.add_argument("--fixture", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    global ACTIVE_FIXTURE
    as_json = json_requested(argv)
    meta = source_meta(PAGE_URL)
    try:
        args = build_parser().parse_args(argv)
        ACTIVE_FIXTURE = load_fixture(args.fixture) if args.fixture else None
        if args.command == "dashboard":
            payload = command_dashboard()
            human = render_dashboard(payload)
        else:
            payload = command_metrics(args.vehicle, args.period, args.series, args.limit)
            human = render_metrics(payload)
            meta = payload["meta"]
        emit(payload, as_json=as_json, human=human)
        return 0
    except InputError as exc:
        payload = error_envelope(2, str(exc), meta)
        emit(payload, as_json=as_json, human=f"Invalid input: {exc}", failed=True)
        return 2
    except BlockedError as exc:
        payload = error_envelope(4, str(exc), meta, retry_after=exc.retry_after)
        emit(payload, as_json=as_json, human=f"Blocked: {exc}", failed=True)
        return 4
    except (UpstreamError, MissingExport) as exc:
        payload = error_envelope(5, str(exc), meta)
        emit(payload, as_json=as_json, human=f"Upstream unavailable: {exc}", failed=True)
        return 5
    except SchemaError as exc:
        payload = error_envelope(6, str(exc), meta)
        emit(payload, as_json=as_json, human=f"Schema failure: {exc}", failed=True)
        return 6
    except UnsafeError as exc:
        payload = error_envelope(7, str(exc), meta)
        emit(payload, as_json=as_json, human=f"Unsupported operation: {exc}", failed=True)
        return 7
    finally:
        ACTIVE_FIXTURE = None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
