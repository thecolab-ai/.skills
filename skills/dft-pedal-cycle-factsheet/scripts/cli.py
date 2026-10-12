#!/usr/bin/env python3
"""Canonical Python CLI for dft-pedal-cycle-factsheet."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factsheet import (
    DEFAULT_PREVIEW,
    FACTSHEET_URL,
    LICENCE,
    MAX_ODS_BYTES,
    MAX_PREVIEW,
    PUBLISHER,
    FactsheetError,
    load_workbook,
)
from provenance import error_envelope, provenance, result_envelope

SHEET_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_. -]{0,79}")


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 100")
    number = int(value)
    if not 1 <= number <= MAX_PREVIEW:
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 100")
    return number


def read_fixture(path: str) -> bytes:
    try:
        with Path(path).open("rb") as handle:
            blob = handle.read(MAX_ODS_BYTES + 1)
    except OSError as exc:
        raise FactsheetError(2, "fixture file was not found") from exc
    if len(blob) > MAX_ODS_BYTES:
        raise FactsheetError(7, "fixture exceeds the ODS byte cap")
    return blob


def source_meta(source_url: str, latest_data: str | None) -> dict[str, str]:
    return provenance(source_url, PUBLISHER, licence=LICENCE, latest_data=latest_data)


def emit_error(code: int, message: str, as_json: bool, retry_after: str | None = None) -> int:
    meta = source_meta(FACTSHEET_URL, None)
    if as_json:
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"dft-pedal-cycle-factsheet: {message}", file=sys.stderr)
    return code


def render_text(record: dict[str, object], meta: dict[str, str]) -> str:
    lines = [
        str(record["publication"]),
        f"Publisher: {meta['publisher']}",
        f"Licence: {meta['licence']}",
    ]
    if meta.get("latest_data"):
        lines.append(f"First published: {meta['latest_data']}")
    if record.get("next_publication"):
        lines.append(f"Next publication: {record['next_publication']}")
    lines.append(f"Numeric cells: {record['numeric_cell_count']}")
    worksheets = record["worksheets"]
    if isinstance(worksheets, list):
        lines.append("Worksheets: " + ", ".join(str(name) for name in worksheets))
    if record.get("missing_data_note"):
        lines.append(f"Missing data: {record['missing_data_note']}")
    preview = record["numeric_preview"]
    if isinstance(preview, list):
        for cell in preview:
            if not isinstance(cell, dict):
                continue
            header = cell.get("column_header") or cell.get("column")
            unit = f" [{cell['unit']}]" if cell.get("unit") else ""
            display = cell.get("display") or "blank"
            lines.append(
                f"{cell['sheet']} row {cell['row']} {header}{unit}: "
                f"value {cell['value']}; display {display}"
            )
    semantic = record["semantic_preview"]
    if isinstance(semantic, list):
        for cell in semantic:
            if isinstance(cell, dict):
                lines.append(
                    f"{cell['sheet']} row {cell['row']} {cell.get('column_header') or cell['column']}: "
                    f"{cell['kind']} {cell['text']}"
                )
    if record.get("preview_truncated"):
        lines.append(f"Preview truncated at {record['preview_limit']} cells per kind.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = ArgumentParser(description="DfT pedal-cycle road casualty factsheet tables")
    sub = parser.add_subparsers(dest="command", required=True)
    tables = sub.add_parser(
        "tables",
        help="list pedal-cycle worksheets and a bounded preview of numeric cells",
    )
    tables.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    tables.add_argument(
        "--fixture",
        help="parse a local ODS fixture instead of downloading the official workbook",
    )
    tables.add_argument("--sheet", help="restrict the preview to one worksheet name")
    tables.add_argument(
        "--limit",
        type=parse_limit,
        default=DEFAULT_PREVIEW,
        help=f"maximum numeric and semantic preview cells (1-{MAX_PREVIEW}, default {DEFAULT_PREVIEW})",
    )
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        return emit_error(2, str(exc), "--json" in argv)
    as_json = bool(args.json)
    if args.sheet is not None and not SHEET_NAME.fullmatch(args.sheet):
        return emit_error(2, "--sheet must be a worksheet name", as_json)
    try:
        fixture = read_fixture(args.fixture) if args.fixture else None
        record, latest_data = load_workbook(fixture=fixture, limit=args.limit, sheet_name=args.sheet)
    except FactsheetError as exc:
        return emit_error(exc.code, str(exc), as_json, exc.retry_after)
    source_url = record["ods_url"] if record.get("read") == "live" and isinstance(record.get("ods_url"), str) else FACTSHEET_URL
    meta = source_meta(source_url, latest_data)
    if as_json:
        print(json.dumps(result_envelope([record], meta), indent=2, ensure_ascii=False))
    else:
        print(render_text(record, meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
