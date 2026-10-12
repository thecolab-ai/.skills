#!/usr/bin/env python3
"""Read AKLOnTrack's public Auckland train observation archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from provenance import error_envelope, provenance, result_envelope

PUBLISHER = "AKLOnTrack"
DOCS_URL = "https://aklontrack.com/data"
INDEX_URL = "https://data.aklontrack.com/open/v1/index.json"
CANONICAL_BASE = "https://data.aklontrack.com/open/v1"
ALLOWED_HOSTS = frozenset({"data.aklontrack.com", "aklontrack.com"})
USER_AGENT = "thecolab-skills-akl-ontrack/1.0 (+https://github.com/thecolab-ai/.skills)"
TIMEOUT_SECONDS = 15
MAX_INDEX_BYTES = 2_000_000
MAX_DAY_BYTES = 1_500_000
MAX_INDEX_DAYS = 800
MAX_PARSED_OBSERVATIONS = 20_000
DEFAULT_DAY_LIMIT = 20
MAX_OUTPUT_LIMIT = 500
MAX_OFFSET = 20_000
AUCKLAND = ZoneInfo("Pacific/Auckland")

TRIP_FIELDS = [
    "trip_id",
    "route_id",
    "direction_id",
    "trip_rel",
    "feed_version",
    "stops",
]
STOP_FIELDS = [
    "stop_sequence",
    "stop",
    "state",
    "stop_rel",
    "arrival_delay",
    "departure_delay",
    "arrival",
    "departure",
]
STATE_LABELS = {
    0: "stopped",
    1: "cancelled",
    2: "skipped",
    3: "no_report",
}
DAY_PATH_RE = re.compile(r"^observations/(\d{4})/(\d{2})/(\d{2})\.json$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
FIXTURE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

Transport = Callable[[str, int], "HttpResult"]


class SkillError(Exception):
    """Typed CLI failure with a stable exit code."""

    def __init__(
        self,
        code: int,
        message: str,
        *,
        retry_after: str | None = None,
        source_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.source_url = source_url


class InputError(SkillError):
    def __init__(self, message: str, *, source_url: str | None = None) -> None:
        super().__init__(2, message, source_url=source_url)


class BlockedError(SkillError):
    def __init__(
        self,
        message: str,
        *,
        retry_after: str | None = None,
        source_url: str | None = None,
    ) -> None:
        super().__init__(4, message, retry_after=retry_after, source_url=source_url)


class UpstreamError(SkillError):
    def __init__(self, message: str, *, source_url: str | None = None) -> None:
        super().__init__(5, message, source_url=source_url)


class SchemaError(SkillError):
    def __init__(self, message: str, *, source_url: str | None = None) -> None:
        super().__init__(6, message, source_url=source_url)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    url: str
    body: bytes


@dataclass(frozen=True)
class DayRef:
    date: str
    path: str
    byte_count: int
    rows: int
    trips: int
    sha256: str
    rev: int
    written_at: str

    def as_record(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "path": self.path,
            "bytes": self.byte_count,
            "rows": self.rows,
            "trips": self.trips,
            "sha256": self.sha256,
            "rev": self.rev,
            "written_at": self.written_at,
        }


@dataclass(frozen=True)
class IndexDocument:
    generated_at: str
    base_url: str
    licence: str
    days: tuple[DayRef, ...]

    @property
    def latest_data(self) -> str | None:
        if not self.days:
            return None
        return max(day.date for day in self.days)


def https_allowlisted(url: str) -> bool:
    """True only for HTTPS on an official host, with no credentials or odd port."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    host = parsed.hostname
    if host not in ALLOWED_HOSTS:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    return port in (None, 443)


class AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    """Follow only a few redirects that stay on the official hosts."""

    max_redirections = 3
    max_repeats = 2

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not https_allowlisted(newurl):
            raise BlockedError("redirect host is outside the allowlist")
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl
        )


def _header_map(headers: Any) -> dict[str, str]:
    mapped: dict[str, str] = {}
    if headers is None:
        return mapped
    for key in headers.keys():
        if key is None:
            continue
        mapped[str(key)] = str(headers.get(key))
    return mapped


def _retry_after(headers: dict[str, str]) -> str | None:
    raw = None
    for key, value in headers.items():
        if key.lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    text = " ".join(str(raw).split())
    if not text:
        return None
    return text[:80]


