#!/usr/bin/env python3
"""Inspect ComCom telecommunications connectivity map public metadata."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
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
from typing import Any

BASE = "https://www.comcom.govt.nz"
CONNECTIVITY_URL = (
    BASE
    + "/regulated-industries/telecommunications/monitoring-the-telecommunications-market/"
    + "telecommunications-connectivity-map/"
)
ANNUAL_REPORT_URL = (
    BASE
    + "/regulated-industries/telecommunications/monitoring-the-telecommunications-market/"
    + "annual-monitoring-report/"
)
DEFAULT_TIMEOUT = 10
UA = "comcom-connectivity-map-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class SkillError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error", source_url: str | None = None):
        super().__init__(message)
        self.code = code
        self.source_url = source_url


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetched_at() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def absolute_url(base_url: str, href: str) -> str:
    return urllib.parse.urljoin(base_url, html.unescape(href))


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
            "Accept-Language": "en-NZ,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            return resp.read(), resp.geturl(), (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        raw = exc.read(800).decode("utf-8", "replace")
        if exc.code in {403, 429} or looks_like_bot_block(raw, ""):
            raise SkillError(
                f"HTTP {exc.code} from {url}; public source appears bot-blocked.",
                code="blocked_by_upstream",
                source_url=url,
            ) from exc
        raise SkillError(f"HTTP {exc.code} from {url}: {clean_text(raw)[:240]}", code="dead_link", source_url=url) from exc
    except TimeoutError as exc:
        raise SkillError(f"timeout while fetching {url}", code="network_timeout", source_url=url) from exc
    except urllib.error.URLError as exc:
        raise SkillError(f"network error contacting {url}: {exc.reason}", code="network_error", source_url=url) from exc


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    body, final_url, content_type = fetch_bytes(url, timeout=timeout)
    text = body.decode("utf-8", "replace")
    if looks_like_bot_block(text, content_type):
        raise SkillError(
            f"{url} returned an Incapsula/bot-challenge page instead of public content.",
            code="blocked_by_upstream",
            source_url=url,
        )
    return text, final_url


def looks_like_bot_block(body: str, content_type: str) -> bool:
    head = body[:4000].lower()
    return any(
        marker in head
        for marker in (
            "incapsula",
            "_incapsula_resource",
            "request unsuccessful",
            "access denied",
            "bot detection",
            "captcha",
        )
    ) and ("text/html" in content_type or "<html" in head or "<!doctype" in head)


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.iframes: list[str] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        if tag == "a":
            self._href = attrs_dict.get("href")
            self._text = []
        elif tag == "iframe" and attrs_dict.get("src"):
            self.iframes.append(absolute_url(self.base_url, attrs_dict["src"]))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append({"url": absolute_url(self.base_url, self._href), "label": clean_text(" ".join(self._text))})
            self._href = None
            self._text = []


def parse_links(raw_html: str, source_url: str) -> LinkParser:
    parser = LinkParser(source_url)
    parser.feed(raw_html)
    parser.close()
    return parser


def link_format(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    match = re.search(r"\.([a-z0-9]+)$", path)
    return match.group(1) if match else ""


def year_from_text(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text)
    return int(match.group(1)) if match else None


def date_from_text(text: str) -> str | None:
    match = re.search(r"(\d{1,2})[\s-]+([A-Za-z]+)[\s-]+(20\d{2})", text)
    if not match:
        return None
    day, month_name, year = match.groups()
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    month = months.get(month_name.lower())
    if not month:
        return None
    return dt.date(int(year), month, int(day)).isoformat()


def parse_coverage_date(raw_html: str) -> str | None:
    text = clean_text(raw_html)
    match = re.search(r"all the data is as at\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", text, re.I)
    if match:
        return date_from_text(match.group(1))
    return None


def year_from_iso_date(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(20\d{2})-", value)
    return int(match.group(1)) if match else None


def parse_provider_link(links: list[dict[str, str]]) -> dict[str, Any] | None:
    candidates = []
    for link in links:
        text = f"{link['label']} {link['url']}".lower()
        if "provider" in text and link_format(link["url"]) in {"xlsx", "xls", "csv"}:
            candidates.append(link)
    if not candidates:
        return None
    link = candidates[0]
    label = link["label"] or urllib.parse.unquote(link["url"].rsplit("/", 1)[-1])
    return {
        "label": label,
        "url": link["url"],
        "format": link_format(link["url"]),
        "updated": date_from_text(label),
        "fetch_method": "direct_http",
    }


def parse_layers(links: list[dict[str, str]], iframes: list[str]) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    terms = ("featureserver", "mapserver", "layerserver", "arcgis", "geoserver", "wms", "wfs")
    for url in [*iframes, *(link["url"] for link in links)]:
        low = url.lower()
        if any(term in low for term in terms) and url not in seen:
            seen.add(url)
            layers.append({"url": url, "kind": "public_map_layer", "fetch_method": "discovered_from_page"})
    return layers


def parse_connectivity_page(raw_html: str, source_url: str) -> dict[str, Any]:
    parser = parse_links(raw_html, source_url)
    provider_list = parse_provider_link(parser.links)
    coverage_date = parse_coverage_date(raw_html)
    parcel_threshold = None
    if re.search(r"at least\s+50%\s+of the parcel", raw_html, re.I):
        parcel_threshold = "50%"
    map_embed = None
    for iframe in parser.iframes:
        if "googletagmanager" not in iframe.lower():
            map_embed = iframe
            break
    return {
        "status": "ok",
        "source_url": source_url,
        "fetch_method": "direct_http",
        "coverage_date": coverage_date,
        "map": {
            "embed_url": map_embed,
            "public_address_level_data": False,
            "note": "ComCom publishes an interactive map view; address-level/orderability data are not exported by this skill.",
        },
        "provider_list": provider_list,
        "methodology": {
            "provider_supplied": True,
            "parcel_threshold": parcel_threshold,
            "update_cadence": "annual",
            "practical_availability_note": "Coverage indicates provider-supplied public coverage, not guaranteed orderability at a specific address.",
        },
        "layers": parse_layers(parser.links, parser.iframes),
    }


def report_priority(item: dict[str, Any]) -> int:
    label = str(item.get("label", "")).lower()
    if item.get("format") == "pdf" and "monitoring" in label and "infographic" not in label and "summary" not in label:
        return 0
    if item.get("format") == "pdf":
        return 1
    return 2


def parse_annual_reports(raw_html: str, source_url: str) -> list[dict[str, Any]]:
    parser = parse_links(raw_html, source_url)
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        text = f"{link['label']} {link['url']}"
        fmt = link_format(link["url"])
        if fmt not in {"pdf", "xlsx", "xls"}:
            continue
        if not re.search(r"(telecommunications|questionnaire|monitoring)", text, re.I):
            continue
        year = year_from_text(text)
        if not year or link["url"] in seen:
            continue
        seen.add(link["url"])
        reports.append(
            {
                "year": year,
                "label": link["label"] or urllib.parse.unquote(link["url"].rsplit("/", 1)[-1]),
                "url": link["url"],
                "format": fmt,
                "release_date": date_from_text(text),
                "fetch_method": "direct_http",
            }
        )
    reports.sort(key=lambda item: (-item["year"], report_priority(item), item["label"]))
    return reports


def first_worksheet_rows(xlsx_bytes: bytes, limit: int = 100) -> list[dict[str, str]]:
    with zipfile.ZipFile(BytesIO(xlsx_bytes)) as zf:
        shared = read_shared_strings(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        first_sheet = workbook.find("a:sheets/a:sheet", XLSX_NS)
        if first_sheet is None:
            return []
        rel_id = first_sheet.attrib.get(OFFICE_REL)
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels:
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target")
                break
        if not target:
            return []
        sheet_path = "xl/" + target.lstrip("/")
        rows = parse_sheet_rows(zf.read(sheet_path), shared)
    if not rows:
        return []
    header_index = 0
    for idx, row in enumerate(rows[:10]):
        populated = [cell for cell in row if cell]
        if len(populated) >= 2:
            header_index = idx
            break
    headers = [value or f"column_{idx + 1}" for idx, value in enumerate(rows[header_index])]
    records: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        if not any(row):
            continue
        record = {headers[idx]: row[idx] if idx < len(row) else "" for idx in range(len(headers))}
        records.append(record)
        if len(records) >= limit:
            break
    return records


def read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root.findall("a:si", XLSX_NS):
        parts = [node.text or "" for node in item.findall(".//a:t", XLSX_NS)]
        strings.append(clean_text("".join(parts)))
    return strings


def parse_sheet_rows(sheet_xml: bytes, shared: list[str]) -> list[list[str]]:
    root = ET.fromstring(sheet_xml)
    rows: list[list[str]] = []
    for row_node in root.findall(".//a:sheetData/a:row", XLSX_NS):
        row: list[str] = []
        for cell in row_node.findall("a:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            col = column_index(ref)
            while len(row) < col:
                row.append("")
            value = cell_value(cell, shared)
            row.append(value)
        rows.append(row)
    return rows


def column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    total = 0
    for char in letters:
        total = total * 26 + (ord(char) - ord("A") + 1)
    return max(total - 1, 0)


def cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return clean_text("".join(node.text or "" for node in cell.findall(".//a:t", XLSX_NS)))
    value_node = cell.find("a:v", XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return value
    return clean_text(value)


def annual_reports() -> list[dict[str, Any]]:
    raw_html, final_url = fetch_text(ANNUAL_REPORT_URL)
    return parse_annual_reports(raw_html, final_url)


def connectivity_metadata() -> dict[str, Any]:
    raw_html, final_url = fetch_text(CONNECTIVITY_URL)
    metadata = parse_connectivity_page(raw_html, final_url)
    metadata["fetched_at"] = fetched_at()
    metadata["map_data_year"] = year_from_iso_date(metadata.get("coverage_date"))
    metadata["current_map_only"] = True
    return metadata


def report_for_year(year: int) -> dict[str, Any] | None:
    reports = annual_reports()
    exact = [item for item in reports if item["year"] == year and item["format"] == "pdf"]
    if exact:
        return exact[0]
    fallback = [item for item in reports if item["year"] == year]
    return fallback[0] if fallback else None


def year_context(metadata: dict[str, Any], requested_year: int) -> dict[str, Any]:
    map_year = metadata.get("map_data_year")
    supported = map_year == requested_year
    return {
        "requested_year": requested_year,
        "map_data_year": map_year,
        "current_map_only": True,
        "year_supported_for_map": supported,
        "year_note": (
            "ComCom's public connectivity map is a current point-in-time map. "
            f"The fetched map data year is {map_year}; annual report links can cover older years."
            if map_year and not supported
            else "Requested year matches the current public connectivity map data year."
        ),
    }


def emit(payload: dict[str, Any], json_flag: bool) -> None:
    if json_flag:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)


def print_human(payload: dict[str, Any]) -> None:
    command = payload.get("command")
    print(f"ComCom connectivity map: {payload.get('status', 'unknown')}")
    if payload.get("source_url"):
        print(f"  Source: {payload['source_url']}")
    if command == "list-years":
        for item in payload.get("years", []):
            print(f"  {item['year']}: {item['label']} ({item['format']})")
    elif command == "coverage-summary":
        print(f"  Coverage date: {payload.get('coverage_date') or 'unknown'}")
        print(f"  Map: {payload.get('map', {}).get('embed_url') or 'not found'}")
        if payload.get("annual_report"):
            print(f"  Annual report: {payload['annual_report']['url']}")
    elif command == "providers":
        provider = payload.get("provider_list") or {}
        print(f"  Provider list: {provider.get('url') or 'not found'}")
        for row in payload.get("providers", [])[:10]:
            print("  - " + "; ".join(f"{k}: {v}" for k, v in row.items() if v))
    elif command == "layer-metadata":
        if payload.get("layers"):
            for layer in payload["layers"]:
                print(f"  {layer['url']} ({layer.get('kind', 'layer')})")
        else:
            print("  No public downloadable map layers discovered on the ComCom page.")


def cmd_list_years(args: argparse.Namespace) -> int:
    reports = annual_reports()
    years: dict[int, dict[str, Any]] = {}
    for item in reports:
        years.setdefault(item["year"], item)
    payload = {
        "status": "ok",
        "command": "list-years",
        "source_url": ANNUAL_REPORT_URL,
        "fetch_method": "direct_http",
        "years": [years[year] for year in sorted(years, reverse=True)],
    }
    emit(payload, args.json)
    return 0


def cmd_coverage_summary(args: argparse.Namespace) -> int:
    metadata = connectivity_metadata()
    payload = {
        **metadata,
        "command": "coverage-summary",
        **year_context(metadata, args.year),
        "annual_report": report_for_year(args.year),
        "coverage_table_status": "report_pdf_linked",
        "coverage_table_note": "The public page links annual monitoring PDFs; this stdlib CLI does not text-extract PDF tables.",
    }
    emit(payload, args.json)
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    metadata = connectivity_metadata()
    context = year_context(metadata, args.year)
    provider = metadata.get("provider_list")
    rows: list[dict[str, str]] = []
    provider_status = "not_found"
    provider_error = None
    if provider and provider.get("url"):
        if context["year_supported_for_map"]:
            try:
                body, _, _ = fetch_bytes(provider["url"])
                if provider.get("format") == "xlsx":
                    rows = first_worksheet_rows(body, limit=args.limit)
                provider_status = "ok"
            except SkillError as exc:
                provider_status = exc.code
                provider_error = {"code": exc.code, "message": str(exc), "source_url": exc.source_url}
        else:
            provider_status = "year_not_available"
    payload = {
        "status": provider_status,
        "command": "providers",
        **context,
        "source_url": CONNECTIVITY_URL,
        "fetch_method": "direct_http",
        "provider_list": provider,
        "provider_fetch_status": provider_status,
        "provider_error": provider_error,
        "providers": rows,
        "count": len(rows),
        "note": "Provider rows come from ComCom's public provider list workbook; this is not an address-level availability export.",
    }
    emit(payload, args.json)
    return 0


def cmd_layer_metadata(args: argparse.Namespace) -> int:
    metadata = connectivity_metadata()
    layers = metadata.get("layers", [])
    context = year_context(metadata, args.year)
    status = "year_not_available" if not context["year_supported_for_map"] else ("ok" if layers else "not_discovered")
    payload = {
        "status": status,
        "command": "layer-metadata",
        **context,
        "source_url": CONNECTIVITY_URL,
        "fetch_method": "direct_http",
        "map": metadata.get("map"),
        "layers": layers,
        "note": "Only public map/GIS layer URLs directly discoverable from ComCom's page are reported.",
    }
    emit(payload, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect ComCom Telecommunications Connectivity Map public metadata and source caveats."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_years = sub.add_parser("list-years", help="list annual telecommunications monitoring report years")
    p_years.add_argument("--json", action="store_true", help="emit JSON")
    p_years.set_defaults(func=cmd_list_years)

    p_summary = sub.add_parser("coverage-summary", help="summarise map coverage metadata and annual report source")
    p_summary.add_argument("--year", type=int, required=True, help="report year, e.g. 2025")
    p_summary.add_argument("--json", action="store_true", help="emit JSON")
    p_summary.set_defaults(func=cmd_coverage_summary)

    p_providers = sub.add_parser("providers", help="inspect provider-list workbook metadata and preview rows")
    p_providers.add_argument("--year", type=int, required=True, help="coverage/report year, e.g. 2025")
    p_providers.add_argument("--limit", type=int, default=50, help="max workbook rows to preview")
    p_providers.add_argument("--json", action="store_true", help="emit JSON")
    p_providers.set_defaults(func=cmd_providers)

    p_layers = sub.add_parser("layer-metadata", help="report discoverable public map layer URLs, if any")
    p_layers.add_argument("--year", type=int, required=True, help="coverage/report year, e.g. 2025")
    p_layers.add_argument("--json", action="store_true", help="emit JSON")
    p_layers.set_defaults(func=cmd_layer_metadata)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SkillError as exc:
        payload = {"status": exc.code, "error": exc.code, "message": str(exc), "source_url": exc.source_url}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"comcom-connectivity-map: {exc}", file=sys.stderr)
        return 2 if exc.code == "blocked_by_upstream" else 1


if __name__ == "__main__":
    raise SystemExit(main())
