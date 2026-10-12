#!/usr/bin/env python3
"""Keyless reader for US FTA National Transit Database safety resources.

This is United States federal transit data from data.transportation.gov.
It is not an Auckland or New Zealand feed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from fields import DENIED_FIELDS, EVENT_UNITS, EVENTS_FIELDS, MODE_UNITS, MODES_FIELDS
from provenance import error_envelope, provenance, result_envelope

HOST = "data.transportation.gov"
PUBLISHER = "Federal Transit Administration"
ROOT_URL = "https://data.transportation.gov/"
USER_AGENT = (
    "thecolab-us-ntd-safety/1.0 "
    "(public NTD safety skill; +https://github.com/thecolab-ai/.skills)"
)
TIMEOUT_SECONDS = 15
MAX_BYTES = 1_500_000
MAX_LIMIT = 100
DEFAULT_LIMIT = 20
MAX_CODED_TEXT = 160
MAX_RETRY_AFTER = 80
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
INTEGER_TEXT = re.compile(r"-?\d+")
DECIMAL_TEXT = re.compile(r"-?\d+\.\d+")
FIXTURE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

RESOURCES: dict[str, dict[str, Any]] = {
    "events": {
        "id": "9ivb-8ae9",
        "licence_id": "USGOV_WORKS",
        "fields": EVENTS_FIELDS,
        "units": EVENT_UNITS,
        "order": "incident_date DESC, incident_number DESC",
        "time_note": (
            "incident_date and incident_time are source strings with no timezone. "
            "They are not Auckland times and are not converted to UTC."
        ),
        "measure_note": (
            "property_damage is the source estimated dollar value where reported. "
            "Absent measures are omitted and are not zeroes."
        ),
    },
    "modes": {
        "id": "5ti2-5uiv",
        "licence_id": "PUBLIC_DOMAIN",
        "fields": MODES_FIELDS,
        "units": MODE_UNITS,
        "order": "year DESC, month_year DESC",
        "time_note": (
            "month is the source English month name and month_year is the source "
            "calendar_date string. Neither is an Auckland date."
        ),
        "measure_note": (
            "Vehicle revenue miles, hours and ridership are calendar-year values "
            "and are year-to-date when that year is incomplete. Null service values "
            "can mean late reporting. Absent measures are omitted and are not zeroes."
        ),
    },
}


class SkillError(Exception):
    """A typed command failure with a stable exit code."""

    def __init__(
        self,
        code: int,
        message: str,
        *,
        retry_after: str | None = None,
        source_url: str | None = None,
        licence: str | None = None,
        latest_data: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.source_url = source_url
        self.licence = licence
        self.latest_data = latest_data


class InputError(SkillError):
    """An argparse failure emitted as invalid_input."""

    def __init__(self, message: str) -> None:
        super().__init__(2, message, source_url=ROOT_URL)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


@dataclass(frozen=True)
class Query:
    limit: int
    year: int | None
    month: str | None
    mode: str | None
    ntd_id: str | None


def field_types(resource: str) -> dict[str, str]:
    return dict(RESOURCES[resource]["fields"])


def assert_official_url(url: str) -> None:
    """Accept only HTTPS on the official host, with no userinfo or odd port."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        host = parsed.hostname or ""
        if host and host != HOST:
            raise SkillError(4, f"redirect to a host outside the allowlist: {host}", source_url=ROOT_URL)
        raise SkillError(4, "refusing a URL outside the official host", source_url=ROOT_URL)


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        assert_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    AllowlistRedirectHandler,
)


