#!/usr/bin/env python3
"""Read-only CLI for the official New Zealand Heritage List CSV export."""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

LANDING_URL = "https://www.heritage.org.nz/list-details"
CSV_URL = "https://hnzpt-prod-web.azurewebsites.net/api/report/GetPlaceListCsv"
ALLOWED_HOSTS = {"hnzpt-prod-web.azurewebsites.net"}
SOURCE_NAME = "Heritage New Zealand Pouhere Taonga"
TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_LIMIT = 100

REQUIRED_COLUMNS = (
    "ListNumber",
    "Name",
    "ListEntryType",
    "ListEntryStatus",
    "DateEntered",
    "DateOfEffect",
    "Address",
    "LegalDescription",
    "ExtentOfListEntry",
    "DistrictCouncil",
    "NZAANumbers",
)
COLUMN_MAP = {
    "ListNumber": "list_number",
    "Name": "name",
    "ListEntryType": "entry_type",
    "ListEntryStatus": "entry_status",
    "DateEntered": "date_entered",
    "DateOfEffect": "date_of_effect",
    "Address": "address",
    "LegalDescription": "legal_description",
    "ExtentOfListEntry": "extent_of_list_entry",
    "DistrictCouncil": "district_council",
    "NZAANumbers": "nzaa_numbers",
}
SEARCH_FIELDS = (
    "list_number",
    "name",
    "address",
    "district_council",
    "entry_type",
    "entry_status",
)
PUBLIC_FIELDS = (
    "list_number",
    "name",
    "entry_type",
    "entry_status",
    "address",
    "district_council",
)
DETAIL_FIELDS = PUBLIC_FIELDS + ("date_entered", "date_of_effect", "nzaa_numbers")
CAVEATS = [
    "Treat this export as discovery evidence, not legal advice or a title, planning, or LIM search.",
    "A List entry does not itself establish access rights, ownership, or every applicable protection.",
    "Check the current List detail, relevant council plan, property title, and Heritage New Zealand Pouhere Taonga before relying on a result.",
    "Archaeological-site obligations may apply whether or not a place appears in this export.",
]


class SkillError(Exception):
    """Base error carrying the repository exit-code contract."""

    exit_code = 5
    error_code = "upstream_unavailable"
    blocked = False


class InputError(SkillError):
    exit_code = 2
    error_code = "invalid_input"


class NotFoundError(InputError):
    error_code = "not_found"


class SourceBlockedError(SkillError):
    exit_code = 4
    error_code = "source_blocked"
    blocked = True


class SourceSchemaError(SkillError):
    exit_code = 6
    error_code = "source_schema_error"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_nzaa_numbers(value: str) -> list[str]:
    stripped = value.strip().strip("[]")
    return [part.strip() for part in stripped.split(",") if part.strip()]


