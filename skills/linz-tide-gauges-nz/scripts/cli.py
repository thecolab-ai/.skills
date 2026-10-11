#!/usr/bin/env python3
"""Read official LINZ tide-gauge sea-level observations. Keyless and read-only."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

from provenance import error_envelope, provenance, result_envelope  # noqa: E402

HOST = "sealevel-data.linz.govt.nz"
ALLOWED_HOSTS = frozenset({HOST})
ORIGIN = f"https://{HOST}"
PUBLISHER = "Toitū Te Whenua Land Information New Zealand (LINZ)"
LICENCE = "Creative Commons Attribution 3.0 New Zealand (CC BY 3.0 NZ)"
LANDING_URL = f"{ORIGIN}/index.html?tidegauge=AUCT"
MAX_RESPONSE_BYTES = 2_000_000
HEIGHT_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
GAUGE_RE = re.compile(r"^[A-Z][A-Z0-9]{3}$")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class InputError(ValueError):
    """Caller input that must exit 2 without a traceback."""


class SchemaError(ValueError):
    """A successful response that does not match the published file shape."""


class UnsafeError(ValueError):
    """A URL, redirect, or archive path outside the public read boundary."""


class NoMatch(Exception):
    """The source answered, and it does not publish the requested selection."""

    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def bounded_int(label: str, low: int, high: int):
    def parse(value: str) -> int:
        if not re.fullmatch(r"[0-9]{1,6}", value):
            raise argparse.ArgumentTypeError(f"{label} must be an integer from {low} to {high}")
        number = int(value)
        if number < low or number > high:
            raise argparse.ArgumentTypeError(f"{label} must be an integer from {low} to {high}")
        return number

    return parse


def gauge_type(value: str) -> str:
    if not GAUGE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("gauge must be a four-character LINZ code such as AUCT")
    return value


def year_type(value: str) -> str:
    if not re.fullmatch(r"[12][0-9]{3}", value):
        raise argparse.ArgumentTypeError("year must be a four-digit year from 1990 to 2100")
    if not 1990 <= int(value) <= 2100:
        raise argparse.ArgumentTypeError("year must be a four-digit year from 1990 to 2100")
    return value


def sensor_type(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]?", value):
        raise argparse.ArgumentTypeError("sensor must be an integer from 1 to 99")
    return value


def date_type(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD and is a UTC day, not a New Zealand local day")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be a real calendar day") from exc
    if not 1990 <= parsed.year <= 2100:
        raise argparse.ArgumentTypeError("date year must be from 1990 to 2100")
    return parsed.isoformat()


def timeout_type(value: str) -> int:
    return bounded_int("timeout", 1, 60)(value)


def check_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or "\\" in url
        or not (parsed.path.startswith("/api/") or parsed.path.startswith("/tidegauge/"))
    ):
        raise UnsafeError("refusing a request outside the LINZ tide-gauge host")


def http_get(url: str, *, expect_json: bool, timeout: int) -> bytes:
    check_url(url)
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            allowed_hosts=ALLOWED_HOSTS,
            expect_json=expect_json,
            max_bytes=MAX_RESPONSE_BYTES,
        )
    except (TimeoutError, OSError) as exc:
        raise nzfetch.FetchError(f"network error: {exc}") from exc
    check_url(final_url)
    return body


def read_json(url: str, timeout: int) -> dict:
    body = http_get(url, expect_json=True, timeout=timeout)
    return decode_json(body)


def decode_json(body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError("source response was not UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise SchemaError("source JSON was not an object")
    return data


def resolve_fixture(name: str, suffixes: set[str]) -> Path:
    if not name or name.startswith(("/", "\\")) or ".." in Path(name).parts:
        raise InputError("fixture must be a relative file under tests/fixtures")
    path = (FIXTURES / name).resolve()
    if not path.is_relative_to(FIXTURES.resolve()) or not path.is_file():
        raise InputError("fixture must be a file inside tests/fixtures")
    if path.suffix.lower() not in suffixes:
        raise InputError("fixture suffix is not valid for this command")
    return path


def read_fixture(name: str, suffixes: set[str]) -> bytes:
    try:
        return resolve_fixture(name, suffixes).read_bytes()
    except OSError as exc:
        raise InputError("fixture could not be read") from exc


def gauges_url() -> str:
    return f"{ORIGIN}/api/listGauges"


def datasets_url(gauge: str) -> str:
    return f"{ORIGIN}/api/getGaugeData/{gauge}"


def files_url(gauge: str, year: str, sensor: str) -> str:
    return f"{ORIGIN}/api/listDatasetFiles/{gauge}/{year}/{sensor}"


def zip_url(gauge: str, year: str, sensor: str, name: str) -> str:
    return f"{ORIGIN}/tidegauge/{gauge}/{year}/{sensor}/{name}"


def parse_gauges(data: dict) -> list[str]:
    gauges = data.get("gauges")
    if not isinstance(gauges, list) or not gauges or not all(isinstance(item, str) and GAUGE_RE.fullmatch(item) for item in gauges):
        raise SchemaError("listGauges did not return LINZ gauge codes")
    if len(gauges) != len(set(gauges)):
        raise SchemaError("listGauges returned duplicate gauge codes")
    return gauges


def parse_datasets(data: dict, gauge: str) -> list[dict[str, str]]:
    if data.get("gauge") != gauge or not isinstance(data.get("datasets"), list) or not isinstance(data.get("files"), list):
        raise SchemaError("getGaugeData did not match the requested gauge")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data["datasets"]:
        if not isinstance(item, dict):
            raise SchemaError("dataset entry was not an object")
        year, sensor, dataset_id = item.get("year"), item.get("sensor"), item.get("datasetid")
        expected = f"{gauge}/{year}/{sensor}"
        if not (isinstance(year, str) and re.fullmatch(r"\d{4}", year) and isinstance(sensor, str) and re.fullmatch(r"[1-9][0-9]?", sensor)):
            raise SchemaError("dataset year or sensor was not in the published form")
        if dataset_id != expected or dataset_id in seen:
            raise SchemaError("dataset id did not match the gauge, year, and sensor")
        seen.add(dataset_id)
        rows.append({"gauge": gauge, "year": year, "sensor": sensor, "dataset_id": dataset_id})
    return rows


def day_from_ordinal(year: str, ordinal: str) -> str:
    start = date(int(year), 1, 1)
    parsed = start + timedelta(days=int(ordinal) - 1)
    if parsed.year != int(year):
        raise SchemaError("daily file day of year falls outside the requested year")
    return parsed.isoformat()


def parse_files(data: dict, gauge: str, year: str, sensor: str) -> list[dict[str, object]]:
    files = data.get("files")
    if not isinstance(files, list):
        raise SchemaError("listDatasetFiles did not return a file list")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    pattern = re.compile(rf"^{re.escape(gauge)}_{re.escape(sensor)}_{re.escape(year)}(\d{{3}})\.zip$")
    for item in files:
        if not isinstance(item, dict):
            raise SchemaError("daily file entry was not an object")
        name, uri, size, modified = item.get("name"), item.get("uri"), item.get("size"), item.get("modified")
        match = pattern.fullmatch(name) if isinstance(name, str) else None
        if match is None or name in seen:
            raise SchemaError("daily file name did not match the requested dataset")
        seen.add(name)
        if uri != f"/tidegauge/{gauge}/{year}/{sensor}/{name}":
            raise SchemaError("daily file URI did not match the official tide-gauge path")
        if type(size) is not int or not 0 <= size <= MAX_RESPONSE_BYTES:
            raise SchemaError("daily file size was not a bounded integer")
        if not isinstance(modified, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified):
            raise SchemaError("daily file modified value was not an ISO date")
        rows.append(
            {
                "gauge": gauge,
                "sensor": sensor,
                "name": name,
                "utc_date": day_from_ordinal(year, match.group(1)),
                "size": size,
                "modified": modified,
            }
        )
    return rows


def parse_daily_csv(text: str, gauge: str, utc_date: str, sensor: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 3:
            raise SchemaError("daily CSV row did not have site, UTC minute, and height")
        site, stamp, height = parts
        if site != gauge:
            raise SchemaError("daily CSV site code did not match the gauge")
        try:
            observed = datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise SchemaError("daily CSV timestamp was not a UTC minute in YYYY-MM-DD HH:MM form") from exc
        if observed.date().isoformat() != utc_date:
            raise SchemaError("daily CSV timestamp was not on the requested UTC date")
        if stamp in seen:
            raise SchemaError("daily CSV contained a duplicate UTC minute")
        seen.add(stamp)
        if HEIGHT_RE.fullmatch(height) is None:
            raise SchemaError("daily CSV height was not a plain decimal metre value")
        rows.append(
            {
                "gauge": gauge,
                "sensor": sensor,
                "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "height_m": height,
            }
        )
    if not rows:
        raise SchemaError("daily CSV contained no readings")
    stamps = [row["observed_at"] for row in rows]
    if stamps != sorted(stamps):
        raise SchemaError("daily CSV timestamps were not in ascending UTC order")
    return rows


def parse_daily_zip(blob: bytes, gauge: str, utc_date: str, sensor: str, year: str) -> list[dict[str, str]]:
    if len(blob) > MAX_RESPONSE_BYTES:
        raise UnsafeError("daily archive exceeds the size bound")
    ordinal = f"{date.fromisoformat(utc_date).timetuple().tm_yday:03d}"
    expected = f"{gauge}_{sensor}_{year}{ordinal}.csv"
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise SchemaError("daily archive was not a zip file") from exc
    names = archive.namelist()
    if any(name.startswith("/") or ".." in Path(name).parts or name != Path(name).name for name in names):
        raise UnsafeError("daily archive contained an unsafe path")
    if names != [expected]:
        raise SchemaError("daily archive did not contain the single expected CSV")
    info = archive.getinfo(expected)
    if info.file_size > MAX_RESPONSE_BYTES:
        raise UnsafeError("daily CSV exceeds the size bound")
    try:
        text = archive.read(expected).decode("utf-8-sig")
    except UnicodeError as exc:
        raise SchemaError("daily CSV was not UTF-8") from exc
    return parse_daily_csv(text, gauge, utc_date, sensor)


def page(rows: list, offset: int, limit: int) -> tuple[list, int, bool]:
    selected = rows[offset : offset + limit]
    return selected, len(rows), offset + len(selected) < len(rows)


def published_gauges(args) -> tuple[list[str], str]:
    if args.fixture:
        return parse_gauges(decode_json(read_fixture(args.fixture, {".json"}))), "fixture"
    return parse_gauges(read_json(gauges_url(), args.timeout)), "live"


def published_datasets(args, gauge: str) -> tuple[list[dict[str, str]], str]:
    if args.fixture:
        return parse_datasets(decode_json(read_fixture(args.fixture, {".json"})), gauge), "fixture"
    gauges, _kind = published_gauges(argparse.Namespace(fixture=None, timeout=args.timeout))
    if gauge not in gauges:
        raise NoMatch(f"{gauge} is not in the current LINZ tide-gauge list")
    return parse_datasets(read_json(datasets_url(gauge), args.timeout), gauge), "live"


def published_files(args, gauge: str, year: str, sensor: str) -> tuple[list[dict[str, object]], str]:
    if args.fixture:
        return parse_files(decode_json(read_fixture(args.fixture, {".json"})), gauge, year, sensor), "fixture"
    datasets, _kind = published_datasets(argparse.Namespace(fixture=None, timeout=args.timeout), gauge)
    if not any(row["year"] == year and row["sensor"] == sensor for row in datasets):
        raise NoMatch(f"no {year} sensor {sensor} dataset is published for {gauge}")
    return parse_files(read_json(files_url(gauge, year, sensor), args.timeout), gauge, year, sensor), "live"


def command_source(args) -> str:
    if args.command == "gauges":
        return gauges_url()
    if args.command == "datasets":
        return datasets_url(args.gauge)
    if args.command == "files":
        return files_url(args.gauge, args.year, args.sensor)
    year = args.date[:4]
    ordinal = f"{date.fromisoformat(args.date).timetuple().tm_yday:03d}"
    return zip_url(args.gauge, year, args.sensor, f"{args.gauge}_{args.sensor}_{year}{ordinal}.zip")


def base_meta(source_url: str, latest_data: str | None = None) -> dict:
    return provenance(source_url, PUBLISHER, licence=LICENCE, latest_data=latest_data)


def emit_error(code: int, message: str, json_mode: bool, meta: dict, retry_after: str | None = None) -> int:
    if json_mode:
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"linz-tide-gauges-nz: {message}", file=sys.stderr)
    return code


def emit_ok(json_mode: bool, rows: list, meta: dict, human: list[str]) -> int:
    if json_mode:
        print(json.dumps(result_envelope(rows, meta), indent=2, ensure_ascii=False))
    elif human:
        print("\n".join(human))
    else:
        print("linz-tide-gauges-nz: no matching records")
    return 0


def with_page_meta(source_url: str, *, latest_data: str | None, status: str, matched: int, truncated: bool, kind: str, note: str | None) -> dict:
    meta = base_meta(source_url, latest_data)
    meta["query_status"] = status
    meta["matched_count"] = matched
    meta["truncated"] = truncated
    meta["retrieval_kind"] = kind
    if note:
        meta["note"] = note
    return meta


def run_gauges(args) -> int:
    gauges, kind = published_gauges(args)
    rows = [{"gauge": code} for code in gauges]
    selected, matched, truncated = page(rows, 0, len(rows))
    meta = with_page_meta(gauges_url(), latest_data=None, status="ok", matched=matched, truncated=truncated, kind=kind, note=None)
    return emit_ok(args.json, selected, meta, gauges)


def run_datasets(args) -> int:
    rows, kind = published_datasets(args, args.gauge)
    selected, matched, truncated = page(rows, 0, len(rows) or 0)
    latest = max((row["year"] for row in rows), default=None)
    meta = with_page_meta(datasets_url(args.gauge), latest_data=latest, status="ok", matched=matched, truncated=truncated, kind=kind, note=None)
    human = [f"{row['gauge']} {row['year']} sensor {row['sensor']}" for row in selected]
    return emit_ok(args.json, selected, meta, human)


def run_files(args) -> int:
    rows, kind = published_files(args, args.gauge, args.year, args.sensor)
    selected, matched, truncated = page(rows, args.offset, args.limit)
    latest = max((str(row["modified"]) for row in rows), default=None)
    meta = with_page_meta(files_url(args.gauge, args.year, args.sensor), latest_data=latest, status="ok", matched=matched, truncated=truncated, kind=kind, note=None)
    meta["latest_data_meaning"] = "newest file modified date in this dataset listing; not an observation time"
    human = [f"{row['utc_date']} {row['name']} modified {row['modified']}" for row in selected]
    return emit_ok(args.json, selected, meta, human)


def run_readings(args) -> int:
    year = args.date[:4]
    source = command_source(args)
    if args.fixture:
        blob = read_fixture(args.fixture, {".csv", ".zip"})
        if args.fixture.lower().endswith(".zip"):
            rows = parse_daily_zip(blob, args.gauge, args.date, args.sensor, year)
        else:
            rows = parse_daily_csv(blob.decode("utf-8-sig"), args.gauge, args.date, args.sensor)
        kind = "fixture"
    else:
        files, _kind = published_files(
            argparse.Namespace(fixture=None, timeout=args.timeout),
            args.gauge,
            year,
            args.sensor,
        )
        match = next((row for row in files if row["utc_date"] == args.date), None)
        if match is None:
            raise NoMatch(f"no daily file is published for {args.gauge} sensor {args.sensor} on UTC date {args.date}")
        blob = http_get(zip_url(args.gauge, year, args.sensor, str(match["name"])), expect_json=False, timeout=args.timeout)
        rows = parse_daily_zip(blob, args.gauge, args.date, args.sensor, year)
        kind = "live"
    selected, matched, truncated = page(rows, args.offset, args.limit)
    meta = with_page_meta(source, latest_data=rows[-1]["observed_at"], status="ok", matched=matched, truncated=truncated, kind=kind, note=None)
    meta["observation_time"] = "UTC"
    meta["latest_data_meaning"] = "last UTC observation minute in this daily file; not the retrieval time and not a quality-control time"
    human = [f"{row['gauge']} sensor {row['sensor']} {row['observed_at']} {row['height_m']} m" for row in selected]
    if human:
        human.append("Times are UTC minutes. Heights are unquality-controlled sensor metres, not tide predictions.")
    return emit_ok(args.json, selected, meta, human)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Official LINZ tide-gauge sea-level observations")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(target, *, fixture: bool) -> None:
        target.add_argument("--json", action="store_true", help="emit the meta/results JSON envelope")
        target.add_argument("--timeout", type=timeout_type, default=10, help="per-request timeout in seconds (1-60)")
        if fixture:
            target.add_argument("--fixture", help="relative tests/fixtures file for an offline parser run")

    gauges = sub.add_parser("gauges", help="list published LINZ tide-gauge codes")
    add_common(gauges, fixture=True)
    datasets = sub.add_parser("datasets", help="list year and sensor datasets for one gauge")
    datasets.add_argument("--gauge", required=True, type=gauge_type)
    add_common(datasets, fixture=True)
    files = sub.add_parser("files", help="list daily zip files for one gauge, year, and sensor")
    files.add_argument("--gauge", required=True, type=gauge_type)
    files.add_argument("--year", required=True, type=year_type)
    files.add_argument("--sensor", type=sensor_type, default="40")
    files.add_argument("--limit", type=bounded_int("limit", 1, 366), default=20)
    files.add_argument("--offset", type=bounded_int("offset", 0, 100000), default=0)
    add_common(files, fixture=True)
    readings = sub.add_parser("readings", help="read one UTC day's minute heights")
    readings.add_argument("--gauge", required=True, type=gauge_type)
    readings.add_argument("--date", required=True, type=date_type, help="UTC calendar day, not a New Zealand local day")
    readings.add_argument("--sensor", type=sensor_type, default="40")
    readings.add_argument("--limit", type=bounded_int("limit", 1, 1440), default=60)
    readings.add_argument("--offset", type=bounded_int("offset", 0, 100000), default=0)
    add_common(readings, fixture=True)
    return parser


def dispatch(args) -> int:
    if args.command == "gauges":
        return run_gauges(args)
    if args.command == "datasets":
        return run_datasets(args)
    if args.command == "files":
        return run_files(args)
    if args.command == "readings":
        return run_readings(args)
    raise InputError("unsupported command")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    try:
        args = build_parser().parse_args(argv)
    except InputError as exc:
        return emit_error(2, str(exc), json_mode, base_meta(LANDING_URL))
    try:
        return dispatch(args)
    except InputError as exc:
        return emit_error(2, str(exc), args.json, base_meta(command_source(args)))
    except NoMatch as exc:
        meta = with_page_meta(
            command_source(args),
            latest_data=None,
            status="no_match",
            matched=0,
            truncated=False,
            kind="fixture" if getattr(args, "fixture", None) else "live",
            note=exc.note,
        )
        return emit_ok(args.json, [], meta, [])
    except SchemaError as exc:
        return emit_error(6, str(exc), args.json, base_meta(command_source(args)))
    except UnsafeError as exc:
        return emit_error(7, str(exc), args.json, base_meta(command_source(args)))
    except nzfetch.RateLimited as exc:
        return emit_error(4, f"network error: rate_limited: {exc}", args.json, base_meta(command_source(args)), retry_after=exc.retry_after)
    except nzfetch.Blocked as exc:
        return emit_error(4, f"network error: blocked: {exc}", args.json, base_meta(command_source(args)))
    except nzfetch.FetchError as exc:
        message = str(exc)
        if not message.startswith("network error:"):
            message = f"network error: {message}"
        return emit_error(5, message, args.json, base_meta(command_source(args)))


if __name__ == "__main__":
    raise SystemExit(main())
