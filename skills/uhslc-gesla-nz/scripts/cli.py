#!/usr/bin/env python3
"""Read one short New Zealand GESLA sea-level series from UHSLC ERDDAP."""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from provenance import error_envelope, provenance, result_envelope

ALLOWED_HOST = "uhslc.soest.hawaii.edu"
DATASET_ID = "global_hourly_gesla"
INFO_URL = "https://uhslc.soest.hawaii.edu/erddap/info/global_hourly_gesla/index.html"
PUBLISHER = "University of Hawaii Sea Level Center"
LICENCE = (
    "The data may be used and redistributed for free but is not intended "
    "for legal use, since it may contain inaccuracies."
)
USER_AGENT = (
    "thecolab-uhslc-gesla-nz/1.0 "
    "(public research; +https://github.com/thecolab-ai/.skills)"
)
TIMEOUT_SECONDS = 15
MAX_WINDOW = timedelta(hours=48)
MAX_BYTES = 65536
MAX_ROWS = 400
COLUMNS = ("time", "sea_level", "flag1", "flag2", "record_id")
EXPECTED_UNITS = ["UTC", "m", "", "", ""]
MISSING_SEA_LEVEL = Decimal("-99.9999")
STATION_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,8}$")
TIME_ARG_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)
OBSERVED_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
FIXTURE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}\.csv$")
FLAG1_MEANINGS = {
    0: "no_quality_control",
    1: "correct_value",
    2: "interpolated_value",
    3: "doubtful_value",
    4: "isolated_spike_or_wrong_value",
    5: "missing_value",
}
FLAG2_MEANINGS = {0: "do_not_use", 1: "use"}