def parse_csv_text(text: str) -> list[dict[str, Any]]:
    """Parse the official export and fail closed if its required schema drifts."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = [field.lstrip("\ufeff").strip() for field in (reader.fieldnames or [])]
    missing = [column for column in REQUIRED_COLUMNS if column not in fields]
    if missing:
        raise SourceSchemaError(f"missing required columns: {', '.join(missing)}")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values()):
            continue
        record: dict[str, Any] = {}
        for source_column, output_column in COLUMN_MAP.items():
            value = (raw.get(source_column) or "").strip()
            record[output_column] = parse_nzaa_numbers(value) if source_column == "NZAANumbers" else value
        list_number = record["list_number"]
        if not list_number or not record["name"]:
            raise SourceSchemaError(f"row {line_number} has no list number or name")
        if list_number in seen:
            raise SourceSchemaError(f"duplicate list number in source: {list_number}")
        seen.add(list_number)
        records.append(record)
    if not records:
        raise SourceSchemaError("source contained no Heritage List records")
    return records


def fetch_records() -> tuple[list[dict[str, Any]], dict[str, Any], tuple[str, ...]]:
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            CSV_URL,
            timeout=TIMEOUT_SECONDS,
            accept="text/csv,*/*;q=0.8",
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_DOWNLOAD_BYTES,
        )
    except (nzfetch.Blocked, nzfetch.RateLimited) as exc:
        raise SourceBlockedError(str(exc)) from exc
    except nzfetch.ResponseTooLarge as exc:
        raise SourceSchemaError(str(exc)) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc)) from exc
    if "csv" not in content_type.lower():
        raise SourceSchemaError(f"expected CSV but source returned {content_type or 'no content type'}")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceSchemaError("source is not valid UTF-8 CSV") from exc
    records = parse_csv_text(text)
    source = {
        "name": SOURCE_NAME,
        "url": CSV_URL,
        "landing_page": LANDING_URL,
        "final_url": final_url,
        "retrieved_at": utc_now(),
        "content_type": content_type,
    }
    return records, source, REQUIRED_COLUMNS


def contains(value: str, query: str) -> bool:
    return query.casefold() in value.casefold()


def search_records(
    records: list[dict[str, Any]],
    query: str,
    *,
    district: str | None = None,
    entry_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    query = query.strip()
    matches: list[dict[str, Any]] = []
    for record in records:
        if query and not any(contains(str(record[field]), query) for field in SEARCH_FIELDS):
            continue
        if district and not contains(record["district_council"], district):
            continue
        if entry_type and not contains(record["entry_type"], entry_type):
            continue
        if status and not contains(record["entry_status"], status):
            continue
        matches.append(record)
    return matches


def get_record(records: list[dict[str, Any]], list_number: str) -> dict[str, Any]:
    wanted = list_number.strip().casefold()
    if not wanted:
        raise InputError("list number cannot be empty")
    matches = [record for record in records if record["list_number"].casefold() == wanted]
    if not matches:
        raise NotFoundError(f"no Heritage List entry found for list number {list_number!r}")
    if len(matches) > 1:
        raise SourceSchemaError(f"source returned duplicate list number {list_number!r}")
    return matches[0]


def project_record(record: dict[str, Any], *, detailed: bool) -> dict[str, Any]:
    """Minimise output; omit source legal descriptions and long-form extent text."""
    fields = DETAIL_FIELDS if detailed else PUBLIC_FIELDS
    return {field: record[field] for field in fields}


def bounded_limit(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if not 1 <= parsed <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be between 1 and {MAX_LIMIT}")
    return parsed


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search the official New Zealand Heritage List/Rārangi Kōrero CSV export."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search names, addresses, list numbers and councils")
    search.add_argument("query", nargs="?", default="", help="case-insensitive search text")
    search.add_argument("--council", help="filter by district council")
    search.add_argument("--type", dest="entry_type", help="filter by List entry type")
    search.add_argument("--status", help="filter by List entry status")
    search.add_argument("--limit", type=bounded_limit, default=20, help=f"maximum results (1-{MAX_LIMIT})")
    add_json_flag(search)

    get = subparsers.add_parser("get", help="look up one exact List number")
    get.add_argument("list_number", help="exact ListNumber from the official export")
    add_json_flag(get)

    status = subparsers.add_parser("status", help="check the live export schema and record count")
    add_json_flag(status)
    return parser.parse_args(argv)


def search_payload(args: argparse.Namespace) -> dict[str, Any]:
    records, source, _columns = fetch_records()
    matches = search_records(
        records,
        args.query,
        district=args.council,
        entry_type=args.entry_type,
        status=args.status,
    )
    return {
        "kind": "heritage_list_search",
        "source": source,
        "query": {
            "text": args.query,
            "council": args.council,
            "entry_type": args.entry_type,
            "status": args.status,
            "limit": args.limit,
        },
        "matched_count": len(matches),
        "returned": min(len(matches), args.limit),
        "records": [project_record(record, detailed=False) for record in matches[: args.limit]],
        "warnings": CAVEATS,
    }


def get_payload(args: argparse.Namespace) -> dict[str, Any]:
    records, source, _columns = fetch_records()
    record = get_record(records, args.list_number)
    return {
        "kind": "heritage_list_entry",
        "source": source,
        "record": project_record(record, detailed=True),
        "warnings": CAVEATS,
    }


def status_payload() -> dict[str, Any]:
    records, source, columns = fetch_records()
    return {
        "kind": "heritage_list_status",
        "source": source,
        "record_count": len(records),
        "columns": list(columns),
        "health": "healthy",
        "warnings": CAVEATS,
    }


def print_human(payload: dict[str, Any]) -> None:
    kind = payload["kind"]
    if kind == "heritage_list_search":
        print(f"Matches: {payload['matched_count']} (showing {payload['returned']})")
        for record in payload["records"]:
            print(
                f"{record['list_number']} | {record['name']} | {record['entry_type']} | "
                f"{record['district_council']} | {record['address']}"
            )
    elif kind == "heritage_list_entry":
        record = payload["record"]
        for field, value in record.items():
            label = field.replace("_", " ").title()
            rendered = ", ".join(value) if isinstance(value, list) else value
            print(f"{label}: {rendered or '-'}")
    else:
        print(f"Heritage List export: {payload['record_count']} records; {payload['health']}")
    print(f"Source retrieved: {payload['source']['retrieved_at']}")
    print(f"Source: {payload['source']['url']}")
    print(f"Caveat: {payload['warnings'][0]}")


def print_error(exc: SkillError, *, as_json: bool) -> None:
    payload = {
        "ok": False,
        "error": exc.error_code,
        "message": str(exc),
        "blocked": exc.blocked,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"error: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_cli_args(argv)
    try:
        if args.command == "search":
            payload = search_payload(args)
        elif args.command == "get":
            payload = get_payload(args)
        else:
            payload = status_payload()
    except SkillError as exc:
        print_error(exc, as_json=getattr(args, "json", False))
        return exc.exit_code

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