def status_error(status: int, headers: dict[str, str]) -> SkillError | None:
    """Map an HTTP status to a typed error. 200 is not an error."""
    retry_after = _retry_after(headers)
    if status == 200:
        return None
    if status == 429:
        return BlockedError(
            "network error: HTTP 429",
            retry_after=retry_after,
        )
    if status in {401, 403}:
        return BlockedError(f"network error: HTTP {status}", retry_after=retry_after)
    if status in {300, 301, 302, 303, 307, 308}:
        return BlockedError("redirect host is outside the allowlist")
    if status in {404, 408, 500, 502, 503, 504}:
        return UpstreamError(f"network error: HTTP {status}")
    return UpstreamError(f"network error: HTTP {status}")


def live_get(url: str, limit: int) -> HttpResult:
    """GET one allowlisted HTTPS URL. Proxies are disabled."""
    if not https_allowlisted(url):
        raise BlockedError("request host is outside the allowlist", source_url=INDEX_URL)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        AllowlistRedirect,
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            headers = _header_map(response.headers)
            status = int(response.status)
            if not https_allowlisted(final_url):
                raise BlockedError("redirect host is outside the allowlist")
            declared = headers.get("Content-Length")
            if declared is not None and declared.isdecimal() and int(declared) > limit:
                raise SchemaError(
                    "response exceeded the byte cap",
                    source_url=final_url,
                )
            body = response.read(limit + 1)
    except SkillError:
        raise
    except TimeoutError as exc:
        raise UpstreamError("network error: source request timed out") from exc
    except urllib.error.HTTPError as exc:
        headers = _header_map(exc.headers)
        try:
            exc.read(1024)
        finally:
            exc.close()
        failure = status_error(int(exc.code), headers)
        if failure is None:
            failure = UpstreamError(f"network error: HTTP {exc.code}")
        failure.source_url = url
        raise failure from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason).lower()
        if "timed out" in reason or "timeout" in reason:
            raise UpstreamError("network error: source request timed out") from exc
        raise UpstreamError(f"network error: {exc.reason}") from exc
    if len(body) > limit:
        raise SchemaError("response exceeded the byte cap", source_url=url)
    failure = status_error(status, headers)
    if failure is not None:
        failure.source_url = final_url
        raise failure
    return HttpResult(status=status, headers=headers, url=final_url, body=body)