def limit_type(value: str) -> int:
    if not re.fullmatch(r"[1-9]\d*", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if number > MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def year_type(value: str) -> int:
    if not re.fullmatch(r"(?:19|20)\d{2}", value):
        raise argparse.ArgumentTypeError("--year must be a four-digit year from 1900 to 2099")
    return int(value)


def mode_type(value: str) -> str:
    if not re.fullmatch(r"[A-Z]{1,4}", value):
        raise argparse.ArgumentTypeError("--mode must be a 1 to 4 letter NTD mode code")
    return value


def ntd_type(value: str) -> str:
    if not re.fullmatch(r"\d{5}", value):
        raise argparse.ArgumentTypeError("--ntd-id must be a five-digit NTD id")
    return value


def month_type(value: str) -> str:
    if value not in MONTHS:
        raise argparse.ArgumentTypeError("--month must be an English month name, such as January")
    return value


def soql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def view_url(resource: str) -> str:
    return f"https://{HOST}/api/views/{RESOURCES[resource]['id']}.json"


def where_clause(query: Query) -> str:
    parts: list[str] = []
    if query.year is not None:
        parts.append(f"year={query.year}")
    if query.month is not None:
        parts.append("month=" + soql_string(query.month))
    if query.mode is not None:
        parts.append("mode=" + soql_string(query.mode))
    if query.ntd_id is not None:
        parts.append("_5_digit_ntd_id=" + soql_string(query.ntd_id))
    return " AND ".join(parts)


def rows_url(resource: str, query: Query) -> str:
    names = [name for name, _dtype in RESOURCES[resource]["fields"]]
    if DENIED_FIELDS.intersection(names):
        raise SkillError(7, "refusing to select a withheld field", source_url=view_url(resource))
    params = [
        ("$select", ",".join(names)),
        ("$limit", str(query.limit)),
        ("$order", RESOURCES[resource]["order"]),
    ]
    where = where_clause(query)
    if where:
        params.append(("$where", where))
    url = f"https://{HOST}/resource/{RESOURCES[resource]['id']}.json?{urlencode(params)}"
    assert_official_url(url)
    return url


def clean_retry_after(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if not text or len(text) > MAX_RETRY_AFTER:
        return None
    return text


def read_bounded(response: Any) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = response.read(65536)
        if not block:
            break
        total += len(block)
        if total > MAX_BYTES:
            raise SkillError(6, "non-JSON or truncated JSON", source_url=response.geturl())
        chunks.append(block)
    return b"".join(chunks)


def drain(response: Any) -> None:
    total = 0
    while total <= MAX_BYTES:
        block = response.read(65536)
        if not block:
            break
        total += len(block)
    response.close()


def fetch_exchange(url: str) -> dict[str, Any]:
    """GET one official JSON document. The caller supplies the URL."""
    assert_official_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            assert_official_url(final_url)
            status = int(getattr(response, "status", 200))
            retry_after = clean_retry_after(response.headers.get("Retry-After"))
            body = read_bounded(response)
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        retry_after = clean_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
        drain(exc)
        return {"status": int(exc.code), "retry_after": retry_after, "body_raw": ""}
    except TimeoutError as exc:
        raise SkillError(5, "network error: source request timed out", source_url=url) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise SkillError(5, "network error: source request timed out", source_url=url) from exc
        raise SkillError(5, "network error: upstream unavailable", source_url=url) from exc
    except OSError as exc:
        raise SkillError(5, "network error: upstream unavailable", source_url=url) from exc
    try:
        text = body.decode("utf-8")
    except UnicodeError as exc:
        raise SkillError(6, "non-JSON or truncated JSON", source_url=url) from exc
    if text.lstrip().startswith("<"):
        return {"status": status, "retry_after": retry_after, "body_raw": text}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"status": status, "retry_after": retry_after, "body_raw": text}
    return {"status": status, "retry_after": retry_after, "body": parsed}


def read_exchange(exchange: Any, label: str, source_url: str) -> Any:
    if not isinstance(exchange, dict):
        raise SkillError(6, f"{label} is not an HTTP exchange", source_url=source_url)
    status = exchange.get("status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise SkillError(6, f"{label} has no HTTP status", source_url=source_url)
    retry_after = clean_retry_after(exchange.get("retry_after"))
    if status == 429:
        raise SkillError(
            4,
            f"network error: HTTP 429 from {label}",
            retry_after=retry_after,
            source_url=source_url,
        )
    if status == 503:
        raise SkillError(5, f"network error: HTTP 503 from {label}", source_url=source_url)
    if status != 200:
        raise SkillError(5, f"network error: HTTP {status} from {label}", source_url=source_url)
    if "body_raw" in exchange:
        raw = exchange["body_raw"]
        if not isinstance(raw, str):
            raise SkillError(6, f"{label} is not JSON text", source_url=source_url)
        if raw.lstrip().startswith("<"):
            raise SkillError(5, f"network error: non-JSON response for {label}", source_url=source_url)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SkillError(6, f"non-JSON or truncated JSON in {label}", source_url=source_url) from exc
    if "body" not in exchange:
        raise SkillError(6, f"{label} has no body", source_url=source_url)
    return exchange["body"]


def rows_updated_at(value: Any, source_url: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SkillError(6, "rowsUpdatedAt is not an integer epoch", source_url=source_url)
    if value < 0 or value > 4_000_000_000:
        raise SkillError(6, "rowsUpdatedAt is outside a usable epoch range", source_url=source_url)
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def observed_licence(view: dict[str, Any]) -> str | None:
    licence_id = view.get("licenseId")
    if isinstance(licence_id, str) and licence_id:
        return licence_id
    return None


def parse_view(resource: str, exchange: Any, source_url: str) -> dict[str, Any]:
    body = read_exchange(exchange, "view metadata", source_url)
    if not isinstance(body, dict):
        raise SkillError(6, "view metadata is not a JSON object", source_url=source_url)
    required = RESOURCES[resource]["licence_id"]
    actual = observed_licence(body)
    if actual != required:
        raise SkillError(
            4,
            f"{resource} view licence id {actual!r} does not match required {required}",
            source_url=source_url,
            licence=actual,
        )
    attribution = body.get("attribution")
    if attribution is not None and attribution != PUBLISHER:
        raise SkillError(6, "view attribution does not match the Federal Transit Administration", source_url=source_url, licence=actual)
    columns = body.get("columns")
    if not isinstance(columns, list) or not columns:
        raise SkillError(6, "view metadata has no columns", source_url=source_url, licence=actual)
    found: dict[str, Any] = {}
    for column in columns:
        if isinstance(column, dict) and isinstance(column.get("fieldName"), str):
            found[column["fieldName"]] = column.get("dataTypeName")
    for name, type_name in field_types(resource).items():
        if found.get(name) != type_name:
            raise SkillError(
                6,
                f"column {name} has type {found.get(name)!r}; expected {type_name}",
                source_url=source_url,
                licence=actual,
            )
    if "rowsUpdatedAt" in body:
        body["_latest_data"] = rows_updated_at(body["rowsUpdatedAt"], source_url)
    return body


def fail_type(name: str, source_url: str) -> None:
    raise SkillError(6, f"column {name} has an unexpected value type", source_url=source_url)


def coerce_number(name: str, value: Any, source_url: str, unparsed: list[str]) -> Any:
    if isinstance(value, bool):
        fail_type(name, source_url)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            fail_type(name, source_url)
        if value.is_integer() and abs(value) < 10**15:
            return int(value)
        return value
    if isinstance(value, str):
        if INTEGER_TEXT.fullmatch(value):
            return int(value)
        if DECIMAL_TEXT.fullmatch(value):
            number = float(value)
            if not math.isfinite(number):
                fail_type(name, source_url)
            return number
        if 0 < len(value) <= 40:
            unparsed.append(name)
            return value
    fail_type(name, source_url)
    return None


def coerce_value(name: str, type_name: str, value: Any, source_url: str, unparsed: list[str]) -> Any:
    if value is None:
        return None
    if type_name == "text" or type_name == "calendar_date":
        if not isinstance(value, str):
            fail_type(name, source_url)
        limit = 40 if type_name == "calendar_date" else MAX_CODED_TEXT
        if len(value) > limit:
            raise SkillError(6, f"column {name} exceeds the coded-text bound", source_url=source_url)
        return value
    if type_name == "checkbox":
        if isinstance(value, bool):
            return value
        fail_type(name, source_url)
    if type_name == "number":
        return coerce_number(name, value, source_url, unparsed)
    fail_type(name, source_url)
    return None


def project_row(resource: str, row: Any, source_url: str) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(row, dict):
        raise SkillError(6, "row is not a JSON object", source_url=source_url)
    projected: dict[str, Any] = {}
    unparsed: list[str] = []
    for name, type_name in field_types(resource).items():
        if name not in row or name in DENIED_FIELDS:
            continue
        projected[name] = coerce_value(name, type_name, row[name], source_url, unparsed)
    return projected, unparsed


def licence_name(view: dict[str, Any]) -> str | None:
    licence = view.get("license")
    if not isinstance(licence, dict):
        return None
    name = licence.get("name")
    if isinstance(name, str) and 0 < len(name) <= 120:
        return name
    return None


def success_envelope(resource: str, query: Query, view: dict[str, Any], rows: list[dict[str, Any]], unparsed: list[str], source_url: str) -> dict[str, Any]:
    latest = view.get("_latest_data")
    if latest is not None and not isinstance(latest, str):
        latest = None
    meta = provenance(
        source_url,
        PUBLISHER,
        licence=RESOURCES[resource]["licence_id"],
        latest_data=latest if isinstance(latest, str) else None,
    )
    meta["geography"] = "United States"
    meta["resource_id"] = RESOURCES[resource]["id"]
    meta["view_url"] = view_url(resource)
    meta["licence_id"] = RESOURCES[resource]["licence_id"]
    name = licence_name(view)
    if name:
        meta["licence_name"] = name
    meta["units"] = dict(RESOURCES[resource]["units"])
    meta["time_note"] = RESOURCES[resource]["time_note"]
    meta["measure_note"] = RESOURCES[resource]["measure_note"]
    meta["omitted"] = "incident narratives, person lists, precise locations, and free-text comments"
    meta["count"] = len(rows)
    recorded_query: dict[str, Any] = {"resource": resource, "limit": query.limit}
    if query.year is not None:
        recorded_query["year"] = query.year
    if query.month is not None:
        recorded_query["month"] = query.month
    if query.mode is not None:
        recorded_query["mode"] = query.mode
    if query.ntd_id is not None:
        recorded_query["ntd_id"] = query.ntd_id
    meta["query"] = recorded_query
    if unparsed:
        meta["unparsed_measures"] = sorted(set(unparsed))
    return result_envelope(rows, meta)


def load_fixture(name: str, resource: str) -> list[Any]:
    if not FIXTURE_NAME.fullmatch(name):
        raise SkillError(2, "fixture name must be a hyphenated token", source_url=view_url(resource))
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        raise SkillError(2, "fixture was not found", source_url=view_url(resource))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillError(6, "fixture is not valid JSON", source_url=view_url(resource)) from exc
    if not isinstance(payload, dict):
        raise SkillError(6, "fixture must be a JSON object", source_url=view_url(resource))
    if payload.get("resource") != resource:
        raise SkillError(2, "fixture resource does not match the command", source_url=view_url(resource))
    exchanges = payload.get("exchanges")
    if not isinstance(exchanges, list) or not exchanges:
        raise SkillError(6, "fixture has no exchanges", source_url=view_url(resource))
    return exchanges


def execute(resource: str, query: Query, fixture: str | None) -> dict[str, Any]:
    metadata_url = view_url(resource)
    data_url = rows_url(resource, query)
    if fixture:
        exchanges = load_fixture(fixture, resource)
        view_exchange = exchanges[0]
        rows_exchange = exchanges[1] if len(exchanges) > 1 else None
    else:
        view_exchange = fetch_exchange(metadata_url)
        rows_exchange = None
    view = parse_view(resource, view_exchange, metadata_url)
    if rows_exchange is None:
        rows_exchange = fetch_exchange(data_url)
    body = read_exchange(rows_exchange, "row payload", data_url)
    if not isinstance(body, list):
        raise SkillError(6, "row payload is not a JSON array", source_url=data_url, licence=RESOURCES[resource]["licence_id"])
    if len(body) > query.limit:
        body = body[: query.limit]
    rows: list[dict[str, Any]] = []
    unparsed: list[str] = []
    for item in body:
        projected, row_unparsed = project_row(resource, item, data_url)
        rows.append(projected)
        unparsed.extend(row_unparsed)
    return success_envelope(resource, query, view, rows, unparsed, data_url)


def emit_error(exc: SkillError, json_mode: bool) -> int:
    meta = provenance(
        exc.source_url or ROOT_URL,
        PUBLISHER,
        licence=exc.licence,
        latest_data=exc.latest_data,
    )
    meta["geography"] = "United States"
    if json_mode:
        print(json.dumps(error_envelope(exc.code, str(exc), meta, retry_after=exc.retry_after), indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(f"us-ntd-safety: {exc}", file=sys.stderr)
    return exc.code


def emit_success(resource: str, envelope: dict[str, Any], json_mode: bool) -> int:
    if json_mode:
        print(json.dumps(envelope, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    meta = envelope["meta"]
    results = envelope["results"]
    print(f"United States FTA NTD {resource} ({meta['geography']}; not Auckland)")
    print(f"licence: {meta.get('licence')}  rows: {meta.get('count')}  updated: {meta.get('latest_data', 'not stated')}")
    if resource == "events":
        columns = ("_5_digit_ntd_id", "mode", "year", "event_type", "total_fatalities", "total_injuries")
    else:
        columns = ("_5_digit_ntd_id", "mode", "year", "month", "total_events", "ridership")
    print("\t".join(columns))
    for row in results:
        print("\t".join("" if row.get(column) is None else str(row.get(column, "")) for column in columns))
    print("Use --json for the coded field set. Narratives and person lists are omitted.")
    return 0


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="United States FTA National Transit Database safety data. Not Auckland.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)
    events = sub.add_parser("events", help="coded major safety and security event fields")
    modes = sub.add_parser("modes", help="monthly modal safety and service aggregates")
    for command, parser_ in (("events", events), ("modes", modes)):
        parser_.add_argument("--limit", type=limit_type, default=DEFAULT_LIMIT, help=f"row limit from 1 to {MAX_LIMIT} (default {DEFAULT_LIMIT})")
        parser_.add_argument("--year", type=year_type, help="four-digit calendar year")
        parser_.add_argument("--mode", type=mode_type, help="NTD mode code, such as MB or HR")
        parser_.add_argument("--ntd-id", type=ntd_type, help="five-digit NTD agency id")
        parser_.add_argument("--fixture", help=argparse.SUPPRESS)
        parser_.add_argument("--json", action="store_true", help="emit machine-readable JSON")
        if command == "modes":
            parser_.add_argument("--month", type=month_type, help="English month name, such as January")
    return parser


def query_from_args(args: argparse.Namespace) -> Query:
    return Query(
        limit=args.limit,
        year=args.year,
        month=getattr(args, "month", None),
        mode=args.mode,
        ntd_id=args.ntd_id,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        envelope = execute(args.command, query_from_args(args), args.fixture)
    except SkillError as exc:
        return emit_error(exc, json_mode)
    return emit_success(args.command, envelope, json_mode or args.json)


if __name__ == "__main__":
    raise SystemExit(main())
