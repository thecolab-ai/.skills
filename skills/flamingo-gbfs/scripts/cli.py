#!/usr/bin/env python3
"""Read Flamingo's public Auckland GBFS 3.0 discovery, system, and current vehicles."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

from provenance import (  # noqa: E402
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    provenance,
    result_envelope,
)

HOST = "data.rideflamingo.com"
ORIGIN = f"https://{HOST}"
GBFS_URL = f"{ORIGIN}/gbfs/3/auckland/gbfs.json"
SYSTEM_URL = f"{ORIGIN}/gbfs/3/auckland/system_information.json"
VEHICLE_URL = f"{ORIGIN}/gbfs/3/auckland/vehicle_status.json"
PUBLISHER = "Flamingo"
USER_AGENT = "TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills)"
ALLOWED_HOSTS = frozenset({HOST})
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2_000_000
MAX_JSON_DEPTH = 8
MAX_FEEDS = 30
MAX_VEHICLES = 5000
MAX_LIMIT = 100
DEFAULT_LIMIT = 20
MAX_RANGE_METERS = 1_000_000
AUCKLAND_PREFIX = "/gbfs/3/auckland/"
CACHE_DIR = pathlib.Path(tempfile.gettempdir()) / "thecolab-flamingo-gbfs-cache"
FIXTURE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,48}")
FEED_NAME_RE = re.compile(r"[a-z0-9_]{1,64}")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")
STAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
LICENCE_TEXT = {"CC-BY-4.0": "CC BY 4.0"}
TRAJECTORY_KEYS = ("route", "path", "trip", "trajectory", "history", "trace", "polyline")


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


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_meta(
    url: str,
    *,
    licence: str | None = None,
    latest_data: str | None = None,
    retrieved_at: str | None = None,
) -> dict[str, str]:
    return provenance(
        url,
        PUBLISHER,
        licence=licence,
        latest_data=latest_data,
        retrieved_at=retrieved_at,
    )


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def parse_vehicle_id(value: str) -> str:
    text = value.strip()
    if not TOKEN_RE.fullmatch(text):
        raise InputError("vehicle id must be 1 to 80 letters, digits, hyphens or underscores")
    return text


def machine_readable(argv: list[str]) -> bool:
    return "--json" in argv or "geojson" in argv


def assert_allowed_url(url: str) -> None:
    if not auckland_feed_url(url):
        raise UnsafeError("refusing a request outside https://data.rideflamingo.com/gbfs/3/auckland/")


def auckland_feed_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path or ""
    return (
        parsed.scheme == "https"
        and host == HOST
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
        and not parsed.query
        and not parsed.fragment
        and path.startswith(AUCKLAND_PREFIX)
        and ".." not in path
        and path.endswith(".json")
    )


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


def _reject_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant {value}")


def parse_json_document(text: str) -> Any:
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError("upstream JSON exceeds the supported nesting depth") from exc
    except ValueError as exc:
        raise SchemaError("upstream returned malformed JSON") from exc


def as_ttl(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 86400:
        raise SchemaError("ttl must be an integer from 0 to 86400 seconds")
    return value


def as_stamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not STAMP_RE.fullmatch(value):
        raise SchemaError("last_updated must be a timezone-aware GBFS timestamp when present")
    return value


def gbfs_document(payload: Any) -> tuple[dict[str, Any], int, str | None]:
    if not isinstance(payload, dict):
        raise SchemaError("GBFS response was not a JSON object")
    if payload.get("version") != "3.0":
        raise SchemaError("GBFS version must be 3.0; this skill does not read other versions")
    ttl = as_ttl(payload.get("ttl"))
    latest = as_stamp(payload.get("last_updated")) if "last_updated" in payload else None
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SchemaError("GBFS data was not an object")
    return data, ttl, latest


def licence_text(license_id: str) -> str:
    return LICENCE_TEXT.get(license_id, license_id)


def cache_path(url: str) -> pathlib.Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def read_cache(url: str) -> tuple[str, str] | None:
    path = cache_path(url)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("url") != url:
        return None
    ttl = payload.get("ttl_seconds")
    retrieved = payload.get("retrieved_at")
    body = payload.get("body")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
        return None
    if not isinstance(retrieved, str) or not isinstance(body, str) or not STAMP_RE.fullmatch(retrieved):
        return None
    stamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    if age < 0 or age >= ttl:
        return None
    return body, retrieved


def store_cache(url: str, body: str, retrieved_at: str, ttl: int) -> None:
    if ttl <= 0:
        cache_path(url).unlink(missing_ok=True)
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = cache_path(url)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"url": url, "retrieved_at": retrieved_at, "ttl_seconds": ttl, "body": body},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)


def remember(url: str, body: str, retrieved_at: str, ttl: int, cached_at: str | None) -> None:
    if cached_at is not None:
        return
    store_cache(url, body, retrieved_at, ttl)


def _read_http_error(exc: Any) -> tuple[int, str]:
    try:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
    except OSError:
        raw = b""
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpstreamError("upstream response exceeds the safety cap")
    return exc.code, raw.decode("utf-8", "replace")


def retrieve(url: str) -> tuple[int, str, str | None]:
    assert_allowed_url(url)
    cached = read_cache(url)
    if cached is not None:
        return 200, cached[0], cached[1]
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            accept="application/json",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            browser_headers=False,
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_RESPONSE_BYTES,
            expect_json=True,
        )
    except nzfetch.RateLimited as exc:
        retry = exc.retry_after if isinstance(exc.retry_after, str) else None
        raise BlockedError(
            f"network error: rate_limited: retry_after={retry}: HTTP 429",
            retry_after=retry,
        ) from exc
    except nzfetch.Blocked as exc:
        raise BlockedError("network error: upstream access blocked") from exc
    except nzfetch.ResponseTooLarge as exc:
        raise UpstreamError("upstream response exceeds the safety cap") from exc
    except nzfetch.FetchError as exc:
        message = str(exc)
        if "allowlist" in message or "downgrade" in message:
            raise UnsafeError(
                "refusing off-host redirect; requests stay on data.rideflamingo.com"
            ) from exc
        cause = exc.__cause__
        if isinstance(cause, TimeoutError) or "timed out" in message.lower():
            raise UpstreamError("network error: source request timed out") from exc
        http_error = cause if hasattr(cause, "code") else None
        if http_error is not None and getattr(http_error, "code", None) == 429:
            retry_after = None
            headers = getattr(http_error, "headers", None)
            if headers is not None:
                raw_retry = headers.get("Retry-After")
                retry_after = raw_retry if isinstance(raw_retry, str) else None
            raise BlockedError(
                f"network error: rate_limited: retry_after={retry_after}: HTTP 429",
                retry_after=retry_after,
            ) from exc
        if http_error is not None and getattr(http_error, "code", None) in {500, 502, 503, 504}:
            raise UpstreamError(f"upstream unavailable (HTTP {http_error.code})") from exc
        raise UpstreamError("upstream unavailable: network error") from exc
    assert_allowed_url(final_url)
    if len(body) > MAX_RESPONSE_BYTES:
        raise UpstreamError("upstream response exceeds the safety cap")
    return 200, body.decode("utf-8"), None


def fixture_file(name: str) -> pathlib.Path:
    if not FIXTURE_RE.fullmatch(name):
        raise InputError("fixture name is not allowed")
    root = (pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures").resolve()
    path = (root / f"{name}.json").resolve()
    if path.parent != root or not path.is_file():
        raise InputError("fixture is not available")
    return path


def load_fixture(name: str) -> tuple[int, str]:
    try:
        payload = json.loads(fixture_file(name).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError("fixture JSON is malformed") from exc
    if not isinstance(payload, dict):
        raise InputError("fixture is not a response fixture")
    transport = payload.get("transport")
    if transport == "rate_limited":
        retry_after = payload.get("retry_after")
        retry_text = retry_after if isinstance(retry_after, str) else None
        raise BlockedError(
            f"network error: rate_limited: retry_after={retry_text}: HTTP 429",
            retry_after=retry_text,
        )
    if transport == "unavailable":
        status = payload.get("status")
        code = status if isinstance(status, int) and not isinstance(status, bool) else 503
        raise UpstreamError(f"upstream unavailable (HTTP {code})")
    if transport == "timeout":
        raise UpstreamError("network error: source request timed out")
    if transport == "off_host_redirect":
        raise UnsafeError("refusing off-host redirect; requests stay on data.rideflamingo.com")
    if "body_raw" in payload:
        body = payload.get("body_raw")
        status = payload.get("http_status", 200)
        if not isinstance(body, str) or isinstance(status, bool) or not isinstance(status, int):
            raise InputError("fixture is not a response fixture")
        return status, body
    if "body" in payload:
        status = payload.get("http_status", 200)
        if isinstance(status, bool) or not isinstance(status, int):
            raise InputError("fixture is not a response fixture")
        return status, json.dumps(payload["body"])
    raise InputError("fixture is not a response fixture")


def response_for(url: str, fixture: str | None) -> tuple[int, str, str | None]:
    assert_allowed_url(url)
    if fixture:
        status, body = load_fixture(fixture)
        return status, body, None
    return retrieve(url)


def guarded_payload(status: int, body: str) -> Any:
    if status == 429:
        raise BlockedError("network error: rate_limited: retry_after=None: HTTP 429")
    if status in {401, 403}:
        raise BlockedError(f"network error: upstream access blocked (HTTP {status})")
    if status >= 500 or status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    return parse_json_document(body)


def optional_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit or any(char in text for char in "\r\n"):
        return None
    return text


def localized_name(value: Any) -> str:
    if isinstance(value, str):
        text = optional_text(value, 120)
        if text:
            return text
    if isinstance(value, list):
        english = None
        fallback = None
        for item in value:
            if not isinstance(item, dict):
                continue
            text = optional_text(item.get("text"), 120)
            if not text:
                continue
            if item.get("language") == "en" and english is None:
                english = text
            elif fallback is None:
                fallback = text
        if english or fallback:
            return english or fallback or ""
    raise SchemaError("system name was missing")


def parse_feeds(data: dict[str, Any], ttl: int, latest: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    feeds = data.get("feeds")
    if not isinstance(feeds, list):
        raise SchemaError("feeds was not a list")
    if len(feeds) > MAX_FEEDS:
        raise SchemaError(f"feed list exceeds the {MAX_FEEDS} feed bound")
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in feeds:
        if not isinstance(item, dict):
            raise SchemaError("feed entry was not an object")
        name = item.get("name")
        url = item.get("url")
        if not isinstance(name, str) or not FEED_NAME_RE.fullmatch(name):
            warnings.append("suppressed a feed whose name was not a GBFS token")
            continue
        if not isinstance(url, str) or not auckland_feed_url(url):
            warnings.append(f"refused feed {name}: off-host or outside the Auckland GBFS path")
            continue
        record: dict[str, Any] = {
            "name": name,
            "url": url,
            "gbfs_version": "3.0",
            "ttl_seconds": ttl,
        }
        if latest:
            record["feed_last_updated"] = latest
        records.append(record)
    records.sort(key=lambda record: record["name"])
    return records, warnings


def parse_system(data: dict[str, Any], ttl: int) -> tuple[dict[str, Any], list[str], str]:
    license_id = data.get("license_id")
    if not isinstance(license_id, str) or not license_id.strip():
        raise SchemaError("license_id was missing; the reuse terms are not stated")
    license_id = license_id.strip()
    if len(license_id) > 80:
        raise SchemaError("license_id was not a short token")
    system_id = data.get("system_id")
    if not isinstance(system_id, str) or not TOKEN_RE.fullmatch(system_id):
        raise SchemaError("system_id was missing")
    record: dict[str, Any] = {
        "system_id": system_id,
        "name": localized_name(data.get("name")),
        "license_id": license_id,
        "ttl_seconds": ttl,
    }
    warnings: list[str] = []
    languages = data.get("languages")
    if isinstance(languages, list) and all(isinstance(item, str) and TOKEN_RE.fullmatch(item) for item in languages):
        record["languages"] = languages[:8]
    timezone_name = optional_text(data.get("timezone"), 64)
    if timezone_name:
        record["timezone"] = timezone_name
    else:
        warnings.append("timezone was not stated; no local zone was assumed")
    opening = optional_text(data.get("opening_hours"), 80)
    if opening:
        record["opening_hours"] = opening
    operator_url = optional_text(data.get("url"), 200)
    if operator_url and operator_url.startswith("https://"):
        record["operator_url"] = operator_url
    if license_id != "CC-BY-4.0":
        warnings.append(f"source license_id is {license_id}; it was not relabelled as CC-BY-4.0")
    return record, warnings, licence_text(license_id)


def _vehicle_record(item: dict[str, Any], ttl: int, warnings: list[str]) -> dict[str, Any] | None:
    vehicle_id = item.get("vehicle_id")
    if not isinstance(vehicle_id, str) or not TOKEN_RE.fullmatch(vehicle_id):
        warnings.append("suppressed a vehicle with a missing or unsafe vehicle_id")
        return None
    lat = item.get("lat")
    lon = item.get("lon")
    if (
        isinstance(lat, bool)
        or isinstance(lon, bool)
        or not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
        or not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180)
    ):
        warnings.append(f"suppressed vehicle {vehicle_id}: coordinates missing or outside WGS84")
        return None
    record: dict[str, Any] = {
        "vehicle_id": vehicle_id,
        "lat": lat,
        "lon": lon,
        "ttl_seconds": ttl,
    }
    for key in ("is_reserved", "is_disabled"):
        value = item.get(key)
        if isinstance(value, bool):
            record[key] = value
        elif key in item:
            warnings.append(f"suppressed {key} for vehicle {vehicle_id}: value was not a boolean")
    range_meters = item.get("current_range_meters")
    if range_meters is not None:
        if (
            isinstance(range_meters, bool)
            or not isinstance(range_meters, int)
            or not 0 <= range_meters <= MAX_RANGE_METERS
        ):
            warnings.append(
                f"suppressed current_range_meters for vehicle {vehicle_id}: value was not metres in range"
            )
        else:
            record["current_range_meters"] = range_meters
    for key in ("vehicle_type_id", "pricing_plan_id"):
        value = item.get(key)
        if isinstance(value, str) and TOKEN_RE.fullmatch(value):
            record[key] = value
        elif key in item and value not in (None, ""):
            warnings.append(f"suppressed {key} for vehicle {vehicle_id}")
    reported = item.get("last_reported")
    if isinstance(reported, str) and STAMP_RE.fullmatch(reported):
        record["last_reported"] = reported
    elif reported not in (None, ""):
        warnings.append(
            f"suppressed last_reported for vehicle {vehicle_id}: timestamp had no timezone"
        )
    return record


def parse_vehicles(
    data: dict[str, Any],
    ttl: int,
    *,
    limit: int,
    bbox: tuple[float, float, float, float] | None,
    vehicle_id: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    raw = data.get("vehicles")
    if not isinstance(raw, list):
        raise SchemaError("vehicles was not a list")
    if len(raw) > MAX_VEHICLES:
        raise SchemaError(f"vehicle_status exceeds the {MAX_VEHICLES} vehicle bound")
    warnings: list[str] = []
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    duplicates = 0
    for item in raw:
        if not isinstance(item, dict):
            raise SchemaError("vehicle entry was not an object")
        record = _vehicle_record(item, ttl, warnings)
        if record is None:
            continue
        if record["vehicle_id"] in seen:
            duplicates += 1
            continue
        seen.add(record["vehicle_id"])
        valid.append(record)
    if duplicates:
        warnings.append(f"suppressed {duplicates} duplicate vehicle_id")
    if raw and not valid:
        raise SchemaError("vehicle_status contained no usable current positions")
    matched = valid
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        matched = [
            record
            for record in matched
            if min_lon <= float(record["lon"]) <= max_lon and min_lat <= float(record["lat"]) <= max_lat
        ]
    if vehicle_id is not None:
        matched = [record for record in matched if record["vehicle_id"] == vehicle_id]
    matched.sort(key=lambda record: record["vehicle_id"])
    shown = matched[:limit]
    warnings.append(f"source vehicle_count: {len(valid)}")
    warnings.append(f"matched vehicle_count: {len(matched)}")
    warnings.append(f"showing {len(shown)} of {len(matched)}")
    if ttl == 0:
        warnings.append(
            "feed ttl_seconds: 0; the provider marks this snapshot as already due for refresh. "
            "This command performs one GET and does not poll"
        )
    else:
        warnings.append(
            f"feed ttl_seconds: {ttl}; do not request this feed again until the ttl has elapsed"
        )
    warnings.append("positions are the current vehicle_status snapshot; this command does not return trajectories")
    return shown, warnings


def ttl_note(ttl: int) -> str:
    if ttl == 0:
        return "feed ttl_seconds: 0; one GET only, no poll"
    return f"feed ttl_seconds: {ttl}; do not request this feed again until the ttl has elapsed"


def emit_success(
    results: list[dict[str, Any]],
    meta: dict[str, str],
    lines: list[str],
    *,
    as_json: bool,
    as_geojson: bool,
    warnings: list[str],
) -> int:
    if as_geojson:
        features = []
        for record in results:
            properties = {key: value for key, value in record.items() if key not in {"lat", "lon"}}
            features.append(
                {
                    "type": "Feature",
                    "id": record["vehicle_id"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [record["lon"], record["lat"]],
                    },
                    "properties": properties,
                }
            )
        payload = geojson_envelope(features, meta)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif as_json:
        payload = result_envelope(results, meta)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)
    return 0


def emit_error(
    code: int,
    message: str,
    meta: dict[str, str],
    argv: list[str],
    *,
    retry_after: str | None = None,
) -> int:
    if machine_readable(argv):
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"flamingo-gbfs: {message}", file=sys.stderr)
    return code


def finish(
    url: str,
    fixture: str | None,
    body: str,
    cached_at: str | None,
    ttl: int,
) -> str:
    retrieved = cached_at or utc_now()
    if fixture is None:
        remember(url, body, retrieved, ttl, cached_at)
    return retrieved


def with_fixture(warnings: list[str], fixture: str | None, cached_at: str | None) -> list[str]:
    notes = list(warnings)
    if fixture:
        notes.insert(0, f"fixture: {fixture}; not a live Flamingo response")
    elif cached_at:
        notes.append("cached within feed ttl; not a new retrieval")
    return notes


def run_discovery(args: argparse.Namespace) -> int:
    url = GBFS_URL
    status, body, cached_at = response_for(url, args.fixture)
    payload = guarded_payload(status, body)
    data, ttl, latest = gbfs_document(payload)
    records, warnings = parse_feeds(data, ttl, latest)
    retrieved = finish(url, args.fixture, body, cached_at, ttl)
    warnings = with_fixture([*warnings, ttl_note(ttl), "gbfs version: 3.0"], args.fixture, cached_at)
    lines = [f"Flamingo Auckland GBFS discovery ({len(records)} feeds)"]
    if not records:
        lines.append("No Auckland feeds were listed.")
    for record in records:
        lines.append(f"- {record['name']} {record['url']}")
    for warning in warnings:
        if warning.startswith("refused") or warning.startswith("suppressed") or warning.startswith("fixture"):
            lines.append(warning)
    lines.append(ttl_note(ttl))
    if latest:
        lines.append(f"Discovery file last_updated: {latest}")
    lines.append(f"Source: {url}")
    lines.append(f"Publisher: {PUBLISHER}")
    return emit_success(
        records,
        source_meta(url, latest_data=latest, retrieved_at=retrieved),
        lines,
        as_json=args.json,
        as_geojson=False,
        warnings=warnings,
    )


def run_system(args: argparse.Namespace) -> int:
    url = SYSTEM_URL
    status, body, cached_at = response_for(url, args.fixture)
    payload = guarded_payload(status, body)
    data, ttl, latest = gbfs_document(payload)
    record, warnings, licence = parse_system(data, ttl)
    retrieved = finish(url, args.fixture, body, cached_at, ttl)
    warnings = with_fixture([*warnings, ttl_note(ttl)], args.fixture, cached_at)
    lines = [
        f"{record['name']} ({record['system_id']})",
        f"Licence: {licence} (license_id {record['license_id']})",
    ]
    if record.get("timezone"):
        lines.append(f"Timezone: {record['timezone']}")
    if record.get("opening_hours"):
        lines.append(f"Opening hours: {record['opening_hours']}")
    if record.get("operator_url"):
        lines.append(f"Operator URL (not fetched): {record['operator_url']}")
    lines.append(ttl_note(ttl))
    if latest:
        lines.append(f"System file last_updated: {latest}")
    lines.append(f"Source: {url}")
    lines.append(f"Publisher: {PUBLISHER}")
    return emit_success(
        [record],
        source_meta(url, licence=licence, latest_data=latest, retrieved_at=retrieved),
        lines,
        as_json=args.json,
        as_geojson=False,
        warnings=warnings,
    )


def run_vehicles(args: argparse.Namespace) -> int:
    vehicle_id = parse_vehicle_id(args.vehicle_id) if args.vehicle_id else None
    url = VEHICLE_URL
    status, body, cached_at = response_for(url, args.fixture)
    payload = guarded_payload(status, body)
    data, ttl, latest = gbfs_document(payload)
    records, warnings = parse_vehicles(
        data,
        ttl,
        limit=args.limit,
        bbox=args.bbox,
        vehicle_id=vehicle_id,
    )
    retrieved = finish(url, args.fixture, body, cached_at, ttl)
    warnings = with_fixture(warnings, args.fixture, cached_at)
    lines = [f"Flamingo current vehicles: showing {len(records)}"]
    lines.append("Snapshot only. Not a trajectory. Positions are WGS84. Range is metres.")
    if not records:
        lines.append("No current vehicles matched.")
    for record in records:
        range_text = (
            f"{record['current_range_meters']} metres"
            if "current_range_meters" in record
            else "range not stated"
        )
        lines.append(f"- {record['vehicle_id']} {record['lat']}, {record['lon']} {range_text}")
    for warning in warnings:
        if warning.startswith("suppressed") or warning.startswith("fixture") or warning.startswith("feed ttl"):
            lines.append(warning)
    if latest:
        lines.append(f"Vehicle file last_updated: {latest}")
    lines.append(f"Source: {url}")
    lines.append(f"Publisher: {PUBLISHER}")
    lines.append("Reuse terms are license_id on system_information; this file does not repeat them.")
    return emit_success(
        records,
        source_meta(url, latest_data=latest, retrieved_at=retrieved),
        lines,
        as_json=args.json and args.format != "geojson",
        as_geojson=args.format == "geojson",
        warnings=warnings,
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Read Flamingo Auckland GBFS current public data")
    sub = parser.add_subparsers(dest="command", required=True)
    discovery = sub.add_parser("discovery", help="list Auckland GBFS 3.0 feeds from gbfs.json")
    discovery.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    discovery.add_argument("--fixture", help="named fixture under tests/fixtures; not a live read")
    system = sub.add_parser("system", help="read system_information including license_id")
    system.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    system.add_argument("--fixture", help="named fixture under tests/fixtures; not a live read")
    vehicles = sub.add_parser("vehicles", help="read current vehicle_status positions only")
    vehicles.add_argument("--limit", type=parse_limit, default=DEFAULT_LIMIT, help=f"rows to show, 1 to {MAX_LIMIT}")
    vehicles.add_argument("--vehicle-id", help="keep one vehicle id from the current snapshot")
    add_spatial_arguments(vehicles)
    vehicles.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    vehicles.add_argument("--fixture", help="named fixture under tests/fixtures; not a live read")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "discovery":
            return run_discovery(args)
        if args.command == "system":
            return run_system(args)
        if args.command == "vehicles":
            return run_vehicles(args)
        raise InputError(f"unsupported command: {args.command}")
    except InputError as exc:
        return emit_error(2, str(exc), source_meta(GBFS_URL), argv)
    except BlockedError as exc:
        return emit_error(4, str(exc), source_meta(GBFS_URL), argv, retry_after=exc.retry_after)
    except UpstreamError as exc:
        return emit_error(5, str(exc), source_meta(GBFS_URL), argv)
    except SchemaError as exc:
        return emit_error(6, str(exc), source_meta(GBFS_URL), argv)
    except UnsafeError as exc:
        return emit_error(7, str(exc), source_meta(GBFS_URL), argv)


if __name__ == "__main__":
    raise SystemExit(main())
