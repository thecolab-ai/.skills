#!/usr/bin/env python3
"""Education Counts teacher workforce CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any

BASE = "https://www.educationcounts.govt.nz"
DEFAULT_TIMEOUT = 10
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

DATASETS: dict[str, dict[str, Any]] = {
    "ite": {
        "title": "Initial teacher education statistics",
        "source_url": f"{BASE}/statistics/initial-teacher-education-statistics",
        "release_date": "discover from live page",
        "notes": "Overview page includes rounded first-time domestic enrolment and first qualification completion tables.",
    },
    "teacher-movement": {
        "title": "Entering and leaving teaching",
        "source_url": f"{BASE}/statistics/teacher-movement",
        "release_date": "discover from live page",
        "notes": "Entering and leaving data workbooks are discovered from the live page.",
    },
    "teacher-turnover": {
        "title": "Teacher turnover",
        "source_url": f"{BASE}/statistics/teacher-turnover",
        "release_date": "discover from live page",
        "notes": "Regular teacher turnover workbook resources are discovered from the live page.",
    },
    "teacher-numbers": {
        "title": "Teacher numbers",
        "source_url": f"{BASE}/statistics/teacher-numbers",
        "release_date": "discover from live page",
        "notes": "Headcount, FTTE, pivot, and school-level workbook resources are discovered from the live page.",
    },
    "tds": {
        "title": "Teacher Demand and Supply Planning Projection",
        "source_url": f"{BASE}/publications/series/a-summary-of-the-teacher-demand-and-supply-planning-tool",
        "release_date": "discover from live page",
        "notes": "Publication series discovery for annual projection result pages; detailed projection tables require reachable source documents.",
    },
}


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


def request_headers(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    is_asset = bool(re.search(r"\.(xlsx|xls|csv|pdf)$", parsed.path, re.I))
    accept = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/pdf,text/csv,*/*;q=0.8"
        if is_asset
        else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    )
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": accept,
        "Accept-Language": "en-NZ,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        "Sec-Fetch-Dest": "document" if not is_asset else "empty",
        "Sec-Fetch-Mode": "navigate" if not is_asset else "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": '"Chromium";v="146", "Not A(Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str, str]:
    if url.startswith("file://"):
        path = Path(urllib.parse.urlparse(url).path)
        return path.read_bytes(), url, "application/octet-stream"
    req = urllib.request.Request(url, headers=request_headers(url))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            return resp.read(), resp.geturl(), (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = clean_text(exc.read(600).decode("utf-8", errors="replace"))[:240]
        except Exception:
            snippet = ""
        if exc.code in {403, 429}:
            raise UpstreamBlocked(
                f"HTTP {exc.code} from Education Counts; the public source may be bot-blocking this network. {snippet}",
                code="blocked",
                source_url=url,
            ) from exc
        raise SkillError(f"HTTP {exc.code} from {url}. {snippet}", code="upstream_http", source_url=url) from exc
    except TimeoutError as exc:
        raise UpstreamBlocked(f"timeout while fetching {url}", code="timeout", source_url=url) from exc
    except urllib.error.URLError as exc:
        raise UpstreamBlocked(f"network error contacting {url}: {exc.reason}", code="unreachable", source_url=url) from exc


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    body, final_url, _ = fetch_bytes(url, timeout=timeout)
    return body.decode("utf-8", errors="replace"), final_url


def extension_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    match = re.search(r"\.([a-z0-9]+)$", path)
    return match.group(1) if match else ""


class ResourceParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.heading = ""
        self.links: list[dict[str, Any]] = []
        self.release_date: str | None = None
        self._page_text: list[str] = []
        self._heading_tag: str | None = None
        self._heading_text: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        if tag in {"h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_text = []
        elif tag == "a":
            self._href = attrs_dict.get("href")
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if data:
            self._page_text.append(data)
        if self._heading_tag:
            self._heading_text.append(data)
        if self._href:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            text = clean_text(" ".join(self._heading_text))
            if text:
                self.heading = text
            self._heading_tag = None
            self._heading_text = []
        elif tag == "a" and self._href:
            url = urllib.parse.urljoin(self.base_url, self._href)
            ext = extension_from_url(url)
            if ext in {"xlsx", "xls", "csv", "pdf"}:
                label = clean_text(" ".join(self._link_text)) or urllib.parse.unquote(url.rsplit("/", 1)[-1])
                self.links.append(
                    {
                        "label": label,
                        "section": self.heading,
                        "url": url,
                        "format": ext,
                        "resource_key": resource_key(label, url),
                    }
                )
            self._href = None
            self._link_text = []

    def close(self) -> None:
        super().close()
        match = re.search(r"(?:Last updated|Date Published):\s*([A-Za-z]+\s+20\d{2}|Various)", clean_text(" ".join(self._page_text)), re.I)
        if match:
            self.release_date = match.group(1)


class PublicationParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self.release_date: str | None = None
        self._page_text: list[str] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs_dict = {name: value or "" for name, value in attrs}
            self._href = attrs_dict.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if data:
            self._page_text.append(data)
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            label = clean_text(" ".join(self._text))
            if "teacher demand" in label.lower() and "supply" in label.lower():
                year_match = re.search(r"(20\d{2})", label)
                self.items.append(
                    {
                        "title": label,
                        "year": int(year_match.group(1)) if year_match else None,
                        "url": urllib.parse.urljoin(self.base_url, self._href),
                    }
                )
            self._href = None
            self._text = []

    def close(self) -> None:
        super().close()
        match = re.search(r"Date Published:\s*([A-Za-z]+\s+20\d{2}|Various)", clean_text(" ".join(self._page_text)), re.I)
        if match:
            self.release_date = match.group(1)


def resource_key(label: str, url: str) -> str:
    text = key_text(f"{label} {urllib.parse.unquote(url)}")
    if "turnover" in text and "rate" in text:
        return "turnover-rates"
    if "turnover" in text and "number" in text:
        return "turnover-numbers"
    if "entering" in text and "rate" in text:
        return "entering-rates"
    if "entering" in text and "number" in text:
        return "entering-numbers"
    if "leaving" in text and "rate" in text:
        return "leaving-rates"
    if "leaving" in text and "number" in text:
        return "leaving-numbers"
    if "ftte" in text:
        return "ftte"
    if "headcount" in text:
        return "headcount"
    if "by school" in text:
        return "school"
    if "pivot" in text:
        return "pivot"
    if "completion" in text:
        return "ite-completions"
    if "enrol" in text:
        return "ite-enrolments"
    return re.sub(r"-+", "-", text.replace(" ", "-")).strip("-")[:80] or "resource"


def discover_resources(dataset: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    if dataset not in DATASETS:
        raise SkillError(f"unknown dataset {dataset!r}; choose one of {', '.join(DATASETS)}", code="bad_dataset")
    meta = DATASETS[dataset]
    text, final_url = fetch_text(meta["source_url"], timeout=timeout)
    parser = ResourceParser(final_url)
    parser.feed(text)
    parser.close()
    return {
        "status": "ok",
        "kind": "resources",
        "dataset": dataset,
        "title": meta["title"],
        "source_url": final_url,
        "release_date": parser.release_date or meta["release_date"],
        "fetched_at": fetched_at(),
        "count": len(parser.links),
        "resources": parser.links,
    }


def discover_tds_publications(timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    meta = DATASETS["tds"]
    text, final_url = fetch_text(meta["source_url"], timeout=timeout)
    parser = PublicationParser(final_url)
    parser.feed(text)
    parser.close()
    return {
        "status": "ok",
        "kind": "tds_publications",
        "source_url": final_url,
        "release_date": parser.release_date or meta["release_date"],
        "fetched_at": fetched_at(),
        "publications": parser.items,
    }


def tds_publication_details(publications: list[dict[str, Any]], timeout: int) -> list[dict[str, Any]]:
    detailed = []
    for publication in publications:
        item = dict(publication)
        try:
            text, final_url = fetch_text(str(publication["url"]), timeout=timeout)
            parser = ResourceParser(final_url)
            parser.feed(text)
            parser.close()
            item["source_url"] = final_url
            item["release_date"] = parser.release_date
            item["resources"] = parser.links
            item["resource_count"] = len(parser.links)
        except UpstreamBlocked as exc:
            item["status"] = "blocked"
            item["code"] = exc.code
            item["message"] = str(exc)
            item["source_url"] = exc.source_url
        detailed.append(item)
    return detailed


def blocked_payload(exc: UpstreamBlocked, *, kind: str, dataset: str | None = None) -> dict[str, Any]:
    payload = {
        "status": "blocked",
        "kind": kind,
        "code": exc.code,
        "message": str(exc),
        "source_url": exc.source_url,
        "fetched_at": fetched_at(),
        "note": "The source is public but blocked this HTTP client; use the source_url in a browser or retry from another network.",
    }
    if dataset:
        payload["dataset"] = dataset
        payload["manifest"] = DATASETS.get(dataset)
    return payload


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
        target = relmap.get(rid)
        if name and target:
            sheets[name] = target.lstrip("/") if target.startswith("/") else "xl/" + target.lstrip("/")
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


def xlsx_rows(blob: bytes, sheet_name: str | None = None) -> tuple[list[list[str]], list[str], str]:
    try:
        zf = zipfile.ZipFile(BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise SkillError(f"invalid XLSX workbook: {exc}", code="invalid_xlsx") from exc
    sheets = workbook_sheets(zf)
    if not sheets:
        raise SkillError("XLSX workbook contains no worksheets", code="no_sheets")
    selected = sheet_name if sheet_name in sheets else next(iter(sheets))
    if sheet_name and sheet_name not in sheets:
        raise SkillError(f"sheet {sheet_name!r} not found; available sheets: {', '.join(sheets)}", code="missing_sheet")
    strings = shared_strings(zf)
    root = ET.fromstring(zf.read(sheets[selected]))
    rows: list[list[str]] = []
    for row in root.findall("a:sheetData/a:row", XLSX_NS):
        values: list[str] = []
        for cell in row.findall("a:c", XLSX_NS):
            idx = col_index(cell.attrib.get("r", "A1"))
            while len(values) <= idx:
                values.append("")
            values[idx] = cell_text(cell, strings)
        while values and values[-1] == "":
            values.pop()
        if any(values):
            rows.append(values)
    return rows, list(sheets), selected


def parse_year(value: str) -> int | None:
    text = clean_text(value).replace(".0", "")
    return int(text) if re.fullmatch(r"20\d{2}|19\d{2}", text) else None


def long_records(rows: list[list[str]], from_year: int | None, to_year: int | None, limit: int) -> list[dict[str, Any]]:
    header_index = None
    year_columns: list[tuple[int, int]] = []
    for idx, row in enumerate(rows[:80]):
        cols = [(pos, year) for pos, value in enumerate(row) if (year := parse_year(value)) is not None]
        if len(cols) >= 2:
            header_index = idx
            year_columns = cols
            break
    if header_index is None:
        return [{"row_number": i + 1, "values": row} for i, row in enumerate(rows[:limit])]

    label_headers = rows[header_index]
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        descriptors: dict[str, str] = {}
        for pos in range(0, year_columns[0][0]):
            if pos < len(row) and row[pos]:
                label = label_headers[pos] if pos < len(label_headers) and label_headers[pos] else f"dimension_{pos + 1}"
                descriptors[key_text(label).replace(" ", "_") or f"dimension_{pos + 1}"] = row[pos]
        if not descriptors and not any(pos < len(row) and row[pos] for pos, _ in year_columns):
            continue
        for pos, year in year_columns:
            if from_year and year < from_year:
                continue
            if to_year and year > to_year:
                continue
            value = row[pos] if pos < len(row) else ""
            if value == "":
                continue
            records.append({"row_number": row_number, "year": year, "value": value, "dimensions": descriptors})
            if len(records) >= limit:
                return records
    return records


def workbook_payload(url: str, sheet: str | None, from_year: int | None, to_year: int | None, limit: int, timeout: int) -> dict[str, Any]:
    blob, final_url, content_type = fetch_bytes(url, timeout=timeout)
    rows, sheets, selected = xlsx_rows(blob, sheet)
    return {
        "status": "ok",
        "kind": "workbook_rows",
        "source_url": final_url,
        "content_type": content_type,
        "fetched_at": fetched_at(),
        "sheets": sheets,
        "sheet": selected,
        "row_count": len(rows),
        "records": long_records(rows, from_year, to_year, limit),
    }


def choose_resource(dataset: str, desired_key: str, timeout: int) -> dict[str, Any]:
    payload = discover_resources(dataset, timeout=timeout)
    resources = payload.get("resources", [])
    exact = [r for r in resources if r.get("resource_key") == desired_key]
    if exact:
        return exact[0]
    fuzzy = [r for r in resources if desired_key in r.get("resource_key", "") or desired_key in key_text(r.get("label", ""))]
    if fuzzy:
        return fuzzy[0]
    raise SkillError(f"no {desired_key!r} workbook found on {payload.get('source_url')}", code="resource_not_found", source_url=payload.get("source_url"))


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    status = data.get("status")
    if status == "blocked":
        print(f"Blocked: {data.get('message')}")
        print(f"Source: {data.get('source_url')}")
        return
    kind = data.get("kind")
    if kind == "dataset_list":
        print("Education Counts teacher workforce datasets:")
        for item in data["datasets"]:
            print(f"- {item['name']}: {item['title']} ({item['release_date']})")
    elif kind == "resources":
        print(f"{data.get('title')}: {data.get('count')} resources")
        for item in data.get("resources", []):
            print(f"- {item['resource_key']}: {item['label']} [{item['format']}] {item['url']}")
    elif kind == "tds_publications":
        print("Teacher Demand and Supply Planning Projection publication pages:")
        for item in data["publications"]:
            suffix = f" ({item.get('resource_count')} resources)" if "resource_count" in item else ""
            print(f"- {item.get('year') or '-'}: {item['title']} {item.get('url', '')}{suffix}")
    elif kind == "workbook_rows":
        print(f"Workbook rows from {data.get('sheet')}: {len(data.get('records', []))} records shown")
        for row in data.get("records", [])[:20]:
            print("- " + json.dumps(row, ensure_ascii=False))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    emit(
        {
            "status": "ok",
            "kind": "dataset_list",
            "fetched_at": fetched_at(),
            "datasets": [{"name": name, **meta} for name, meta in DATASETS.items()],
        },
        args.json,
    )


def cmd_resources(args: argparse.Namespace) -> None:
    try:
        payload = discover_resources(args.dataset, timeout=args.timeout)
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="resources", dataset=args.dataset)
    emit(payload, args.json)


def cmd_ite_enrolments(args: argparse.Namespace) -> None:
    command_from_resource(args, "ite", "ite-enrolments")


def cmd_workbook(args: argparse.Namespace) -> None:
    try:
        payload = workbook_payload(args.url, args.sheet, args.from_year, args.to_year, args.limit, args.timeout)
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="workbook")
    emit(payload, args.json)


def command_from_resource(args: argparse.Namespace, dataset: str, desired_key: str) -> None:
    try:
        resource = choose_resource(dataset, desired_key, timeout=args.timeout)
        if resource.get("format") != "xlsx":
            raise SkillError(f"resource {resource.get('label')} is {resource.get('format')}, not parseable XLSX", code="unsupported_format", source_url=resource.get("url"))
        payload = workbook_payload(resource["url"], args.sheet, args.from_year, args.to_year, args.limit, args.timeout)
        payload["dataset"] = dataset
        payload["resource"] = resource
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="workbook", dataset=dataset)
    emit(payload, args.json)


def cmd_teacher_numbers(args: argparse.Namespace) -> None:
    command_from_resource(args, "teacher-numbers", args.resource)


def cmd_teacher_movement(args: argparse.Namespace) -> None:
    command_from_resource(args, "teacher-movement", f"{args.kind}-{args.measure}")


def cmd_teacher_turnover(args: argparse.Namespace) -> None:
    key = "pivot" if args.measure == "pivot" else f"turnover-{args.measure}"
    command_from_resource(args, "teacher-turnover", key)


def cmd_ite_completions(args: argparse.Namespace) -> None:
    try:
        resource = choose_resource("ite", "ite-completions", timeout=args.timeout)
        if resource.get("format") == "xlsx":
            payload = workbook_payload(resource["url"], args.sheet, args.from_year, args.to_year, args.limit, args.timeout)
            payload["dataset"] = "ite"
            payload["resource"] = resource
        else:
            payload = {"status": "ok", "kind": "ite_completions", "resource": resource, "note": "Completion source is listed but is not a parseable XLSX workbook."}
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="ite_completions", dataset="ite")
    emit(payload, args.json)


def cmd_tds(args: argparse.Namespace) -> None:
    try:
        payload = discover_tds_publications(timeout=args.timeout)
        if args.year is not None:
            payload["publications"] = [item for item in payload["publications"] if item.get("year") == args.year]
        if args.year is not None and payload["publications"]:
            payload["publications"] = tds_publication_details(payload["publications"], timeout=args.timeout)
            payload["note"] = "TDS publications currently expose PDF/DOC source documents; use source URLs for detailed projection assumptions when no XLSX is listed."
    except UpstreamBlocked as exc:
        payload = blocked_payload(exc, kind="tds_publications", dataset="tds")
    emit(payload, args.json)


def add_common_workbook_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sheet", help="worksheet name; defaults to the first sheet")
    parser.add_argument("--from", dest="from_year", type=int, help="minimum year")
    parser.add_argument("--to", dest="to_year", type=int, help="maximum year")
    parser.add_argument("--limit", type=int, default=100, help="maximum output records")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query Education Counts teacher workforce public data")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("list", help="list supported dataset families")
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(func=cmd_list)

    cmd = sub.add_parser("resources", help="discover workbook and PDF resources from a source page")
    cmd.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(func=cmd_resources)

    cmd = sub.add_parser("ite-enrolments", help="discover and parse first-time domestic ITE enrolment workbook rows")
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_ite_enrolments)

    cmd = sub.add_parser("ite-completions", help="discover or parse first ITE completion sources")
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_ite_completions)

    cmd = sub.add_parser("teacher-numbers", help="parse teacher number workbook rows")
    cmd.add_argument("--resource", choices=["headcount", "ftte", "pivot", "school"], default="headcount")
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_teacher_numbers)

    cmd = sub.add_parser("teacher-movement", help="parse entering/leaving teacher movement workbook rows")
    cmd.add_argument("--kind", choices=["entering", "leaving"], required=True)
    cmd.add_argument("--measure", choices=["numbers", "rates"], required=True)
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_teacher_movement)

    cmd = sub.add_parser("teacher-turnover", help="parse teacher turnover workbook rows")
    cmd.add_argument("--measure", choices=["numbers", "rates", "pivot"], default="rates")
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_teacher_turnover)

    cmd = sub.add_parser("tds", help="discover Teacher Demand and Supply Planning Projection publication pages")
    cmd.add_argument("--year", type=int)
    cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(func=cmd_tds)

    cmd = sub.add_parser("workbook", help="parse a direct public XLSX workbook URL or file:// path")
    cmd.add_argument("--url", required=True)
    add_common_workbook_flags(cmd)
    cmd.set_defaults(func=cmd_workbook)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except SkillError as exc:
        payload = {"status": "error", "code": exc.code, "message": str(exc), "source_url": exc.source_url}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"education-counts-nz: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            os._exit(1)


if __name__ == "__main__":
    main()
