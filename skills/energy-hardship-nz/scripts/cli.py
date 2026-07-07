#!/usr/bin/env python3
"""New Zealand energy-hardship source discovery and lookup CLI.

Read-only stdlib wrapper around public MBIE, Stats NZ HES, and Electricity
Authority sources. The CLI returns explicit partial/blocked states where the
public data surface is an XLSX/PDF/Sigma dashboard that cannot be fully parsed
with Python standard library only.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import pathlib
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

TIMEOUT = 10
UA = "energy-hardship-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

MBIE_PAGE = (
    "https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/"
    "energy-statistics-and-modelling/energy-publications-and-technical-papers/"
    "reporting-on-energy-hardship-measures"
)
MBIE_REPORT_2024 = (
    "https://www.mbie.govt.nz/dmsdocument/"
    "31651-report-on-energy-hardship-measures-year-ended-june-2024"
)
MBIE_WORKBOOK_2024 = (
    "https://www.mbie.govt.nz/dmsdocument/"
    "31652-energy-hardship-measures-year-ended-june-2024"
)
MBIE_REPORT_2022 = (
    "https://www.mbie.govt.nz/dmsdocument/"
    "31653-report-on-energy-hardship-measures-year-ended-june-2022"
)

STATS_HES_2023_PAGE = (
    "https://www.stats.govt.nz/information-releases/"
    "household-expenditure-statistics-year-ended-june-2023/"
)
STATS_HES_2023_CSV_ZIP = (
    "https://www.stats.govt.nz/assets/Uploads/Household-expenditure-statistics/"
    "Household-expenditure-statistics-Year-ended-June-2023/Download-data/"
    "household-expenditure-statistics-year-ended-june-2023.zip"
)
STATS_HES_2023_XLSX = (
    "https://www.stats.govt.nz/assets/Uploads/Household-expenditure-statistics/"
    "Household-expenditure-statistics-Year-ended-June-2023/Download-data/"
    "household-expenditure-statistics-year-ended-june-2023-updated.xlsx"
)
STATS_HES_2023_DETAILED_ZIP = (
    "https://www.stats.govt.nz/assets/Uploads/Household-expenditure-statistics/"
    "Household-expenditure-statistics-Year-ended-June-2023/Download-data/"
    "detailed-household-expenditure-year-ended-June-2023-updated.zip"
)

EA_DASHBOARD_PAGE = (
    "https://www.ea.govt.nz/data-and-insights/charts-and-dashboards/"
    "disconnections-for-non-payment/"
)
EA_DATASET_HELP = "https://www.ea.govt.nz/data-and-insights/how-to-access-our-downloadable-datasets/"
EA_BLOB_CONTAINER = "https://emidatasets.blob.core.windows.net/publicdata"
EA_DISCONNECTION_PREFIX = "Datasets/Retail/Disconnections/"

ENERGY_CODES = {
    "04.5": "Electricity, gas and other domestic fuels",
    "04.5.01": "Electricity",
    "04.5.02": "Reticulated gas",
    "04.5.03": "Solid fuels",
    "04.5.04": "Liquid fuels",
    "04.5.05": "Other domestic fuel and service fees",
}

MBIE_MEASURES_2024 = [
    {
        "id": "cannot_afford_adequately_warm",
        "measure": "Could not afford to keep dwelling adequately warm",
        "period": "year ended June 2024",
        "households": 132000,
        "percent": 6.7,
        "change_since_2019_percentage_points": -0.9,
        "statistically_significant_since_2019": False,
        "confidence_interval_percent": None,
        "confidence_interval_households": None,
    },
    {
        "id": "feeling_cold_to_keep_costs_down",
        "measure": "Put up with feeling cold a lot to keep costs down",
        "period": "year ended June 2024",
        "households": 126000,
        "percent": 6.3,
        "change_since_2019_percentage_points": -1.3,
        "statistically_significant_since_2019": True,
        "confidence_interval_percent": None,
        "confidence_interval_households": None,
    },
    {
        "id": "utility_bills_late_more_than_once",
        "measure": "Paid electricity, gas, rates, or water bills late more than once",
        "period": "year ended June 2024",
        "households": 118000,
        "percent": 6.0,
        "change_since_2019_percentage_points": 0.4,
        "statistically_significant_since_2019": False,
        "confidence_interval_percent": None,
        "confidence_interval_households": None,
    },
    {
        "id": "heating_or_keeping_warm_major_problem",
        "measure": "Major problem with heating or keeping accommodation warm in winter",
        "period": "year ended June 2024",
        "households": 102000,
        "percent": 5.2,
        "change_since_2019_percentage_points": -3.2,
        "statistically_significant_since_2019": True,
        "confidence_interval_percent": None,
        "confidence_interval_households": None,
    },
    {
        "id": "damp_or_mould_major_problem",
        "measure": "Major problem with dampness or mould in accommodation",
        "period": "year ended June 2024",
        "households": 74000,
        "percent": 3.7,
        "change_since_2019_percentage_points": -1.6,
        "statistically_significant_since_2019": True,
        "confidence_interval_percent": None,
        "confidence_interval_households": None,
    },
]


class UpstreamError(Exception):
    """Raised when a public source cannot be reached or decoded."""


def die(message: str, code: int = 1) -> None:
    print(f"energy-hardship-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_url_bytes(url: str, timeout: int = TIMEOUT) -> bytes:
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="text/html,application/json,application/xml,text/csv,*/*",
        )
        return body
    except nzfetch.Blocked as e:
        raise UpstreamError(f"network error calling {url}: {e}") from None
    except nzfetch.FetchError as e:
        raise UpstreamError(str(e)) from None
    except (TimeoutError, OSError) as e:
        raise UpstreamError(f"network error calling {url}: {e}") from None


def read_url_text(url: str, timeout: int = TIMEOUT) -> str:
    return read_url_bytes(url, timeout=timeout).decode("utf-8", "replace")


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def strip_tags(text: str) -> str:
    return one_line(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}{suffix}"
    return f"{int(value):,}{suffix}"


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def output(payload: dict[str, Any], json_flag: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if json_flag:
        emit_json(payload)
    else:
        render(payload)


def absolute(base: str, maybe_url: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(maybe_url))


def link_items(text: str, base_url: str) -> list[dict[str, str]]:
    links = []
    pattern = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
    for match in pattern.finditer(text):
        links.append(
            {
                "label": strip_tags(match.group(2)),
                "url": absolute(base_url, match.group(1)),
            }
        )
    return links


def parse_year_ended(raw: str) -> int:
    text = str(raw).strip()
    if not re.fullmatch(r"\d{4}", text):
        die("--year-ended must be a four-digit year, for example 2024")
    return int(text)


def parse_year(raw: str) -> str:
    text = str(raw).strip()
    if not re.fullmatch(r"\d{4}", text):
        die("--year must be a four-digit year, for example 2023")
    return text


def parse_ym(raw: str, flag: str) -> tuple[int, int]:
    text = str(raw).strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if not match:
        die(f"{flag} must be in YYYY-MM format")
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        die(f"{flag} month must be 01 through 12")
    return year, month


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

def discover_mbie_sources(timeout: int) -> dict[str, Any]:
    releases = [
        {
            "year_ended": 2024,
            "released": "December 2025",
            "coverage": "1 July 2012 to 30 June 2024",
            "report_pdf_url": MBIE_REPORT_2024,
            "workbook_xlsx_url": MBIE_WORKBOOK_2024,
        },
        {
            "year_ended": 2022,
            "released": "June 2023",
            "coverage": "1 July 2012 to 30 June 2022",
            "report_pdf_url": MBIE_REPORT_2022,
            "workbook_xlsx_url": None,
        },
    ]
    source: dict[str, Any] = {
        "id": "mbie-energy-hardship-measures",
        "title": "Reporting on energy hardship measures",
        "organisation": "Ministry of Business, Innovation and Employment",
        "page_url": MBIE_PAGE,
        "access_status": "fallback",
        "releases": releases,
        "notes": [
            "Direct MBIE fetches can return 403 in automated Python/curl contexts.",
            "The 2024 report summary is represented in the measures command; workbook confidence intervals are not parsed here.",
        ],
    }
    try:
        text = read_url_text(MBIE_PAGE, timeout=timeout)
    except UpstreamError as e:
        source["access_status"] = "blocked"
        source["blocked_reason"] = str(e)
        return source

    energy_links = []
    for item in link_items(text, MBIE_PAGE):
        low = f"{item['label']} {item['url']}".lower()
        if "energy hardship" in low or "hardship measures" in low:
            energy_links.append(item)
    if energy_links:
        source["access_status"] = "ok"
        source["discovered_links"] = energy_links
    return source


def discover_stats_sources(timeout: int) -> dict[str, Any]:
    docs = [
        {
            "title": "Household expenditure statistics: Year ended June 2023 - CSV zip",
            "format": "zip",
            "url": STATS_HES_2023_CSV_ZIP,
        },
        {
            "title": "Household expenditure statistics: Year ended June 2023 - XLSX",
            "format": "xlsx",
            "url": STATS_HES_2023_XLSX,
        },
        {
            "title": "Detailed household expenditure: Year ended June 2023 - CSV zip",
            "format": "zip",
            "url": STATS_HES_2023_DETAILED_ZIP,
        },
    ]
    source: dict[str, Any] = {
        "id": "stats-hes-household-expenditure-2023",
        "title": "Household expenditure statistics: Year ended June 2023",
        "organisation": "Stats NZ",
        "page_url": STATS_HES_2023_PAGE,
        "access_status": "fallback",
        "documents": docs,
    }
    try:
        text = read_url_text(STATS_HES_2023_PAGE, timeout=timeout)
    except UpstreamError as e:
        source["access_status"] = "blocked"
        source["blocked_reason"] = str(e)
        return source

    match = re.search(r'<div id="pageViewData"[^>]*data-value="(.*?)"', text, re.S)
    if not match:
        source["access_status"] = "partial"
        source["blocked_reason"] = "could not find pageViewData JSON in Stats NZ release page"
        return source
    try:
        data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        source["access_status"] = "partial"
        source["blocked_reason"] = f"invalid Stats NZ embedded JSON: {e}"
        return source

    discovered = []
    for block in data.get("PageBlocks", []):
        for doc in block.get("BlockDocuments") or []:
            link = doc.get("DocumentLink")
            if not link:
                continue
            discovered.append(
                {
                    "title": one_line(doc.get("Title") or doc.get("Name") or ""),
                    "format": str(doc.get("DocumentExtension") or "").lower(),
                    "url": absolute(STATS_HES_2023_PAGE, str(link)),
                    "size": str(doc.get("DocumentSize") or ""),
                }
            )
    if discovered:
        source["access_status"] = "ok"
        source["documents"] = discovered
    return source


def discover_ea_sources(timeout: int) -> dict[str, Any]:
    source: dict[str, Any] = {
        "id": "ea-disconnections-for-non-payment",
        "title": "Disconnections for non-payment",
        "organisation": "Electricity Authority",
        "page_url": EA_DASHBOARD_PAGE,
        "dataset_access_notes_url": EA_DATASET_HELP,
        "blob_prefix": EA_DISCONNECTION_PREFIX,
        "access_status": "partial",
        "dashboard_embed_url": None,
        "public_documents": [],
        "notes": [
            "Dashboard is embedded with Sigma Computing.",
            "The public Azure Blob dataset folder currently exposes PDF source material for this topic, not a CSV feed parsed by this skill.",
        ],
    }
    try:
        text = read_url_text(EA_DASHBOARD_PAGE, timeout=timeout)
        title = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        if title:
            source["html_title"] = strip_tags(title.group(1))
        iframe = re.search(r'<iframe[^>]+src=[\'"]([^\'"]+)[\'"]', text, re.I)
        if iframe:
            source["dashboard_embed_url"] = html.unescape(iframe.group(1))
        source["access_status"] = "ok"
    except UpstreamError as e:
        source["access_status"] = "blocked"
        source["blocked_reason"] = str(e)

    try:
        source["public_documents"] = list_ea_disconnection_blobs(timeout=timeout)
    except UpstreamError as e:
        source["blob_access_status"] = "blocked"
        source["blob_blocked_reason"] = str(e)
    else:
        source["blob_access_status"] = "ok"
    return source


def list_ea_disconnection_blobs(timeout: int) -> list[dict[str, Any]]:
    params = {
        "restype": "container",
        "comp": "list",
        "prefix": EA_DISCONNECTION_PREFIX,
        "maxresults": "5000",
    }
    url = EA_BLOB_CONTAINER + "?" + urllib.parse.urlencode(params)
    raw = read_url_bytes(url, timeout=timeout)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise UpstreamError(f"invalid Azure Blob XML for {EA_DISCONNECTION_PREFIX}: {e}") from None
    documents = []
    for blob in root.findall(".//Blob"):
        name = blob.findtext("Name") or ""
        props = blob.find("Properties")
        documents.append(
            {
                "name": name,
                "url": f"{EA_BLOB_CONTAINER}/{urllib.parse.quote(name)}",
                "content_length": as_float(props.findtext("Content-Length") if props is not None else None),
                "last_modified": props.findtext("Last-Modified") if props is not None else None,
            }
        )
    return documents


# ---------------------------------------------------------------------------
# Minimal XLSX reader for simple code tables
# ---------------------------------------------------------------------------

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def col_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref.upper())
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for si in root.findall("a:si", XLSX_NS):
        values.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return values


def workbook_sheets(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    sheets = {}
    for sheet in workbook.findall("a:sheets/a:sheet", XLSX_NS):
        name = sheet.attrib.get("name", "")
        rid = sheet.attrib.get(OFFICE_REL, "")
        target = relmap.get(rid)
        if name and target:
            sheets[name] = "xl/" + target.lstrip("/")
    return sheets


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
    value = cell.find("a:v", XLSX_NS)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell.attrib.get("t") == "s":
        try:
            return strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def xlsx_rows(blob: bytes, sheet_name: str) -> list[list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise UpstreamError(f"invalid XLSX workbook: {e}") from None
    sheets = workbook_sheets(zf)
    if sheet_name not in sheets:
        raise UpstreamError(f"XLSX workbook has no sheet named {sheet_name!r}")
    strings = shared_strings(zf)
    root = ET.fromstring(zf.read(sheets[sheet_name]))
    rows = []
    for row in root.findall("a:sheetData/a:row", XLSX_NS):
        values: list[str] = []
        for cell in row.findall("a:c", XLSX_NS):
            index = col_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append("")
            values[index] = cell_text(cell, strings)
        while values and values[-1] == "":
            values.pop()
        rows.append(values)
    return rows


# ---------------------------------------------------------------------------
# Stats NZ HES loading
# ---------------------------------------------------------------------------

def stats_csv_zip_url(timeout: int) -> str:
    source = discover_stats_sources(timeout=timeout)
    for doc in source.get("documents", []):
        title = str(doc.get("title", "")).lower()
        url = str(doc.get("url", ""))
        if "csv" in title and "detailed" not in title and url.lower().endswith(".zip"):
            return url
    return STATS_HES_2023_CSV_ZIP


def load_hes(timeout: int) -> tuple[list[dict[str, str]], dict[str, str], dict[str, Any]]:
    url = stats_csv_zip_url(timeout=timeout)
    raw = read_url_bytes(url, timeout=timeout)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise UpstreamError(f"Stats NZ HES release was not a valid ZIP: {e}") from None

    csv_name = next((n for n in zf.namelist() if n.lower().endswith(".csv") and "datafile" in n.lower()), None)
    codebook_name = next((n for n in zf.namelist() if n.lower().endswith(".xlsx") and "codes" in n.lower()), None)
    if not csv_name:
        raise UpstreamError(f"Stats NZ HES ZIP has no datafile CSV; members: {', '.join(zf.namelist())}")
    if not codebook_name:
        raise UpstreamError(f"Stats NZ HES ZIP has no codes XLSX; members: {', '.join(zf.namelist())}")

    with zf.open(csv_name) as raw_csv:
        reader = csv.DictReader(io.TextIOWrapper(raw_csv, encoding="utf-8-sig", newline=""))
        rows = list(reader)

    codebook = zf.read(codebook_name)
    code_map = {}
    for row in xlsx_rows(codebook, "NZHEC")[1:]:
        if len(row) >= 2 and row[0]:
            code_map[row[0]] = row[1]

    release = {
        "source": "Stats NZ Household Expenditure Statistics",
        "page_url": STATS_HES_2023_PAGE,
        "csv_zip_url": url,
        "csv_member": csv_name,
        "codebook_member": codebook_name,
    }
    return rows, code_map, release


def estimate(row: dict[str, str]) -> dict[str, Any]:
    return {
        "weekly_expenditure_nzd": as_float(row.get("Estimate")),
        "rse_percent": as_float(row.get("RSE")),
        "lower_ci_weekly_nzd": as_float(row.get("LowerCIB")),
        "upper_ci_weekly_nzd": as_float(row.get("UpperCIB")),
        "flag": (row.get("Flag") or "").strip() or None,
    }


def hes_energy_expenditure(year: str, timeout: int) -> dict[str, Any]:
    rows, code_map, release = load_hes(timeout=timeout)
    t1_rows = [
        r for r in rows
        if r.get("Year") == year
        and r.get("Table") == "T1"
        and r.get("MsCode") == "M001"
        and r.get("CatCode") == "C000A"
    ]
    if not t1_rows:
        return {
            "status": "blocked",
            "blocked_reason": f"the HES CSV has no national Table 1 M001 rows for year {year}",
            "release": release,
            "records": [],
        }

    total_main = 0.0
    for row in t1_rows:
        if re.fullmatch(r"\d{2}", row.get("HECCode", "")):
            total_main += as_float(row.get("Estimate")) or 0.0

    records = []
    for code, label in ENERGY_CODES.items():
        row = next((r for r in t1_rows if r.get("HECCode") == code), None)
        if not row:
            continue
        item = {
            "hec_code": code,
            "label": label,
            "source_descriptor": code_map.get(code),
            **estimate(row),
        }
        weekly = item["weekly_expenditure_nzd"]
        if weekly is not None and total_main:
            item["share_of_main_group_expenditure_percent"] = round(weekly / total_main * 100, 2)
        else:
            item["share_of_main_group_expenditure_percent"] = None
        records.append(item)

    return {
        "status": "partial",
        "release": release,
        "year": year,
        "records": records,
        "derived_denominator": {
            "description": "sum of published national top-level HES Table 1 weekly expenditure groups",
            "weekly_expenditure_nzd": round(total_main, 2),
        },
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_datasets(args: argparse.Namespace) -> None:
    sources = [
        discover_mbie_sources(args.timeout),
        discover_stats_sources(args.timeout),
        discover_ea_sources(args.timeout),
    ]
    payload = {
        "status": "ok",
        "count": len(sources),
        "sources": sources,
    }

    def render(p: dict[str, Any]) -> None:
        print("NZ energy-hardship source catalogue")
        for src in p["sources"]:
            print(f"- {src['title']} ({src['organisation']})")
            print(f"  status: {src.get('access_status')}")
            print(f"  url: {src.get('page_url')}")
            if src.get("blocked_reason"):
                print(f"  note: {src['blocked_reason']}")

    output(payload, args.json, render)


def cmd_sources(args: argparse.Namespace) -> None:
    payload = {
        "status": "ok",
        "sources": [
            discover_mbie_sources(args.timeout),
            discover_stats_sources(args.timeout),
            discover_ea_sources(args.timeout),
        ],
        "caveats": [
            "Survey estimates should be read with sampling error and confidence interval caveats.",
            "MBIE workbook confidence intervals are not parsed when MBIE direct document access is blocked.",
            "Stats NZ HES public CSV supports national energy expenditure here, not income-decile or income-quintile burden ratios.",
            "Electricity Authority dashboard counts are not extracted from Sigma embeds by this stdlib-only CLI.",
        ],
    }

    def render(p: dict[str, Any]) -> None:
        for src in p["sources"]:
            print(f"{src['title']}")
            print(f"  organisation: {src['organisation']}")
            print(f"  page: {src['page_url']}")
            print(f"  status: {src.get('access_status')}")
            for doc in src.get("documents", []) or src.get("public_documents", []):
                print(f"  - {doc.get('title') or doc.get('name')}: {doc.get('url')}")
            for rel in src.get("releases", []):
                print(f"  - year ended {rel.get('year_ended')}: {rel.get('report_pdf_url')}")
        print("Caveats:")
        for caveat in p["caveats"]:
            print(f"- {caveat}")

    output(payload, args.json, render)


def cmd_measures(args: argparse.Namespace) -> None:
    year = parse_year_ended(args.year_ended)
    if year == 2024:
        payload = {
            "status": "ok",
            "source": {
                "title": "Report on energy hardship measures - Year ended June 2024",
                "organisation": "Ministry of Business, Innovation and Employment",
                "report_pdf_url": MBIE_REPORT_2024,
                "workbook_xlsx_url": MBIE_WORKBOOK_2024,
            },
            "year_ended": year,
            "measure_count": len(MBIE_MEASURES_2024),
            "measures": MBIE_MEASURES_2024,
            "caveats": [
                "National summary values are taken from the MBIE report key insights.",
                "Confidence intervals are null because they are not included in the report summary and the workbook is not parsed by this command.",
                "Changes are against year ended June 2019 as reported by MBIE.",
            ],
        }
    else:
        payload = {
            "status": "blocked",
            "year_ended": year,
            "source": discover_mbie_sources(args.timeout),
            "measures": [],
            "blocked_reason": (
                "This stdlib-only skill has curated national summary values for year ended June 2024 only. "
                "Use the MBIE report/workbook source metadata for other years."
            ),
        }

    def render(p: dict[str, Any]) -> None:
        print(f"MBIE energy-hardship measures, year ended June {p['year_ended']} ({p['status']})")
        if p["status"] != "ok":
            print(p.get("blocked_reason", "No data available."))
            return
        for item in p["measures"]:
            sig = "significant" if item["statistically_significant_since_2019"] else "not significant"
            print(f"- {item['measure']}: {item['percent']:.1f}% ({item['households']:,} households)")
            print(f"  change since 2019: {item['change_since_2019_percentage_points']:+.1f} pp, {sig}")
        print("Confidence intervals: not available in the parsed summary.")

    output(payload, args.json, render)


def cmd_burden(args: argparse.Namespace) -> None:
    year = parse_year(args.year)
    try:
        result = hes_energy_expenditure(year, args.timeout)
    except UpstreamError as e:
        payload = {
            "status": "blocked",
            "requested_breakdown": args.breakdown,
            "year": year,
            "records": [],
            "blocked_reason": str(e),
        }
    else:
        payload = {
            **result,
            "requested_breakdown": args.breakdown,
            "burden_metric_status": "blocked",
            "burden_blocked_reason": (
                "The public Stats NZ HES 2023 CSV release used by this skill does not include "
                "income-decile or income-quintile domestic-energy burden ratios. It includes national "
                "average weekly expenditure and confidence intervals for electricity, gas, and other "
                "domestic fuels."
            ),
            "caveats": [
                "weekly_expenditure_nzd is an average across all households.",
                "share_of_main_group_expenditure_percent is derived from published expenditure groups, not household income.",
                "Do not use this as a 10 percent or 2M income-burden estimate without an income denominator source.",
            ],
        }

    def render(p: dict[str, Any]) -> None:
        print(f"Stats NZ HES domestic-energy expenditure, {year} ({p['status']})")
        if p["status"] == "blocked":
            print(p.get("blocked_reason", "No data available."))
            return
        print(f"Requested breakdown: {p['requested_breakdown']} (not available in public CSV)")
        for item in p["records"]:
            share = item.get("share_of_main_group_expenditure_percent")
            share_text = "n/a" if share is None else f"{share:.2f}% of top-level expenditure"
            print(f"- {item['label']}: ${fmt_number(item['weekly_expenditure_nzd'])}/week, {share_text}")
        print(p["burden_blocked_reason"])

    output(payload, args.json, render)


def cmd_disconnections(args: argparse.Namespace) -> None:
    date_from = parse_ym(args.date_from, "--from")
    date_to = parse_ym(args.date_to, "--to")
    if date_from > date_to:
        die("--from must be earlier than or equal to --to")
    source = discover_ea_sources(args.timeout)
    payload = {
        "status": "metadata_only",
        "range": {"from": args.date_from, "to": args.date_to},
        "source": source,
        "counts": [],
        "blocked_reason": (
            "No public CSV/JSON disconnection-count feed was found. The current public page is a Sigma "
            "dashboard and the discoverable Azure Blob folder has PDF material only, so this stdlib-only "
            "skill returns source metadata rather than prepay/postpay counts."
        ),
    }

    def render(p: dict[str, Any]) -> None:
        print(f"EA disconnections for non-payment, {args.date_from} to {args.date_to}: metadata only")
        print(f"Dashboard: {p['source'].get('page_url')}")
        if p["source"].get("dashboard_embed_url"):
            print(f"Embed: {p['source']['dashboard_embed_url']}")
        docs = p["source"].get("public_documents") or []
        if docs:
            print("Public documents:")
            for doc in docs:
                print(f"- {doc['name']}: {doc['url']}")
        print(p["blocked_reason"])

    output(payload, args.json, render)


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query NZ energy-hardship source data and metadata")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help="network timeout in seconds (default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)

    datasets = sub.add_parser("datasets", help="list public source datasets and releases")
    add_json(datasets)
    datasets.set_defaults(func=cmd_datasets)

    measures = sub.add_parser("measures", help="return MBIE five energy-hardship measures")
    measures.add_argument("--year-ended", default="2024", help="June year ended, for example 2024")
    add_json(measures)
    measures.set_defaults(func=cmd_measures)

    burden = sub.add_parser("burden", help="return feasible HES energy expenditure and burden caveats")
    burden.add_argument("--breakdown", choices=("income-decile", "income-quintile"), required=True)
    burden.add_argument("--year", default="2023", help="HES release year, for example 2023")
    add_json(burden)
    burden.set_defaults(func=cmd_burden)

    disconnections = sub.add_parser("disconnections", help="return EA disconnection source metadata")
    disconnections.add_argument("--from", dest="date_from", required=True, help="start month YYYY-MM")
    disconnections.add_argument("--to", dest="date_to", required=True, help="end month YYYY-MM")
    add_json(disconnections)
    disconnections.set_defaults(func=cmd_disconnections)

    sources = sub.add_parser("sources", help="show source URLs and parsing caveats")
    add_json(sources)
    sources.set_defaults(func=cmd_sources)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.timeout <= 0:
        die("--timeout must be positive")
    args.func(args)


if __name__ == "__main__":
    main()
