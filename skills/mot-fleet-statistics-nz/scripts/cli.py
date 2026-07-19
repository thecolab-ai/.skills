#!/usr/bin/env python3
"""Ministry of Transport annual fleet statistics CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SOURCE_PAGE = "https://www.transport.govt.nz/statistics-and-insights/fleet-statistics/sheet/annual-fleet-statistics"
APP_PAGE = "https://www.mot-dev.link/fleet/annual-motor-vehicle-fleet-statistics/"
DEFAULT_TIMEOUT = 10
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class SkillError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error", source_url: str | None = None):
        super().__init__(message)
        self.code = code
        self.source_url = source_url


class UpstreamBlocked(SkillError):
    pass


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def key_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def fetched_at() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


ALLOWED_SOURCE_HOSTS = {"www.transport.govt.nz", "www.mot-dev.link"}


def validate_source_url(url: str) -> urllib.parse.ParseResult:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise SkillError("invalid workbook URL", code="invalid_input", source_url=url) from exc
    if parsed.scheme == "file":
        return parsed
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_SOURCE_HOSTS:
        raise SkillError(
            "workbook URL must use a declared Ministry of Transport HTTPS host or file:// fixture",
            code="unsupported_source",
            source_url=url,
        )
    return parsed


def request_headers(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    is_asset = bool(re.search(r"\.(xlsx|xls|csv)$", parsed.path, re.I))
    accept = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,*/*;q=0.8"
        if is_asset
        else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )
    return {"Accept": accept, "Referer": f"{parsed.scheme}://{parsed.netloc}/"}


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str, str]:
    parsed = validate_source_url(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return path.read_bytes(), url, "application/octet-stream"
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            headers=request_headers(url),
            context=ssl.create_default_context(),
        )
    except nzfetch.Blocked as exc:
        raise UpstreamBlocked(
            f"Ministry of Transport blocked this HTTP request; the source is public but this network may be bot-blocked. {exc}",
            code="blocked",
            source_url=url,
        ) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc), code="upstream_http", source_url=url) from exc
    if b"_Incapsula_Resource" in body[:4000] or b"Request unsuccessful" in body[:4000]:
        raise UpstreamBlocked(
            "Ministry of Transport returned an Incapsula challenge page instead of the requested data.",
            code="blocked",
            source_url=final_url,
        )
    validate_source_url(final_url)
    return body, final_url, content_type


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    body, final_url, _ = fetch_bytes(url, timeout=timeout)
    return body.decode("utf-8", errors="replace"), final_url


class WorkbookLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.release_notes: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []
        self._all_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if data:
            self._all_text.append(data)
        if self._href:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            label = clean_text(" ".join(self._link_text))
            url = urllib.parse.urljoin(self.base_url, self._href)
            if ".xlsx" in url.lower() or "spreadsheet" in label.lower() or "xlsx" in label.lower():
                self.links.append({"label": label or urllib.parse.unquote(url.rsplit("/", 1)[-1]), "url": url, "format": "xlsx"})
            self._href = None
            self._link_text = []

    def close(self) -> None:
        super().close()
        page_text = clean_text(" ".join(self._all_text))
        self.release_notes = re.findall(r"Version\s+[\d.]+:\s*[^.]+(?:\.)?", page_text)


def discover_workbook(timeout: int) -> dict[str, Any]:
    text, final_url = fetch_text(SOURCE_PAGE, timeout=timeout)
    parser = WorkbookLinkParser(final_url)
    parser.feed(text)
    parser.close()
    links = parser.links
    return {
        "status": "ok",
        "source_url": final_url,
        "workbooks": links,
        "workbook_url": links[0]["url"] if links else None,
        "release_notes": parser.release_notes,
    }


def blocked_payload(exc: UpstreamBlocked, *, kind: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "kind": kind,
        "code": exc.code,
        "source_url": exc.source_url,
        "message": str(exc),
        "note": "The source is public but blocked this HTTP client; use the source_url in a browser or pass --url file:///path/to/NZVehicleFleet_2024.xlsx.",
    }


def workbook_url_or_discover(url: str | None, timeout: int) -> tuple[str, dict[str, Any] | None]:
    if url:
        return url, None
    discovery = discover_workbook(timeout)
    workbook_url = discovery.get("workbook_url")
    if not workbook_url:
        raise SkillError("could not find a workbook link on the official source page", code="workbook_not_found", source_url=SOURCE_PAGE)
    return str(workbook_url), discovery


def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")) for si in root.findall("a:si", XLSX_NS)]


def workbook_sheets(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    sheets: dict[str, str] = {}
    for sheet in workbook.findall("a:sheets/a:sheet", XLSX_NS):
        name = sheet.attrib.get("name", "")
        rid = sheet.attrib.get(OFFICE_REL, "")
        target = relmap.get(rid, "")
        if not name or not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target.lstrip("/")
        sheets[name] = path
    return sheets


def col_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return max(value - 1, 0)


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return clean_text("".join(t.text or "" for t in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    value = cell.find("a:v", XLSX_NS)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell.attrib.get("t") == "s":
        try:
            return clean_text(strings[int(raw)])
        except (ValueError, IndexError):
            return clean_text(raw)
    return clean_text(raw)


class Workbook:
    def __init__(self, blob: bytes, source_url: str, content_type: str) -> None:
        try:
            self.zf = zipfile.ZipFile(BytesIO(blob))
        except zipfile.BadZipFile as exc:
            raise SkillError(f"invalid XLSX workbook: {exc}", code="invalid_xlsx", source_url=source_url) from exc
        self.source_url = source_url
        self.content_type = content_type
        self.sheets = workbook_sheets(self.zf)
        self.strings = shared_strings(self.zf)
        if not self.sheets:
            raise SkillError("XLSX workbook contains no worksheets", code="no_sheets", source_url=source_url)

    def rows(self, sheet_name: str) -> list[list[str]]:
        if sheet_name not in self.sheets:
            raise SkillError(f"sheet {sheet_name!r} not found; available sheets: {', '.join(self.sheets)}", code="missing_sheet", source_url=self.source_url)
        root = ET.fromstring(self.zf.read(self.sheets[sheet_name]))
        rows: list[list[str]] = []
        for row in root.findall("a:sheetData/a:row", XLSX_NS):
            values: list[str] = []
            for cell in row.findall("a:c", XLSX_NS):
                idx = col_index(cell.attrib.get("r", "A1"))
                while len(values) <= idx:
                    values.append("")
                values[idx] = cell_text(cell, self.strings)
            while values and values[-1] == "":
                values.pop()
            if any(values):
                rows.append(values)
        return rows


def load_workbook(url: str, timeout: int) -> Workbook:
    blob, final_url, content_type = fetch_bytes(url, timeout=timeout)
    if b"<html" in blob[:300].lower() and not final_url.startswith("file://"):
        raise SkillError("expected an XLSX workbook but received HTML", code="not_workbook", source_url=final_url)
    return Workbook(blob, final_url, content_type)


def parse_year(value: str) -> int | None:
    text = clean_text(value).replace(".0", "")
    return int(text) if re.fullmatch(r"19\d{2}|20\d{2}", text) else None


def sheet_summary(workbook: Workbook, sheet_name: str) -> dict[str, Any]:
    rows = workbook.rows(sheet_name)
    preview = rows[:8]
    years = sorted({year for row in rows[:80] for cell in row if (year := parse_year(cell)) is not None})
    return {
        "sheet": sheet_name,
        "row_count": len(rows),
        "preview": preview,
        "years": years,
        "table_codes": sorted(set(re.findall(r"\b\d+\.\d+[a-z]?\b", " ".join(" ".join(row) for row in preview), re.I))),
    }


def select_sheets(workbook: Workbook, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    for sheet in workbook.sheets:
        rows = workbook.rows(sheet)
        haystack = f"{sheet} {' '.join(' '.join(row) for row in rows[:12])}"
        if any(pattern.search(haystack) for pattern in compiled):
            matches.append(sheet)
    return matches


def count_table_sheet(sheet_name: str, rows: list[list[str]]) -> bool:
    haystack = key_text(f"{sheet_name} {' '.join(' '.join(row) for row in rows[:12])}")
    if re.search(r"\b8\s+2[a-z]?\b", haystack) or any(term in haystack for term in ("vkt", "kilometres travelled", "travel by fuel", "fleet travel")):
        return False
    if re.search(r"\b8\s+[45]\b", haystack):
        return True
    return any(term in haystack for term in ("fleet by main fuel", "light fleet fuel", "powertrain count", "fuel count", "fleet count by fuel"))


def select_count_sheets(workbook: Workbook) -> list[str]:
    matches: list[str] = []
    for sheet in workbook.sheets:
        if count_table_sheet(sheet, workbook.rows(sheet)):
            matches.append(sheet)
    return matches


def records_for_year(rows: list[list[str]], year: int, limit: int) -> list[dict[str, Any]]:
    header_index = None
    year_columns: list[int] = []
    for idx, row in enumerate(rows[:80]):
        cols = [pos for pos, value in enumerate(row) if parse_year(value) == year]
        if cols:
            header_index = idx
            year_columns = cols
            break
    if header_index is None:
        return []
    headers = rows[header_index]
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        descriptors: dict[str, str] = {}
        for pos, value in enumerate(row[: min(year_columns)]):
            if value:
                label = headers[pos] if pos < len(headers) and headers[pos] else f"dimension_{pos + 1}"
                descriptors[key_text(label).replace(" ", "_") or f"dimension_{pos + 1}"] = value
        for pos in year_columns:
            value = row[pos] if pos < len(row) else ""
            if value:
                records.append({"row_number": row_number, "year": year, "value": value, "dimensions": descriptors})
                if len(records) >= limit:
                    return records
    return records


def workbook_payload(url: str, sheet: str | None, limit: int, timeout: int) -> dict[str, Any]:
    workbook = load_workbook(url, timeout)
    selected = sheet or next(iter(workbook.sheets))
    rows = workbook.rows(selected)
    return {
        "status": "ok",
        "kind": "workbook_rows",
        "source_url": workbook.source_url,
        "content_type": workbook.content_type,
        "fetched_at": fetched_at(),
        "sheets": list(workbook.sheets),
        "sheet": selected,
        "row_count": len(rows),
        "rows": rows[:limit],
    }


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload.get("status") == "blocked":
        print(payload.get("message", "Source blocked."))
        print(payload.get("note", ""))
        return
    print(f"{payload.get('kind', 'result')}: {payload.get('status', 'ok')}")
    if payload.get("source_url"):
        print(f"Source: {payload['source_url']}")
    if payload.get("workbooks"):
        for item in payload["workbooks"]:
            print(f"- {item.get('label')}: {item.get('url')}")
    if payload.get("records"):
        for row in payload["records"][:10]:
            print(row)


def cmd_datasets(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "status": "ok",
        "kind": "datasets",
        "source": {
            "title": "Ministry of Transport Annual fleet statistics",
            "source_url": SOURCE_PAGE,
            "app_url": APP_PAGE,
            "coverage": "annual New Zealand historical motor vehicle fleet statistics, currently 2000-2024 on the public 2024 tool",
        },
        "caveats": [
            "The public source can be bot-blocked from direct HTTP clients; use a browser-downloaded workbook with --url file:// when needed.",
            "Hybrid and PHEV VKT should not be split unless the source workbook publishes those categories directly.",
        ],
    }
    try:
        discovery = discover_workbook(args.timeout)
        payload.update({"workbook_discovery": discovery, "release_notes": discovery.get("release_notes", [])})
    except UpstreamBlocked as exc:
        payload["workbook_discovery"] = blocked_payload(exc, kind="workbook_discovery")
        payload["release_notes"] = []
        payload["release_notes_status"] = "blocked"
    print_payload(payload, args.json)


def cmd_tables(args: argparse.Namespace) -> None:
    try:
        url, discovery = workbook_url_or_discover(args.url, args.timeout)
        workbook = load_workbook(url, args.timeout)
        payload = {
            "status": "ok",
            "kind": "tables",
            "source_url": workbook.source_url,
            "fetched_at": fetched_at(),
            "discovery": discovery,
            "tables": [sheet_summary(workbook, sheet) for sheet in workbook.sheets],
        }
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="tables")
    print_payload(payload, args.json)


def focused_payload(args: argparse.Namespace, kind: str, patterns: list[str], notes: list[str]) -> dict[str, Any]:
    url, discovery = workbook_url_or_discover(args.url, args.timeout)
    workbook = load_workbook(url, args.timeout)
    sheets = select_sheets(workbook, patterns)
    records: list[dict[str, Any]] = []
    for sheet in sheets:
        for record in records_for_year(workbook.rows(sheet), args.year, args.limit):
            record["sheet"] = sheet
            records.append(record)
            if len(records) >= args.limit:
                break
        if len(records) >= args.limit:
            break
    return {
        "status": "ok",
        "kind": kind,
        "year": args.year,
        "source_url": workbook.source_url,
        "fetched_at": fetched_at(),
        "discovery": discovery,
        "matched_sheets": sheets,
        "records": records,
        "record_count": len(records),
        "notes": notes,
    }


def fuel_counts_payload(args: argparse.Namespace) -> dict[str, Any]:
    url, discovery = workbook_url_or_discover(args.url, args.timeout)
    workbook = load_workbook(url, args.timeout)
    sheets = select_count_sheets(workbook)
    records: list[dict[str, Any]] = []
    for sheet in sheets:
        for record in records_for_year(workbook.rows(sheet), args.year, args.limit):
            record["sheet"] = sheet
            records.append(record)
            if len(records) >= args.limit:
                break
        if len(records) >= args.limit:
            break
    return {
        "status": "ok",
        "kind": "fuel_counts",
        "year": args.year,
        "source_url": workbook.source_url,
        "fetched_at": fetched_at(),
        "discovery": discovery,
        "matched_sheets": sheets,
        "records": records,
        "record_count": len(records),
        "notes": ["Rows come from workbook sheets matching light-fleet fuel or powertrain count table codes and headings."],
    }


def cmd_vkt(args: argparse.Namespace) -> None:
    try:
        payload = focused_payload(
            args,
            "vkt",
            [r"\b8\.2[a-z]?\b", r"vehicle kilometres|kilometres travelled|vkt|travel by fuel|fleet travel"],
            ["VKT means vehicle kilometres travelled.", "Do not infer hybrid/PHEV VKT splits unless a source table publishes them."],
        )
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="vkt")
    print_payload(payload, args.json)


def cmd_fuel_counts(args: argparse.Namespace) -> None:
    try:
        payload = fuel_counts_payload(args)
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="fuel_counts")
    print_payload(payload, args.json)


def cmd_workbook(args: argparse.Namespace) -> None:
    try:
        payload = workbook_payload(args.url, args.sheet, args.limit, args.timeout)
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="workbook")
    print_payload(payload, args.json)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout in seconds")


def add_workbook_url(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", help="public XLSX URL or local file:// workbook path")
    parser.add_argument("--limit", type=int, default=100, help="maximum rows or records to return")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query NZ Ministry of Transport annual fleet workbook tables")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("datasets", help="show official source pages, discovery status, and caveats")
    add_common(cmd)
    cmd.set_defaults(func=cmd_datasets)

    cmd = sub.add_parser("tables", help="list workbook sheets and preview headings")
    add_common(cmd)
    add_workbook_url(cmd)
    cmd.set_defaults(func=cmd_tables)

    cmd = sub.add_parser("vkt", help="return annual VKT rows for a year")
    add_common(cmd)
    add_workbook_url(cmd)
    cmd.add_argument("--year", type=int, required=True)
    cmd.set_defaults(func=cmd_vkt)

    cmd = sub.add_parser("fuel-counts", help="return light-fleet fuel or powertrain count rows for a year")
    add_common(cmd)
    add_workbook_url(cmd)
    cmd.add_argument("--year", type=int, required=True)
    cmd.set_defaults(func=cmd_fuel_counts)

    cmd = sub.add_parser("workbook", help="parse a direct public XLSX workbook URL or local file:// path")
    add_common(cmd)
    cmd.add_argument("--url", required=True, help="public XLSX URL or local file:// workbook path")
    cmd.add_argument("--sheet", help="worksheet name to parse")
    cmd.add_argument("--limit", type=int, default=50)
    cmd.set_defaults(func=cmd_workbook)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SkillError as exc:
        payload = {"status": "error", "code": exc.code, "message": str(exc), "source_url": exc.source_url}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