class SkillError(Exception):
    """A typed failure with a stable exit code."""

    def __init__(self, message: str, code: int, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class InputError(ValueError):
    """An argparse failure emitted as a JSON error envelope."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any redirect that leaves the official HTTPS host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host != ALLOWED_HOST:
            raise SkillError(
                "redirect to a host outside the allowlist was rejected"
                + (f" ({host})" if host else ""),
                7,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def source_meta(url: str) -> dict[str, str]:
    return provenance(url, PUBLISHER, licence=LICENCE)


def validate_station(station: str) -> str:
    parts = station.split("-")
    if not STATION_RE.fullmatch(station) or "nzl" not in parts:
        raise SkillError(
            "station must be a lowercase GESLA record_id with an nzl country segment, "
            "such as auckland-auct-nzl-ttw",
            2,
        )
    return station


def parse_bound(value: str) -> datetime:
    if not TIME_ARG_RE.fullmatch(value):
        raise SkillError(
            "times must be UTC ISO-8601 to the second, such as 2024-01-01T00:00:00Z",
            2,
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SkillError("times must be real UTC ISO-8601 timestamps", 2) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SkillError("times must include a timezone; naive timestamps are rejected", 2)
    return parsed.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_series_url(station: str, start: datetime, end: datetime) -> str:
    """Build the only request this skill makes: one station and one time window."""
    quoted = urllib.parse.quote(station, safe="")
    return (
        f"https://{ALLOWED_HOST}/erddap/tabledap/{DATASET_ID}.csv"
        f"?{','.join(COLUMNS)}"
        f"&record_id=%22{quoted}%22"
        f"&time%3E={format_utc(start)}"
        f"&time%3C{format_utc(end)}"
    )


def official_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != ALLOWED_HOST or parsed.username or parsed.password:
        raise SkillError("refusing a URL outside the official host", 7)
    return parsed


def header_map(headers) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def read_bounded(response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = response.read(8192)
        if not block:
            break
        total += len(block)
        if total > MAX_BYTES:
            raise SkillError(
                f"response exceeded the {MAX_BYTES} byte cap; partial series refused",
                7,
            )
        chunks.append(block)
    return b"".join(chunks)


def fetch_official(url: str, opener=None) -> tuple[int, dict[str, str], bytes]:
    official_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv, text/plain;q=0.5"},
        method="GET",
    )
    if opener is None:
        opener = urllib.request.build_opener(AllowlistRedirect)
    try:
        response = opener.open(request, timeout=TIMEOUT_SECONDS)
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        try:
            body = read_bounded(exc)
            return exc.code, header_map(exc.headers), body
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
            raise SkillError("network error: source request timed out", 5) from exc
        raise SkillError(f"network error: {reason}", 5) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise SkillError("network error: source request timed out", 5) from exc
    with response:
        final = response.geturl()
        official_url(final)
        status = getattr(response, "status", None) or response.getcode()
        return int(status), header_map(response.headers), read_bounded(response)


def decode_text(body: bytes) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillError("source schema failure: response is not UTF-8 text", 6) from exc
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def parse_observed_time(token: str) -> datetime:
    if not OBSERVED_TIME_RE.fullmatch(token):
        raise SkillError("source schema failure: time is not a UTC timestamp", 6)
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SkillError("source schema failure: time is not a UTC timestamp", 6) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise SkillError(
            "source schema failure: time is not UTC, which contradicts the units row",
            6,
        )
    return parsed.astimezone(timezone.utc)


def parse_flag(token: str, vocabulary: dict[int, str], label: str) -> tuple[int, str]:
    if not re.fullmatch(r"-?\d+", token):
        raise SkillError(f"source schema failure: {label} is not an integer code", 6)
    value = int(token)
    try:
        meaning = vocabulary[value]
    except KeyError as exc:
        raise SkillError(
            f"source schema failure: {label} {value} is outside the published flag vocabulary",
            6,
        ) from exc
    return value, meaning


def parse_sea_level(token: str) -> tuple[str | None, bool]:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise SkillError("source schema failure: sea_level is not a decimal number of metres", 6) from exc
    if not value.is_finite():
        raise SkillError("source schema failure: sea_level is not a finite number of metres", 6)
    if value == MISSING_SEA_LEVEL:
        return None, True
    return token, False


def parse_series_csv(body: bytes, station: str, start: datetime, end: datetime) -> list[dict]:
    text = decode_text(body)
    stripped = text.lstrip()
    if stripped.startswith("<") or stripped.startswith("{"):
        raise SkillError("source schema failure: expected ERDDAP CSV, not HTML or JSON", 6)
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise SkillError("source schema failure: truncated or malformed CSV", 6) from exc
    if len(rows) < 2:
        raise SkillError("source schema failure: CSV is missing the name or units row", 6)
    if rows[0] != list(COLUMNS):
        raise SkillError("source schema failure: unexpected CSV columns", 6)
    if rows[1] != EXPECTED_UNITS:
        raise SkillError("source schema failure: unexpected CSV units", 6)
    data = rows[2:]
    if len(data) > MAX_ROWS:
        raise SkillError(
            f"response exceeded the {MAX_ROWS} row cap; partial series refused",
            7,
        )
    parsed: list[dict] = []
    for index, row in enumerate(data, start=1):
        if len(row) != 5:
            raise SkillError("source schema failure: truncated or malformed CSV", 6)
        observed = parse_observed_time(row[0])
        if not (start <= observed < end):
            raise SkillError(
                "source schema failure: an observation falls outside the requested window",
                6,
            )
        sea_level, missing = parse_sea_level(row[1])
        flag1, flag1_meaning = parse_flag(row[2], FLAG1_MEANINGS, "flag1")
        flag2, flag2_meaning = parse_flag(row[3], FLAG2_MEANINGS, "flag2")
        if row[4] != station:
            raise SkillError(
                "source schema failure: record_id does not match the requested station",
                6,
            )
        parsed.append(
            {
                "time": row[0],
                "sea_level": sea_level,
                "sea_level_unit": "m",
                "sea_level_missing": missing,
                "flag1": flag1,
                "flag1_meaning": flag1_meaning,
                "flag2": flag2,
                "flag2_meaning": flag2_meaning,
                "record_id": row[4],
                "source_row": index,
            }
        )
    return parsed


def interpret_response(
    status: int,
    headers: dict[str, str],
    body: bytes,
    station: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    if status == 429:
        retry_after = headers.get("retry-after") if "retry-after" in headers else None
        raise SkillError("network error: HTTP 429", 4, retry_after=retry_after)
    if status in {500, 502, 503, 504}:
        raise SkillError(f"network error: HTTP {status}", 5)
    if status == 404:
        text = decode_text(body)
        if "no matching results" in text.casefold():
            return []
        raise SkillError("source schema failure: unexpected HTTP 404 response", 6)
    if status != 200:
        raise SkillError(f"network error: HTTP {status}", 5)
    return parse_series_csv(body, station, start, end)


def read_fixture(name: str) -> bytes:
    if not FIXTURE_NAME_RE.fullmatch(name):
        raise SkillError("fixture name must be a CSV file name in tests/fixtures", 2)
    root = (Path(__file__).resolve().parents[1] / "tests" / "fixtures").resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise SkillError("fixture was not found in tests/fixtures", 2)
    return path.read_bytes()


def format_human(results: list[dict]) -> str:
    if not results:
        return "No observations for this station in the requested window."
    lines = [
        "time\tsea_level_m\tmissing\tflag1\tflag1_meaning\tflag2\tflag2_meaning\trecord_id"
    ]
    for row in results:
        level = "" if row["sea_level"] is None else row["sea_level"]
        lines.append(
            "\t".join(
                (
                    row["time"],
                    level,
                    "true" if row["sea_level_missing"] else "false",
                    str(row["flag1"]),
                    row["flag1_meaning"],
                    str(row["flag2"]),
                    row["flag2_meaning"],
                    row["record_id"],
                )
            )
        )
    lines.append(
        f"{len(results)} observation(s). Sea level unit: metres. "
        "Datum: unspecified by the source. Not for legal use."
    )
    return "\n".join(lines)


def emit_error(code: int, message: str, meta: dict[str, str], as_json: bool, retry_after=None) -> int:
    if as_json:
        payload = error_envelope(code, message, meta, retry_after=retry_after)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"uhslc-gesla-nz: {message}", file=sys.stderr)
    return code


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="UHSLC GESLA sea level for one New Zealand station")
    sub = parser.add_subparsers(dest="command", required=True)
    series = sub.add_parser("series", help="sea level, quality flags and record id for one station and time window")
    series.add_argument("--station", required=True, help="GESLA record_id, for example auckland-auct-nzl-ttw")
    series.add_argument("--from", dest="from_time", required=True, help="inclusive UTC start")
    series.add_argument("--to", dest="to_time", required=True, help="exclusive UTC end, at most 48 hours later")
    series.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    series.add_argument(
        "--fixture",
        help="read this CSV file name from tests/fixtures instead of the network",
    )
    return parser


def load_series(args: argparse.Namespace, start: datetime, end: datetime, url: str) -> list[dict]:
    if args.fixture:
        body = read_fixture(args.fixture)
        return parse_series_csv(body, args.station, start, end)
    status, headers, body = fetch_official(url)
    return interpret_response(status, headers, body, args.station, start, end)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    as_json = "--json" in argv
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        return emit_error(2, str(exc), source_meta(INFO_URL), as_json)
    try:
        args.station = validate_station(args.station)
        start = parse_bound(args.from_time)
        end = parse_bound(args.to_time)
        if end <= start:
            raise SkillError("--from must be earlier than --to", 2)
        if end - start > MAX_WINDOW:
            raise SkillError("the time window must be at most 48 hours", 7)
        url = build_series_url(args.station, start, end)
        results = load_series(args, start, end, url)
    except SkillError as exc:
        return emit_error(exc.code, str(exc), source_meta(INFO_URL), args.json, exc.retry_after)
    meta = source_meta(url)
    if args.json:
        print(json.dumps(result_envelope(results, meta), indent=2, ensure_ascii=False))
    else:
        print(format_human(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
