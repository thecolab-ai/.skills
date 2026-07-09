#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.parse
import zipfile
from datetime import datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402


GETS_BASE = "https://www.gets.govt.nz"
GETS_RSS_URL = f"{GETS_BASE}/ExternalRSSFeed.htm"
GETS_STATUS_PATHS = {
    "open": "ExternalIndex.htm",
    "late": "ExternalLateTenderList.htm",
    "closed": "ExternalClosedTenderList.htm",
    "completed": "ExternalAwardedTenderList.htm",
    "awarded": "ExternalAwardedTenderList.htm",
}
GETS_SEARCH_PATH = "ExternalTenderSearching.htm"
GETS_DETAIL_URL = f"{GETS_BASE}/ExternalTenderDetails.htm"
CKAN_PACKAGE_URL = (
    "https://catalogue.data.govt.nz/api/3/action/package_show?"
    "id=new-zealand-government-procurement-award-notices"
)
MBIE_OPEN_DATA_PAGE = (
    "https://www.mbie.govt.nz/cross-government-functions/"
    "new-zealand-government-procurement-and-property/open-data"
)
SSC_PAGE = (
    "https://www.procurement.govt.nz/data-and-reporting/reporting/"
    "significant-service-contracts-framework/"
)
SSC_DASHBOARD_URL = (
    "https://www.procurement.govt.nz/assets/procurement-property/documents/"
    "significant-services-contract-dashboard.xlsx?m=ca63730c2622cedad7f919fed42e140be24ba4db"
)
class SkillError(Exception):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"gets-procurement-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_bytes(url: str, timeout: int = 10, accept: str = "*/*") -> bytes:
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            url, timeout=timeout, accept=accept, expect_json=False
        )
        return body
    except nzfetch.Blocked as exc:
        raise SkillError(f"network error calling {url}: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc)) from exc


def fetch_text(url: str, timeout: int = 10, accept: str = "text/html,*/*") -> str:
    try:
        return nzfetch.fetch_text(url, timeout=timeout, accept=accept)
    except nzfetch.Blocked as exc:
        raise SkillError(f"network error calling {url}: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc)) from exc


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalise_label(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("#", "number")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def absolute_url(url: str) -> str:
    url = urllib.parse.urljoin(GETS_BASE + "/", url)
    return url.replace("https://www.gets.govt.nz//", "https://www.gets.govt.nz/")


def maybe_none(value: str) -> str | None:
    value = clean_text(value)
    if not value or value == "[None]" or value.lower() == "none":
        return None
    return value


def excel_date(value: str) -> str | None:
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return maybe_none(value)
    # Excel's Windows epoch includes the 1900 leap-year bug.
    date = datetime(1899, 12, 30) + timedelta(days=serial)
    return date.date().isoformat()


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._link_href: str | None = None
        self._li_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"text": [], "hrefs": [], "items": [], "tag": tag}
        elif tag == "a" and self._cell is not None:
            href = attr.get("href")
            if href:
                self._link_href = href
                self._cell["hrefs"].append(href)
        elif tag == "li" and self._cell is not None:
            self._li_text = []
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._link_href = None
        elif tag == "li" and self._cell is not None and self._li_text is not None:
            item = clean_text("".join(self._li_text))
            if item:
                self._cell["items"].append(item)
            self._cell["text"].append("\n")
            self._li_text = None
        elif tag in {"td", "th"} and self._row is not None and self._cell is not None:
            text = clean_text("".join(self._cell["text"]))
            self._row.append(
                {
                    "text": text,
                    "hrefs": list(self._cell["hrefs"]),
                    "items": list(self._cell["items"]),
                    "tag": self._cell["tag"],
                }
            )
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell["text"] or cell["hrefs"] for cell in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)
            if self._li_text is not None:
                self._li_text.append(data)


class SectionTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_overview = False
        self._after_overview = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        if tag == "span" and attr.get("class") == "legend":
            self._after_overview = True
        elif tag in {"p", "br"} and self.in_overview:
            self.parts.append("\n")
        elif tag in {"form", "script"} and self.in_overview:
            self.in_overview = False

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._after_overview = False
        elif tag == "p" and self.in_overview:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        if self._after_overview and text == "Overview":
            self.in_overview = True
            self._after_overview = False
            return
        if self.in_overview:
            self.parts.append(data)

    def overview(self) -> str | None:
        text = clean_text(" ".join(self.parts))
        return text or None


def parse_table_rows(document: str) -> list[list[dict[str, Any]]]:
    parser = TableHTMLParser()
    parser.feed(document)
    return parser.rows


def row_to_cells(row: list[dict[str, Any]]) -> list[str]:
    return [clean_text(cell["text"]) for cell in row]


def parse_gets_list(document: str, source_url: str, status: str, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in parse_table_rows(document):
        cells = row_to_cells(row)
        if len(cells) < 6 or not re.fullmatch(r"\d{5,}", cells[0] or ""):
            continue
        link = None
        for cell in row:
            for href in cell["hrefs"]:
                if "ExternalTenderDetails.htm" in href:
                    link = absolute_url(href)
                    break
            if link:
                break
        record = {
            "rfx_id": cells[0],
            "reference": maybe_none(cells[1]),
            "title": maybe_none(cells[2]),
            "tender_type": maybe_none(cells[3]),
            "date": maybe_none(cells[4]),
            "organisation": maybe_none(cells[5]),
            "url": link,
            "status": "completed" if status == "awarded" else status,
            "source_url": source_url,
        }
        if status in {"completed", "awarded"}:
            record["award_date"] = record.pop("date")
        elif status == "closed":
            record["closed_date"] = record.pop("date")
        else:
            record["close_date"] = record.pop("date")
        records.append(record)
        if limit is not None and len(records) >= limit:
            break
    return records


def parse_description_table(description: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in parse_table_rows(description):
        cells = row_to_cells(row)
        if len(cells) >= 2:
            fields[normalise_label(cells[0])] = clean_text(cells[1])
    return fields


def parse_rss_items(document: bytes, limit: int | None = None) -> list[dict[str, Any]]:
    root = ET.fromstring(document)
    channel = root.find("channel")
    if channel is None:
        raise SkillError("GETS RSS feed did not contain a channel")
    dc = {"dc": "http://purl.org/dc/elements/1.1/"}
    records: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        description = item.findtext("description") or ""
        fields = parse_description_table(description)
        categories = [clean_text(c.text or "") for c in item.findall("category") if clean_text(c.text or "")]
        link = absolute_url(item.findtext("link") or "")
        record = {
            "rfx_id": maybe_none(fields.get("rfx_id", "")),
            "reference": maybe_none(fields.get("reference_number", "") or fields.get("reference", "")),
            "title": maybe_none(item.findtext("title") or ""),
            "tender_type": maybe_none(fields.get("tender_type", "")),
            "organisation": maybe_none(fields.get("organisation", "") or item.findtext("dc:creator", namespaces=dc) or ""),
            "open_date": maybe_none(fields.get("open_date", "")),
            "close_date": maybe_none(fields.get("close_date", "")),
            "categories": categories,
            "published": maybe_none(item.findtext("pubDate") or ""),
            "url": link or None,
            "status": "open",
            "source_url": GETS_RSS_URL,
        }
        if not record["rfx_id"]:
            match = re.search(r"[?&]id=(\d+)", link)
            if match:
                record["rfx_id"] = match.group(1)
        records.append(record)
        if limit is not None and len(records) >= limit:
            break
    return records


def parse_detail(document: str, source_url: str) -> dict[str, Any]:
    rows = parse_table_rows(document)
    fields: dict[str, Any] = {}
    for row in rows:
        cells = row_to_cells(row)
        if len(cells) != 2:
            continue
        key = normalise_label(cells[0])
        if not key:
            continue
        value = maybe_none(cells[1])
        if key in {"categories", "regions"} and value:
            fields[key] = row[1].get("items") or [value]
        else:
            fields[key] = value

    overview_parser = SectionTextParser()
    overview_parser.feed(document)
    title_match = re.search(r"<title>(.*?)</title>", document, re.S | re.I)
    page_title = clean_text(title_match.group(1)) if title_match else None
    rfx_id = fields.get("rfx_id")
    if not rfx_id:
        match = re.search(r"[?&]id=(\d+)", source_url)
        if match:
            rfx_id = match.group(1)
    return {
        "kind": "tender",
        "source": "GETS",
        "source_url": source_url,
        "rfx_id": rfx_id,
        "reference": fields.get("reference_number"),
        "title": fields.get("tender_name") or page_title,
        "open_date": fields.get("open_date"),
        "close_date": fields.get("close_date"),
        "tender_type": fields.get("tender_type"),
        "tender_coverage": fields.get("tender_coverage"),
        "organisation": organisation_from_title(page_title),
        "department_business_unit": fields.get("department_business_unit"),
        "categories": fields.get("categories") or [],
        "regions": fields.get("regions") or [],
        "exemption_reason": fields.get("exemption_reason"),
        "required_pre_qualifications": fields.get("required_pre_qualifications"),
        "contact": fields.get("contact"),
        "overview": overview_parser.overview(),
        "raw_fields": fields,
    }


def organisation_from_title(page_title: str | None) -> str | None:
    if not page_title or " | " not in page_title:
        return None
    after_bar = page_title.split("|", 1)[1].strip()
    if " - " not in after_bar:
        return None
    return after_bar.split(" - ", 1)[0].strip() or None


def build_url(path: str, params: dict[str, Any] | None = None) -> str:
    url = urllib.parse.urljoin(GETS_BASE + "/", path)
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if query:
            url = f"{url}?{query}"
    return url


def filter_records(records: list[dict[str, Any]], keyword: str | None = None, agency: str | None = None) -> list[dict[str, Any]]:
    keyword_l = keyword.lower() if keyword else None
    agency_l = agency.lower() if agency else None
    results = []
    for record in records:
        haystack = " ".join(str(record.get(k) or "") for k in ["title", "organisation", "reference", "rfx_id"]).lower()
        if keyword_l and keyword_l not in haystack:
            continue
        if agency_l and agency_l not in str(record.get("organisation") or "").lower():
            continue
        results.append(record)
    return results


def get_open_tenders(limit: int | None, timeout: int) -> list[dict[str, Any]]:
    data = fetch_bytes(GETS_RSS_URL, timeout=timeout, accept="application/rss+xml,application/xml,*/*")
    return parse_rss_items(data, limit=limit)


def get_status_tenders(status: str, page: int, limit: int | None, timeout: int) -> tuple[list[dict[str, Any]], str]:
    path = GETS_STATUS_PATHS[status]
    url = build_url(path, {"page": page if page != 1 else None})
    document = fetch_text(url, timeout=timeout)
    return parse_gets_list(document, url, status=status, limit=limit), url


def get_search_tenders(query: str, page: int, limit: int | None, timeout: int) -> tuple[list[dict[str, Any]], str]:
    url = build_url(GETS_SEARCH_PATH, {"SearchingText": query, "page": page if page != 1 else None})
    document = fetch_text(url, timeout=timeout)
    return parse_gets_list(document, url, status="search", limit=limit), url


def collect_awards(agency: str | None, pages: int, limit: int, timeout: int) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    urls: list[str] = []
    for page in range(1, pages + 1):
        page_records, url = get_status_tenders("completed", page, None, timeout)
        urls.append(url)
        records.extend(filter_records(page_records, agency=agency))
        if len(records) >= limit:
            break
    return records[:limit], urls


def ckan_award_sources(timeout: int) -> tuple[list[dict[str, Any]], str | None]:
    try:
        data = nzfetch.fetch_json(CKAN_PACKAGE_URL, timeout=timeout)
    except nzfetch.FetchError:
        return [], "data.govt.nz package lookup failed"
    if not data.get("success"):
        return [], f"data.govt.nz success=false: {data.get('error')}"
    resources = []
    for item in data.get("result", {}).get("resources", []):
        resources.append(
            {
                "name": item.get("name"),
                "format": item.get("format"),
                "url": item.get("url"),
                "resource_id": item.get("id"),
                "mimetype": item.get("mimetype"),
            }
        )
    return resources, None


def read_xlsx_rows(data: bytes, sheet_name: str) -> list[dict[str, str]]:
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    workbook = ET.fromstring(zipfile.ZipFile(BytesIO(data)).read("xl/workbook.xml"))
    rels = ET.fromstring(zipfile.ZipFile(BytesIO(data)).read("xl/_rels/workbook.xml.rels"))
    relationship_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("rel:Relationship", ns)}
    sheet_path = None
    for sheet in workbook.findall("main:sheets/main:sheet", ns):
        if sheet.attrib.get("name") == sheet_name:
            rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = relationship_targets.get(rid or "")
            if target:
                sheet_path = "xl/" + target
            break
    if not sheet_path:
        raise SkillError(f"sheet not found in significant services workbook: {sheet_name}")

    archive = zipfile.ZipFile(BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in strings.findall("main:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))

    def cell_value(cell: ET.Element) -> str:
        value_node = cell.find("main:v", ns)
        if value_node is None:
            return ""
        value = value_node.text or ""
        if cell.attrib.get("t") == "s" and value:
            return shared[int(value)]
        return value

    rows: list[dict[str, str]] = []
    sheet = ET.fromstring(archive.read(sheet_path))
    for row in sheet.findall(".//main:row", ns):
        values: dict[str, str] = {}
        for cell in row.findall("main:c", ns):
            ref = cell.attrib.get("r", "")
            column = re.sub(r"\d+", "", ref)
            values[column] = cell_value(cell)
        rows.append(values)
    return rows


def get_ssc_summary(timeout: int) -> dict[str, Any]:
    data = fetch_bytes(
        SSC_DASHBOARD_URL,
        timeout=timeout,
        accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
    )
    rows = read_xlsx_rows(data, "Dashboard")
    key_figures = []
    top_providers = {"march_2020_by_value": [], "march_2020_by_count": [], "september_2020_by_value": [], "september_2020_by_count": []}
    for row in rows:
        if row.get("C") and row.get("D") and row.get("E") and row.get("C") not in {"Reporting Period", "Table 1: Significant Services Contract Key Figures"}:
            if re.fullmatch(r"\d+(\.\d+)?", row["C"]):
                key_figures.append(
                    {
                        "reporting_period": excel_date(row["C"]),
                        "total_contracts_value": float(row["D"]) if row.get("D") else None,
                        "contracts": int(float(row["E"])) if row.get("E") else None,
                    }
                )
        if row.get("B") and row.get("C") and row.get("B") not in {"Value of Contracts", "Table 2a: Top 10 providers March 2020 (by alphabetical order)"}:
            if not row["B"].startswith("Number of Contracts"):
                top_providers["march_2020_by_value"].append(row["B"])
                top_providers["march_2020_by_count"].append(row["C"])
        if row.get("G") and row.get("H") and row.get("G") not in {"Value of Contracts", "Table 2b: Top 10 providers September 2020 (by alphabetical order)"}:
            if not row["G"].startswith("Number of Contracts"):
                top_providers["september_2020_by_value"].append(row["G"])
                top_providers["september_2020_by_count"].append(row["H"])
    return {
        "kind": "significant_service_contracts_summary",
        "source": "New Zealand Government Procurement",
        "source_url": SSC_DASHBOARD_URL,
        "page_url": SSC_PAGE,
        "key_figures": key_figures,
        "top_providers": {k: v[:10] for k, v in top_providers.items()},
        "caveat": "Public workbook is an aggregate dashboard, not a contract-by-contract register.",
    }


def output_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output_records(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        output_json(data)
        return
    kind = data.get("kind")
    if kind in {"tenders", "awards"}:
        label = "GETS awards" if kind == "awards" else f"GETS {data.get('status', '')} tenders"
        print(f"{label}: {len(data.get('records', []))} shown")
        for record in data.get("records", []):
            date = record.get("award_date") or record.get("close_date") or record.get("closed_date") or record.get("open_date") or "-"
            print(f"- {record.get('rfx_id')}: {record.get('title')}")
            print(f"  organisation: {record.get('organisation') or '-'} | type: {record.get('tender_type') or '-'} | date: {date}")
            if record.get("url"):
                print(f"  url: {record['url']}")
    elif kind == "tender":
        print(f"{data.get('rfx_id')}: {data.get('title')}")
        print(f"organisation: {data.get('organisation') or '-'} | type: {data.get('tender_type') or '-'}")
        print(f"open: {data.get('open_date') or '-'} | close: {data.get('close_date') or '-'}")
        if data.get("categories"):
            print("categories: " + "; ".join(data["categories"]))
        if data.get("regions"):
            print("regions: " + "; ".join(data["regions"]))
        if data.get("overview"):
            print("\noverview:")
            print(data["overview"])
        print(f"\nsource: {data.get('source_url')}")
    elif kind == "sources":
        print("GETS procurement sources")
        for source in data.get("sources", []):
            print(f"- {source['name']} [{source['type']}]")
            print(f"  {source['url']}")
            if source.get("caveat"):
                print(f"  caveat: {source['caveat']}")
    elif kind == "significant_service_contracts_summary":
        print("Significant service contracts summary")
        for figure in data.get("key_figures", []):
            print(
                f"- {figure['reporting_period']}: "
                f"{figure['contracts']} contracts, ${figure['total_contracts_value']:,.0f}"
            )
        print(f"caveat: {data.get('caveat')}")


def cmd_tenders_list(args: argparse.Namespace) -> None:
    if args.status == "open" and args.page == 1:
        records = get_open_tenders(args.limit, args.timeout)
        source_url = GETS_RSS_URL
    else:
        records, source_url = get_status_tenders(args.status, args.page, args.limit, args.timeout)
    if args.keyword:
        records = filter_records(records, keyword=args.keyword)
    data = {
        "kind": "tenders",
        "source": "GETS",
        "status": args.status,
        "source_url": source_url,
        "page": args.page,
        "records": records[: args.limit],
    }
    output_records(data, args.json)


def cmd_tenders_search(args: argparse.Namespace) -> None:
    records, source_url = get_search_tenders(args.query, args.page, args.limit, args.timeout)
    data = {
        "kind": "tenders",
        "source": "GETS",
        "status": "search",
        "query": args.query,
        "source_url": source_url,
        "page": args.page,
        "records": records,
    }
    output_records(data, args.json)


def cmd_tender_get(args: argparse.Namespace) -> None:
    ref = args.ref.strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        url = ref
    else:
        url = f"{GETS_DETAIL_URL}?{urllib.parse.urlencode({'id': ref})}"
    document = fetch_text(url, timeout=args.timeout)
    output_records(parse_detail(document, url), args.json)


def cmd_awards(args: argparse.Namespace) -> None:
    records, urls = collect_awards(args.agency, args.pages, args.limit, args.timeout)
    data = {
        "kind": "awards",
        "source": "GETS completed tenders",
        "source_urls": urls,
        "agency": args.agency,
        "records": records,
        "caveat": "GETS completed-tender pages expose award notices but may not include supplier/value fields in public HTML.",
    }
    output_records(data, args.json)


def cmd_datasets_sources(args: argparse.Namespace) -> None:
    resources, error = ckan_award_sources(args.timeout)
    sources = [
        {
            "name": "GETS open tenders RSS",
            "type": "rss",
            "url": GETS_RSS_URL,
            "caveat": "Current open notices only.",
        },
        {
            "name": "GETS current tenders",
            "type": "html",
            "url": build_url("ExternalIndex.htm"),
            "caveat": "Public list table; detailed documents can require registration.",
        },
        {
            "name": "GETS completed tenders",
            "type": "html",
            "url": build_url("ExternalAwardedTenderList.htm"),
            "caveat": "Public completed/award list table.",
        },
        {
            "name": "MBIE procurement open data page",
            "type": "html/csv",
            "url": MBIE_OPEN_DATA_PAGE,
            "caveat": "Publishes GETS award-notice CSVs; MBIE asset host may reject some automated clients with HTTP 403.",
        },
        {
            "name": "Significant service contracts framework",
            "type": "html/xlsx",
            "url": SSC_PAGE,
            "caveat": "Public dashboard is aggregate. Some commercially sensitive content requires RealMe access.",
        },
    ]
    for resource in resources:
        sources.append(
            {
                "name": f"data.govt.nz resource: {resource.get('name')}",
                "type": resource.get("format") or "resource",
                "url": resource.get("url"),
                "resource_id": resource.get("resource_id"),
                "caveat": "Discovered through public CKAN metadata.",
            }
        )
    data = {
        "kind": "sources",
        "source": "GETS and NZ Government Procurement",
        "source_url": CKAN_PACKAGE_URL,
        "sources": sources,
        "ckan_error": error,
    }
    output_records(data, args.json)


def cmd_ssc_summary(args: argparse.Namespace) -> None:
    output_records(get_ssc_summary(args.timeout), args.json)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--timeout", type=int, default=10, help="network timeout in seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover New Zealand public procurement notices from GETS and procurement.govt.nz"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tenders = sub.add_parser("tenders", help="list or search GETS tender notices")
    tenders_sub = tenders.add_subparsers(dest="tenders_command", required=True)
    list_parser = tenders_sub.add_parser("list", help="list GETS tender notices by status")
    list_parser.add_argument("--status", choices=sorted(GETS_STATUS_PATHS), default="open")
    list_parser.add_argument("--keyword", help="filter listed notices by keyword after fetching")
    list_parser.add_argument("--page", type=int, default=1, help="GETS list page for HTML-backed statuses")
    list_parser.add_argument("--limit", type=int, default=10)
    add_common(list_parser)
    list_parser.set_defaults(func=cmd_tenders_list)

    search_parser = tenders_sub.add_parser("search", help="search GETS tender notices")
    search_parser.add_argument("query")
    search_parser.add_argument("--page", type=int, default=1)
    search_parser.add_argument("--limit", type=int, default=10)
    add_common(search_parser)
    search_parser.set_defaults(func=cmd_tenders_search)

    tender = sub.add_parser("tender", help="inspect one GETS tender")
    tender_sub = tender.add_subparsers(dest="tender_command", required=True)
    get_parser = tender_sub.add_parser("get", help="get one tender by RFx ID or URL")
    get_parser.add_argument("ref")
    add_common(get_parser)
    get_parser.set_defaults(func=cmd_tender_get)

    awards = sub.add_parser("awards", help="list recent GETS completed/award notices")
    awards.add_argument("--agency", help="case-insensitive organisation filter")
    awards.add_argument("--pages", type=int, default=3, help="number of completed-tender pages to scan")
    awards.add_argument("--limit", type=int, default=10)
    add_common(awards)
    awards.set_defaults(func=cmd_awards)

    datasets = sub.add_parser("datasets", help="show source datasets")
    datasets_sub = datasets.add_subparsers(dest="datasets_command", required=True)
    sources = datasets_sub.add_parser("sources", help="list source feeds, pages, and downloadable datasets")
    add_common(sources)
    sources.set_defaults(func=cmd_datasets_sources)

    ssc = sub.add_parser("ssc", help="significant service contracts dashboard")
    ssc_sub = ssc.add_subparsers(dest="ssc_command", required=True)
    summary = ssc_sub.add_parser("summary", help="summarise the public significant service contracts dashboard")
    add_common(summary)
    summary.set_defaults(func=cmd_ssc_summary)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except SkillError as exc:
        die(str(exc))
    except ET.ParseError as exc:
        die(f"could not parse upstream XML: {exc}")
    except zipfile.BadZipFile as exc:
        die(f"could not parse upstream XLSX workbook: {exc}")


if __name__ == "__main__":
    main()