def parse_json_bytes(body: bytes, *, source_url: str) -> Any:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError("response is not UTF-8 JSON", source_url=source_url) from exc

    def reject_constant(constant: str) -> None:
        raise SchemaError(
            f"non-standard JSON constant: {constant}",
            source_url=source_url,
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except SchemaError:
        raise
    except json.JSONDecodeError as exc:
        raise SchemaError("non-JSON or truncated JSON", source_url=source_url) from exc


def _require_dict(value: Any, label: str, *, source_url: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{label} is not an object", source_url=source_url)
    return value


def _whole(value: Any, label: str, *, source_url: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SchemaError(f"{label} is not a valid integer", source_url=source_url)
    return value


def _optional_whole(value: Any, label: str, *, source_url: str) -> int | None:
    """Keep an omitted or JSON null time field null. Do not coerce it to zero."""
    if value is None:
        return None
    return _whole(value, label, source_url=source_url, minimum=-10**12)


def _text(value: Any, label: str, *, source_url: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SchemaError(f"{label} is missing", source_url=source_url)
    return value


def licence_text(payload: Any, *, source_url: str) -> str:
    """Use the index licence object. Refuse anything other than stated CC BY 4.0."""
    document = _require_dict(payload, "index licence", source_url=source_url)
    name = document.get("name")
    url = document.get("url")
    attribution = document.get("attribution")
    if name != "CC BY 4.0":
        raise BlockedError("source licence is not CC BY 4.0", source_url=source_url)
    if not isinstance(url, str):
        raise BlockedError("source licence URL is missing", source_url=source_url)
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "creativecommons.org"
        or not path.endswith("/licenses/by/4.0")
        or parsed.username
        or parsed.password
    ):
        raise BlockedError(
            "source licence URL is not Creative Commons BY 4.0",
            source_url=source_url,
        )
    if not isinstance(attribution, str) or not attribution.strip():
        raise BlockedError("source licence attribution is missing", source_url=source_url)
    return f"CC BY 4.0 ({url.strip()}); attribution: {attribution.strip()}"


def observation_path(service_date: str) -> str:
    year, month, day = service_date.split("-")
    return f"observations/{year}/{month}/{day}.json"


def parse_service_date(value: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise InputError("date must be YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise InputError("date must be a real calendar day") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise InputError("date must be a real calendar day")
    return value


def _parse_day_ref(raw: Any, *, source_url: str) -> DayRef:
    item = _require_dict(raw, "index day", source_url=source_url)
    try:
        service_date = parse_service_date(_text(item.get("date"), "day date", source_url=source_url))
    except InputError as exc:
        raise SchemaError("index day date is not YYYY-MM-DD", source_url=source_url) from exc
    path = _text(item.get("path"), "day path", source_url=source_url)
    if path != observation_path(service_date) or not DAY_PATH_RE.fullmatch(path):
        raise SchemaError(
            "index day path is not the observation file for that date",
            source_url=source_url,
        )
    byte_count = _whole(item.get("bytes"), "day bytes", source_url=source_url, minimum=1)
    rows = _whole(item.get("rows"), "day rows", source_url=source_url, minimum=0)
    trips = _whole(item.get("trips"), "day trips", source_url=source_url, minimum=0)
    if rows > 0 and byte_count <= 0:
        raise SchemaError("day with rows has no bytes", source_url=source_url)
    digest = _text(item.get("sha256"), "day sha256", source_url=source_url)
    if not SHA256_RE.fullmatch(digest):
        raise SchemaError("day sha256 is not a hex digest", source_url=source_url)
    rev = _whole(item.get("rev"), "day rev", source_url=source_url, minimum=0)
    written_at = _text(item.get("written_at"), "day written_at", source_url=source_url)
    return DayRef(
        date=service_date,
        path=path,
        byte_count=byte_count,
        rows=rows,
        trips=trips,
        sha256=digest,
        rev=rev,
        written_at=written_at,
    )


def canonical_base(value: Any, *, source_url: str) -> str:
    if not isinstance(value, str) or value.rstrip("/") != CANONICAL_BASE:
        raise SchemaError("index base_url is outside the allowlist", source_url=source_url)
    if not https_allowlisted(CANONICAL_BASE + "/"):
        raise SchemaError("index base_url is outside the allowlist", source_url=source_url)
    return CANONICAL_BASE


def parse_index_document(payload: Any, *, source_url: str = INDEX_URL) -> IndexDocument:
    document = _require_dict(payload, "index", source_url=source_url)
    if document.get("v") != 1:
        raise SchemaError("unsupported index version", source_url=source_url)
    generated_at = _text(document.get("generated_at"), "generated_at", source_url=source_url)
    base_url = canonical_base(document.get("base_url"), source_url=source_url)
    licence = licence_text(document.get("licence"), source_url=source_url)
    days_raw = document.get("days")
    if not isinstance(days_raw, list):
        raise SchemaError("index days is not a list", source_url=source_url)
    if len(days_raw) > MAX_INDEX_DAYS:
        raise SchemaError("observation index exceeds the day bound", source_url=source_url)
    days = tuple(_parse_day_ref(item, source_url=source_url) for item in days_raw)
    dates = [day.date for day in days]
    if len(dates) != len(set(dates)):
        raise SchemaError("index lists the same observation date twice", source_url=source_url)
    ordered = tuple(sorted(days, key=lambda day: day.date, reverse=True))
    return IndexDocument(
        generated_at=generated_at,
        base_url=base_url,
        licence=licence,
        days=ordered,
    )


def auckland_midnight_unix(service_date: str) -> int:
    local = datetime.fromisoformat(service_date + "T00:00:00").replace(tzinfo=AUCKLAND)
    return int(local.timestamp())


def local_timestamp(t0: int, seconds: int) -> str:
    moment = datetime.fromtimestamp(t0 + seconds, timezone.utc).astimezone(AUCKLAND)
    return moment.isoformat(timespec="seconds")


def _field_names(payload: Any, key: str, expected: list[str], *, source_url: str) -> None:
    fields = _require_dict(payload, "fields", source_url=source_url)
    names = fields.get(key)
    if names != expected:
        raise SchemaError(f"day {key} columns changed", source_url=source_url)


def parse_day_document(
    payload: Any,
    *,
    expected_date: str,
    source_url: str,
) -> list[dict[str, Any]]:
    """Flatten stop rows. Missing feed values stay missing; nothing is filled in."""
    document = _require_dict(payload, "day file", source_url=source_url)
    if document.get("v") != 1:
        raise SchemaError("unsupported day file version", source_url=source_url)
    service_date = _text(document.get("service_date"), "service_date", source_url=source_url)
    try:
        service_date = parse_service_date(service_date)
    except InputError as exc:
        raise SchemaError("service_date is not YYYY-MM-DD", source_url=source_url) from exc
    if service_date != expected_date:
        raise SchemaError("day file service_date does not match the requested date", source_url=source_url)
    t0 = _whole(document.get("t0"), "t0", source_url=source_url, minimum=0)
    if t0 != auckland_midnight_unix(service_date):
        raise SchemaError(
            "t0 is not Auckland midnight at the start of service_date",
            source_url=source_url,
        )
    _field_names(document.get("fields"), "trip", TRIP_FIELDS, source_url=source_url)
    _field_names(document.get("fields"), "stop", STOP_FIELDS, source_url=source_url)
    feed_versions = document.get("feed_versions")
    if not isinstance(feed_versions, list) or not all(
        isinstance(item, str) and item.strip() for item in feed_versions
    ):
        raise SchemaError("feed_versions is not a list of version strings", source_url=source_url)
    stops = document.get("stops")
    if not isinstance(stops, list) or not all(isinstance(item, str) and item.strip() for item in stops):
        raise SchemaError("stops is not a list of station ids", source_url=source_url)
    trips = document.get("trips")
    if not isinstance(trips, list):
        raise SchemaError("trips is not a list", source_url=source_url)
    records: list[dict[str, Any]] = []
    for trip in trips:
        if not isinstance(trip, list) or len(trip) != len(TRIP_FIELDS):
            raise SchemaError("trip row does not match the published columns", source_url=source_url)
        trip_id, route_id, direction_id, trip_rel, feed_index, stop_rows = trip
        if not isinstance(trip_id, str) or not isinstance(route_id, str):
            raise SchemaError("trip identifiers are not strings", source_url=source_url)
        direction_id = _whole(direction_id, "direction_id", source_url=source_url, minimum=0)
        trip_rel = _whole(trip_rel, "trip_rel", source_url=source_url, minimum=0)
        feed_index = _whole(feed_index, "feed_version", source_url=source_url, minimum=0)
        if feed_index >= len(feed_versions):
            raise SchemaError("feed_version index is outside feed_versions", source_url=source_url)
        if not isinstance(stop_rows, list):
            raise SchemaError("trip stops are not a list", source_url=source_url)
        for stop in stop_rows:
            if len(records) >= MAX_PARSED_OBSERVATIONS:
                raise SchemaError("day file exceeds the observation bound", source_url=source_url)
            if not isinstance(stop, list) or not 4 <= len(stop) <= len(STOP_FIELDS):
                raise SchemaError("stop row does not match the published columns", source_url=source_url)
            padded = list(stop) + [None] * (len(STOP_FIELDS) - len(stop))
            sequence, stop_index, state, stop_rel, arrival_delay, departure_delay, arrival, departure = padded
            sequence = _whole(sequence, "stop_sequence", source_url=source_url, minimum=0)
            stop_index = _whole(stop_index, "stop", source_url=source_url, minimum=0)
            state = _whole(state, "state", source_url=source_url, minimum=0)
            stop_rel = _whole(stop_rel, "stop_rel", source_url=source_url, minimum=0)
            arrival_delay = _optional_whole(arrival_delay, "arrival_delay", source_url=source_url)
            departure_delay = _optional_whole(departure_delay, "departure_delay", source_url=source_url)
            arrival = _optional_whole(arrival, "arrival", source_url=source_url)
            departure = _optional_whole(departure, "departure", source_url=source_url)
            if stop_index >= len(stops):
                raise SchemaError("stop index is outside the day station list", source_url=source_url)
            records.append(
                {
                    "service_date": service_date,
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "direction_id": direction_id,
                    "trip_rel": trip_rel,
                    "feed_version_index": feed_index,
                    "feed_version": feed_versions[feed_index],
                    "stop_sequence": sequence,
                    "stop_index": stop_index,
                    "stop_id": stops[stop_index],
                    "state": state,
                    "state_label": STATE_LABELS.get(state),
                    "stop_rel": stop_rel,
                    "arrival_delay": arrival_delay,
                    "departure_delay": departure_delay,
                    "arrival": arrival,
                    "departure": departure,
                    "arrival_time": None if arrival is None else local_timestamp(t0, arrival),
                    "departure_time": None if departure is None else local_timestamp(t0, departure),
                }
            )
    return records


def fixture_bytes(name: str) -> bytes:
    if not isinstance(name, str) or FIXTURE_NAME_RE.fullmatch(name) is None:
        raise InputError("fixture name is not a bundled test file")
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    path = root / name
    if path.parent != root or not path.is_file():
        raise InputError("fixture name is not a bundled test file")
    data = path.read_bytes()
    if len(data) > MAX_INDEX_BYTES:
        raise SchemaError("fixture exceeds the byte cap")
    return data


def load_index(transport: Transport, *, fixture: str | None) -> tuple[IndexDocument, str]:
    if fixture:
        body = fixture_bytes(fixture)
        source_url = INDEX_URL
    else:
        result = transport(INDEX_URL, MAX_INDEX_BYTES)
        body = result.body
        source_url = result.url
    document = parse_index_document(parse_json_bytes(body, source_url=source_url), source_url=source_url)
    return document, source_url


def select_latest(index: IndexDocument) -> DayRef:
    candidates = [
        day
        for day in index.days
        if day.rows > 0 and 0 < day.byte_count <= MAX_DAY_BYTES
    ]
    if not candidates:
        raise SchemaError(
            "index lists no observation day with rows",
            source_url=INDEX_URL,
        )
    return max(candidates, key=lambda day: day.date)


def day_file_url(index: IndexDocument, day: DayRef) -> str:
    url = index.base_url + "/" + day.path
    if not https_allowlisted(url) or not url.startswith(CANONICAL_BASE + "/observations/"):
        raise SchemaError("observation URL is outside the allowlist", source_url=INDEX_URL)
    return url


def load_day(
    index: IndexDocument,
    day: DayRef,
    transport: Transport,
    *,
    fixture: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    source_url = day_file_url(index, day)
    if day.byte_count > MAX_DAY_BYTES:
        raise SchemaError("observation file exceeds the byte cap", source_url=source_url)
    if fixture:
        body = fixture_bytes(fixture)
    else:
        result = transport(source_url, MAX_DAY_BYTES)
        body = result.body
        source_url = result.url
    if len(body) != day.byte_count or hashlib.sha256(body).hexdigest().lower() != day.sha256.lower():
        raise SchemaError(
            "day file bytes or sha256 do not match the index",
            source_url=source_url,
        )
    records = parse_day_document(
        parse_json_bytes(body, source_url=source_url),
        expected_date=day.date,
        source_url=source_url,
    )
    if len(records) != day.rows:
        raise SchemaError(
            "day file stop count does not match the index row count",
            source_url=source_url,
        )
    return source_url, records


def window(records: list[dict[str, Any]], *, offset: int, limit: int | None) -> list[dict[str, Any]]:
    if offset > len(records):
        return []
    if limit is None:
        return records[offset:]
    return records[offset : offset + limit]


def source_meta(source_url: str, licence: str | None, latest_data: str | None) -> dict[str, str]:
    return provenance(source_url, PUBLISHER, licence=licence, latest_data=latest_data)


def emit_success(
    records: list[dict[str, Any]],
    meta: dict[str, str],
    *,
    json_output: bool,
    human: Callable[[], None],
) -> int:
    if json_output:
        print(json.dumps(result_envelope(records, meta), indent=2, ensure_ascii=False))
    else:
        human()
    return 0


def emit_error(exc: SkillError, argv: list[str], *, source_url: str | None = None) -> None:
    url = exc.source_url or source_url or INDEX_URL
    meta = provenance(url, PUBLISHER)
    if "--json" in argv:
        print(
            json.dumps(
                error_envelope(exc.code, str(exc), meta, retry_after=exc.retry_after),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    print(f"akl-ontrack: {exc}", file=sys.stderr)


def output_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("--limit must be a whole number from 1 to 500")
    number = int(value)
    if number < 1 or number > MAX_OUTPUT_LIMIT:
        raise argparse.ArgumentTypeError("--limit must be a whole number from 1 to 500")
    return number


def output_offset(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("--offset must be a whole number from 0 to 20000")
    number = int(value)
    if number > MAX_OFFSET:
        raise argparse.ArgumentTypeError("--offset must be a whole number from 0 to 20000")
    return number


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="AKLOnTrack Auckland train observation archive")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="list observation dates, byte sizes and row counts")
    index.add_argument("--limit", type=output_limit, help="return at most this many dates (newest first)")
    index.add_argument("--fixture", help="read a bundled tests/fixtures JSON file instead of the network")
    index.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    day = sub.add_parser("day", help="fetch one observation day named by the index")
    day.add_argument("date", nargs="?", help="service date YYYY-MM-DD")
    day.add_argument(
        "--latest",
        action="store_true",
        help="use the newest index day that has rows, instead of a date",
    )
    day.add_argument("--limit", type=output_limit, default=DEFAULT_DAY_LIMIT, help="maximum stop observations to return")
    day.add_argument("--offset", type=output_offset, default=0, help="skip this many stop observations")
    day.add_argument("--fixture", help="read a bundled day fixture; requires --index-fixture for a live-shaped check")
    day.add_argument("--index-fixture", help="read a bundled index fixture instead of the network")
    day.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def find_day(index: IndexDocument, service_date: str) -> DayRef:
    for day in index.days:
        if day.date == service_date:
            return day
    raise InputError(
        "date is not listed in the observation index",
        source_url=INDEX_URL,
    )


def run_index(args: argparse.Namespace, transport: Transport) -> int:
    index, source_url = load_index(transport, fixture=args.fixture)
    selected = list(index.days)
    if args.limit is not None:
        selected = selected[: args.limit]
    records = [day.as_record() for day in selected]
    meta = source_meta(source_url, index.licence, index.latest_data)

    def human() -> None:
        print(f"AKLOnTrack observation index ({index.licence})")
        if index.latest_data:
            print(f"Newest observation date: {index.latest_data}")
        print(f"Showing {len(records)} of {len(index.days)} dates")
        for record in records:
            print(
                f"{record['date']}  rows={record['rows']}  bytes={record['bytes']}  "
                f"trips={record['trips']}"
            )

    return emit_success(records, meta, json_output=args.json, human=human)


def run_day(args: argparse.Namespace, transport: Transport) -> int:
    if bool(args.date) == bool(args.latest):
        raise InputError("provide one YYYY-MM-DD date or --latest")
    if args.fixture and not args.index_fixture:
        raise InputError("day --fixture requires --index-fixture")
    if args.date:
        parse_service_date(args.date)
    index, _index_url = load_index(transport, fixture=args.index_fixture)
    if args.latest:
        chosen = select_latest(index)
    else:
        chosen = find_day(index, args.date)
    source_url, records = load_day(index, chosen, transport, fixture=args.fixture)
    shown = window(records, offset=args.offset, limit=args.limit)
    meta = source_meta(source_url, index.licence, chosen.date)

    def human() -> None:
        print(f"{chosen.date} stop observations ({index.licence})")
        print(
            "Delays are seconds late (negative means early). "
            "arrival and departure are seconds from Auckland midnight."
        )
        print(f"Showing {len(shown)} of {len(records)} stop observations")
        for record in shown:
            label = record["state_label"] or f"state {record['state']}"
            delay = record["departure_delay"]
            delay_text = "not reported" if delay is None else f"{delay}s"
            when = record["departure_time"] or "not reported"
            print(
                f"{record['route_id']} {record['trip_id']} seq {record['stop_sequence']} "
                f"stop {record['stop_id']} {label} "
                f"departure_delay={delay_text} at {when}"
            )

    return emit_success(shown, meta, json_output=args.json, human=human)


def execute(argv: list[str], transport: Transport | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = transport or live_get
    if args.command == "index":
        return run_index(args, client)
    if args.command == "day":
        return run_day(args, client)
    raise InputError("unsupported command")


def main(argv: list[str] | None = None) -> int:
    chosen = list(sys.argv[1:] if argv is None else argv)
    try:
        return execute(chosen)
    except SkillError as exc:
        emit_error(exc, chosen)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
