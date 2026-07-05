#!/usr/bin/env python3
"""Read-only public-data CLI for NZ mental-health regulatory sources."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import xml.etree.ElementTree as ET
from typing import Any

TIMEOUT = 10
UA = (
    "Mozilla/5.0 (compatible; mental-health-data-nz-skill/1.0; "
    "+https://github.com/thecolab-ai/.skills)"
)

HEALTH_ANNUAL_REPORTS = (
    "https://www.health.govt.nz/about-us/corporate-publications/mental-health-annual-reports"
)
MENTAL_HEALTH_DATA = "https://www.health.govt.nz/monitoring-statistics/statistics-and-data-sets/mental-health"
KPI_BASE = "https://www.mhakpi.health.nz"
KPI_INDICATORS = KPI_BASE + "/indicators/"
KPI_DASHBOARDS = KPI_BASE + "/dashboards/"

KNOWN_REPORTS: list[dict[str, Any]] = [
    {
        "id": "odmhas-2023-24",
        "year": "2023/24",
        "start_year": 2023,
        "end_year": 2024,
        "title": "Office of the Director of Mental Health and Addiction Services: Regulatory Report 1 July 2023 to 30 June 2024",
        "publication_date": "2026-03-31",
        "page_url": "https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-2023-to-2024",
        "pdf_url": "https://www.health.govt.nz/system/files/2026-03/odmhas-regulatory-report-2023-24.pdf",
        "docx_url": "https://www.health.govt.nz/system/files/2026-03/odmhas-regulatory-report-2023-24.docx",
    },
    {
        "id": "odmhas-2022-23",
        "year": "2022/23",
        "start_year": 2022,
        "end_year": 2023,
        "title": "Office of the Director of Mental Health and Addiction Services: Regulatory Report 1 July 2022 to 30 June 2023",
        "publication_date": "2025-02-13",
        "page_url": "https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-1-july-2022-to-30",
        "pdf_url": "https://www.health.govt.nz/system/files/2025-02/Office-of-the-Director-of-Mental-Health-and-Addiction-Services-Regulatory-Report-2022-23.pdf",
        "docx_url": "https://www.health.govt.nz/system/files/2025-02/Office-of-the-Director-of-Mental-Health-and-Addiction-Services-Regulatory-Report-2022-23.docx",
    },
    {
        "id": "odmhas-2021-22",
        "year": "2021/22",
        "start_year": 2021,
        "end_year": 2022,
        "title": "Office of the Director of Mental Health and Addiction Services: Regulatory Report 1 July 2021 to 30 June 2022",
        "publication_date": "2023-09-25",
        "page_url": "https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-1-july-2021-to-30",
        "pdf_url": "https://www.health.govt.nz/system/files/2023-09/odmhas-regulatory-report-sep23.pdf",
        "docx_url": "https://www.health.govt.nz/system/files/2023-09/odmhas-regulatory-report-sep23.docx",
    },
    {
        "id": "odmhas-2020-21",
        "year": "2020/21",
        "start_year": 2020,
        "end_year": 2021,
        "title": "Office of the Director of Mental Health and Addiction Services: Regulatory Report 1 July 2020 to 30 June 2021",
        "publication_date": "2022-09-30",
        "page_url": "https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-1-july-2020-to-30",
        "pdf_url": "https://www.health.govt.nz/system/files/2022-09/odmhas-regulatory-report-sep22.pdf",
        "docx_url": "https://www.health.govt.nz/system/files/2022-09/odmhas-regulatory-report-sep22.docx",
    },
    {
        "id": "odmhas-2020",
        "year": "2020",
        "start_year": 2020,
        "end_year": 2020,
        "title": "Office of the Director of Mental Health and Addiction Services 2020 Regulatory Report",
        "publication_date": "2021-12-01",
        "page_url": "https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-2020-regulatory-report",
        "pdf_url": "https://www.health.govt.nz/system/files/2021-11/office_of_the_director_of_mental_health_and_addiction_services_-_2020_regulatory_report_final_v2.pdf",
        "docx_url": "https://www.health.govt.nz/system/files/2021-11/office_of_the_director_of_mental_health_and_addiction_services_-_2020_regulatory_report_final_v2.docx",
    },
]

KPI_FALLBACKS: list[dict[str, str]] = [
    {
        "id": "wait-times",
        "title": "Wait times",
        "url": KPI_BASE + "/indicators/wait-times/",
        "summary": "Explore how long people wait to be seen by mental health and addiction services.",
    },
    {
        "id": "whanau-engagement",
        "title": "Whanau engagement",
        "url": KPI_BASE + "/indicators/whanau-engagement/",
        "summary": "Track how and when services involve whanau in a person's service journey.",
    },
    {
        "id": "continuity-of-care",
        "title": "Continuity of care",
        "url": KPI_BASE + "/indicators/continuity-of-care/",
        "summary": "Understand connected NGO care before, during, and after acute inpatient events.",
    },
    {
        "id": "seclusion",
        "title": "Seclusion",
        "url": KPI_BASE + "/indicators/seclusion/",
        "summary": "View public metadata for seclusion frequency and duration indicators.",
    },
    {
        "id": "7-day-follow-up",
        "title": "7-day follow up",
        "url": KPI_BASE + "/indicators/7-day-follow-up/",
        "summary": "Understand contact after discharge from acute mental health inpatient services.",
    },
    {
        "id": "28-day-readmission",
        "title": "28-day readmission",
        "url": KPI_BASE + "/indicators/28-day-readmission/",
        "summary": "Explore public metadata for readmission within 28 days of discharge.",
    },
]

SOURCE_CATALOGUE: list[dict[str, Any]] = [
    {
        "id": "odmhas-regulatory-reports",
        "name": "ODMHAS annual regulatory reports",
        "agency": "Manatu Hauora / Ministry of Health",
        "url": HEALTH_ANNUAL_REPORTS,
        "formats": ["HTML listing", "PDF", "DOCX"],
        "access": "Public, keyless; HTML discovery can return 403 from automated clients, direct assets may still work.",
        "use_for": ["compulsory treatment orders", "seclusion", "restraint", "ECT", "section 95/99 counts"],
    },
    {
        "id": "mhakpi-indicators",
        "name": "MH&A KPI Programme indicators",
        "agency": "KPI Programme / Wise Group sector programme",
        "url": KPI_INDICATORS,
        "formats": ["HTML metadata", "dashboard links"],
        "access": "Public indicator pages; data dashboards can require registration/sign-in.",
        "use_for": ["wait times", "seclusion", "7-day follow-up", "28-day readmission", "whanau engagement"],
    },
    {
        "id": "primhd-service-use-tool",
        "name": "PRIMHD / mental-health service-use web tools",
        "agency": "Health New Zealand / Ministry of Health",
        "url": MENTAL_HEALTH_DATA,
        "formats": ["web tool", "manual export where offered"],
        "access": "No stable unauthenticated API is assumed; treat as manual-export fallback.",
        "use_for": ["service use", "demographic dashboard context"],
    },
    {
        "id": "section-99-inspections",
        "name": "Section 99 inspection publications",
        "agency": "Director of Mental Health / Ministry of Health",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/section-99-inspection-of-canterbury-mental-health-services",
        "formats": ["HTML", "PDF", "DOCX where offered"],
        "access": "Public publication pages; not a normalised dataset.",
        "use_for": ["inpatient inspections", "Canterbury Waitaha", "Waikato inspection"],
    },
    {
        "id": "district-inspectors",
        "name": "Mental health District Inspectors",
        "agency": "Ministry of Health",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/mental-health-act/mental-health-district-inspectors",
        "formats": ["HTML", "PDF guidance"],
        "access": "Public contact/source pages; not a statistical dataset.",
        "use_for": ["District Inspector role", "complaints", "rights safeguards", "source provenance"],
    },
]

INSPECTION_SOURCES: list[dict[str, str]] = [
    {
        "id": "district-inspectors",
        "title": "Mental health District Inspectors",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/mental-health-act/mental-health-district-inspectors",
        "kind": "source_page",
    },
    {
        "id": "district-inspectors-list",
        "title": "Mental health District Inspectors list",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/mental-health-act/mental-health-district-inspectors/district-inspectors-list",
        "kind": "source_page",
    },
    {
        "id": "section-99-canterbury-source",
        "title": "Section 99 inspection of Canterbury Mental Health Services",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/section-99-inspection-of-canterbury-mental-health-services",
        "kind": "inspection_source",
    },
    {
        "id": "section-99-canterbury-report",
        "title": "Section 99 Inspection into Canterbury - Waitaha Adult Inpatient and Associated Mental Health Services",
        "url": "https://www.health.govt.nz/publications/section-99-inspection-into-canterbury-waitaha-adult-inpatient-and-associated-mental-health-services",
        "kind": "inspection_report",
    },
    {
        "id": "section-99-waikato-report",
        "title": "Section 99 Inspection of Waikato District Health Board Mental Health and Addiction Services",
        "url": "https://www.health.govt.nz/publications/section-99-inspection-of-waikato-district-health-board-mental-health-and-addiction-services",
        "kind": "inspection_report",
    },
    {
        "id": "section-95-waikato-inquiry",
        "title": "Section 95 inquiry into the treatment of a patient at Waikato Hospital",
        "url": "https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/section-95-inquiry-into-the-treatment-of-a-patient-at-waikato-hospital",
        "kind": "inquiry_source",
    },
]


class CliError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error", source_url: str | None = None):
        super().__init__(message)
        self.code = code
        self.source_url = source_url


class UpstreamUnavailable(CliError):
    pass


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_d = dict(attrs)
        self._href = attrs_d.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": clean_text(" ".join(self._text))})
            self._href = None
            self._text = []


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(url: str, timeout: int, accept: str = "*/*"):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-NZ,en;q=0.9",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_bytes(url: str, timeout: int = TIMEOUT, accept: str = "*/*") -> tuple[bytes, str, str]:
    try:
        with request(url, timeout=timeout, accept=accept) as resp:
            return resp.read(), resp.geturl(), resp.headers.get("content-type") or ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = clean_text(exc.read(500).decode("utf-8", "replace"))[:220]
        except Exception:
            detail = ""
        if exc.code in {403, 429}:
            raise UpstreamUnavailable(
                f"HTTP {exc.code} from upstream; likely bot protection or rate limiting",
                code="upstream_blocked",
                source_url=url,
            ) from exc
        raise CliError(
            f"HTTP {exc.code} fetching {url}" + (f": {detail}" if detail else ""),
            code="upstream_http",
            source_url=url,
        ) from exc
    except TimeoutError as exc:
        raise UpstreamUnavailable(f"timeout fetching {url}", code="upstream_timeout", source_url=url) from exc
    except urllib.error.URLError as exc:
        raise UpstreamUnavailable(
            f"network error fetching {url}: {exc.reason}",
            code="upstream_unreachable",
            source_url=url,
        ) from exc


def fetch_text(url: str, timeout: int = TIMEOUT) -> tuple[str, str, str]:
    data, final_url, content_type = fetch_bytes(url, timeout, "text/html,*/*;q=0.8")
    return data.decode("utf-8", "replace"), final_url, content_type


def absolute_url(url: str, base: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(url))


def parse_links(page: str, base_url: str) -> list[dict[str, str]]:
    parser = LinkCollector()
    parser.feed(page)
    rows = []
    for link in parser.links:
        href = link.get("href") or ""
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        rows.append({"url": absolute_url(href, base_url), "text": link.get("text") or ""})
    return rows


def live_report_discovery(timeout: int) -> dict[str, Any]:
    try:
        page, final_url, content_type = fetch_text(HEALTH_ANNUAL_REPORTS, timeout)
    except UpstreamUnavailable as exc:
        return {
            "status": "blocked",
            "code": exc.code,
            "source_url": exc.source_url,
            "message": str(exc),
        }
    except CliError as exc:
        return {
            "status": "error",
            "code": exc.code,
            "source_url": exc.source_url,
            "message": str(exc),
        }

    links = parse_links(page, final_url)
    report_links = []
    for link in links:
        haystack = (link["text"] + " " + link["url"]).lower()
        if "director of mental health" in haystack or "odmhas" in haystack:
            report_links.append(link)
    return {
        "status": "ok",
        "source_url": final_url,
        "content_type": content_type,
        "report_link_count": len(report_links),
        "report_links": report_links[:30],
    }


def report_rows(limit: int | None = None) -> list[dict[str, Any]]:
    rows = [dict(row) for row in KNOWN_REPORTS]
    rows.sort(key=lambda row: (row["end_year"], row["start_year"], row["id"]), reverse=True)
    if limit is not None:
        return rows[:limit]
    return rows


def normalise_year_input(raw: str) -> str:
    text = raw.strip().lower().replace("fy", "").replace(" ", "")
    text = text.replace("_", "-")
    m = re.match(r"^(\d{4})[/\-](\d{2}|\d{4})$", text)
    if m:
        first = int(m.group(1))
        second_raw = m.group(2)
        second = int(second_raw) if len(second_raw) == 4 else int(str(first)[:2] + second_raw)
        return f"{first}/{str(second)[-2:]}"
    if re.match(r"^\d{4}$", text):
        return text
    raise CliError(f"invalid year '{raw}'. Use YYYY, YYYY/YY, or YYYY-YY.", code="invalid_year")


def select_report(raw_year: str) -> dict[str, Any]:
    wanted = normalise_year_input(raw_year)
    for report in KNOWN_REPORTS:
        if wanted == report["year"]:
            return report
    if wanted.isdigit():
        year = int(wanted)
        for report in KNOWN_REPORTS:
            if year == report["start_year"]:
                return report
        for report in KNOWN_REPORTS:
            if year == report["end_year"]:
                return report
    available = ", ".join(row["year"] for row in report_rows())
    raise CliError(f"no known ODMHAS report for '{raw_year}'. Available years: {available}", code="unknown_year")


def docx_text_and_tables(data: bytes) -> tuple[list[str], list[list[list[str]]]]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise CliError("DOCX asset did not contain word/document.xml", code="invalid_docx") from exc

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(xml)

    def text_of(element: ET.Element) -> str:
        return clean_text("".join(t.text or "" for t in element.iter(ns + "t")))

    paragraphs = [text_of(p) for p in root.iter(ns + "p")]
    paragraphs = [p for p in paragraphs if p]

    tables: list[list[list[str]]] = []
    for tbl in root.iter(ns + "tbl"):
        rows = []
        for tr in tbl.findall(ns + "tr"):
            cells = [text_of(tc) for tc in tr.findall(ns + "tc")]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return paragraphs, tables


def fetch_report_docx(report: dict[str, Any], timeout: int) -> tuple[list[str], list[list[list[str]]], dict[str, Any]]:
    url = report.get("docx_url")
    if not url:
        raise CliError(f"{report['year']} has no known DOCX URL", code="docx_unavailable")
    data, final_url, content_type = fetch_bytes(
        url,
        timeout,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*;q=0.8",
    )
    paragraphs, tables = docx_text_and_tables(data)
    meta = {
        "source_url": final_url,
        "content_type": content_type,
        "bytes": len(data),
        "table_count": len(tables),
    }
    return paragraphs, tables, meta


def compact_header(row: list[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", " ".join(row).lower())


def find_table(tables: list[list[list[str]]], required: list[str], forbidden: list[str] | None = None) -> list[list[str]] | None:
    forbidden = forbidden or []
    for table in tables:
        joined = compact_header(table[0])
        all_rows = compact_header([cell for row in table[:3] for cell in row])
        if all(re.sub(r"[^a-z0-9]+", "", term.lower()) in all_rows for term in required) and not any(
            re.sub(r"[^a-z0-9]+", "", term.lower()) in all_rows for term in forbidden
        ):
            return table
    return None


def standard_records(table: list[list[str]]) -> list[dict[str, str]]:
    if not table:
        return []
    headers = [clean_text(h) or f"column_{i + 1}" for i, h in enumerate(table[0])]
    records = []
    carry: dict[int, str] = {}
    for row in table[1:]:
        if len(row) == 1 and row[0]:
            records.append({"section": row[0]})
            continue
        item: dict[str, str] = {}
        for idx, header in enumerate(headers):
            value = row[idx] if idx < len(row) else ""
            if not value and idx in carry:
                value = carry[idx]
            if value and header.lower() in {"act", "legal act"}:
                carry[idx] = value
            item[header] = value
        if any(item.values()):
            records.append(item)
    return records


def seclusion_appendix_records(table: list[list[str]] | None) -> list[dict[str, str]]:
    if not table:
        return []
    headers = table[0]
    excluding_label = headers[1] if len(headers) > 1 else "excluding_outliers"
    including_label = headers[2] if len(headers) > 2 else "including_outliers"
    records = []
    scope = ""
    for row in table[1:]:
        if len(row) == 1 or (row and row[0] and len([c for c in row[1:] if c]) == 0):
            scope = row[0]
            continue
        if not row or not row[0]:
            continue
        records.append(
            {
                "scope": scope,
                "measure": row[0],
                "excluding_label": excluding_label,
                "excluding_value": row[1] if len(row) > 1 else "",
                "including_label": including_label,
                "including_value": row[2] if len(row) > 2 else "",
            }
        )
    return records


def district_percentage_records(table: list[list[str]] | None) -> list[dict[str, str]]:
    if not table:
        return []
    rows = []
    for row in table[1:]:
        if len(row) >= 2 and row[0] and row[1]:
            rows.append({"district": row[0], "percentage": row[1]})
        if len(row) >= 5 and row[3] and row[4]:
            rows.append({"district": row[3], "percentage": row[4]})
    return rows


def inspection_records(table: list[list[str]] | None) -> list[dict[str, str]]:
    if not table or len(table) < 2:
        return []
    years = table[0]
    counts = table[1]
    rows = []
    for idx, year in enumerate(years):
        if not year:
            continue
        rows.append(
            {
                "year": year,
                "section_95_inquiry_or_section_99_inspection_reports_received_or_completed": counts[idx] if idx < len(counts) else "",
            }
        )
    return rows


def filter_records(records: list[dict[str, Any]], key_names: list[str], query: str | None) -> list[dict[str, Any]]:
    if not query:
        return records
    needle = query.lower()
    out = []
    for row in records:
        if any(needle in str(row.get(key, "")).lower() for key in key_names):
            out.append(row)
    return out


def seclusion_payload(args: argparse.Namespace) -> dict[str, Any]:
    report = select_report(args.year)
    try:
        _paragraphs, tables, docx_meta = fetch_report_docx(report, args.timeout)
    except UpstreamUnavailable as exc:
        return {
            "command": "seclusion",
            "status": "blocked",
            "code": exc.code,
            "requested_year": args.year,
            "report": report,
            "source_url": exc.source_url,
            "message": str(exc),
            "caveats": ["DOCX extraction needs direct access to the public report asset."],
        }

    appendix = find_table(tables, ["seclusion measure"])
    forensic = find_table(tables, ["regional service", "number of people secluded", "number of events", "average duration"])
    intellectual_counts = find_table(tables, ["act", "number of people secluded", "number of events", "average number"])
    intellectual_hours = find_table(tables, ["act", "total seclusion hours", "median length"])
    intellectual_ethnicity = find_table(tables, ["ethnicity", "people secluded per 100000 population"])
    district_percent = find_table(tables, ["district", "percentage"])

    adult_district_percent = district_percentage_records(district_percent)
    forensic_rows = standard_records(forensic or [])
    if args.district:
        adult_district_percent = filter_records(adult_district_percent, ["district"], args.district)
        forensic_rows = filter_records(forensic_rows, ["Regional service"], args.district)

    caveats = [
        "Values are extracted only from structured DOCX tables, not OCR or chart digitisation.",
        "Adult inpatient district people/event-rate measures are often chart-only; use the PDF/DOCX manually for those exact chart values.",
        "Rows are source strings so percentages, rates, and hour-minute values are not rounded or coerced.",
    ]
    if args.district and not adult_district_percent and not forensic_rows:
        caveats.append(f"No structured seclusion table rows matched district/regional service query '{args.district}'.")

    return {
        "command": "seclusion",
        "status": "ok",
        "requested_year": args.year,
        "district_filter": args.district,
        "report": report,
        "docx": docx_meta,
        "seclusion_summary": seclusion_appendix_records(appendix),
        "forensic_regional_service": forensic_rows,
        "intellectual_disability_counts": standard_records(intellectual_counts or []),
        "intellectual_disability_hours": standard_records(intellectual_hours or []),
        "intellectual_disability_ethnicity": standard_records(intellectual_ethnicity or []),
        "adult_inpatient_admissions_with_seclusion_percent_by_district": adult_district_percent,
        "caveats": caveats,
    }


def indicator_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    if not path.startswith("indicators/"):
        return None
    parts = path.split("/")
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[1]


def kpi_indicator_list(timeout: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = {item["id"]: dict(item) for item in KPI_FALLBACKS}
    try:
        page, final_url, content_type = fetch_text(KPI_INDICATORS, timeout)
    except UpstreamUnavailable as exc:
        return list(rows.values()), {
            "status": "fallback",
            "code": exc.code,
            "source_url": exc.source_url,
            "message": str(exc),
        }
    except CliError as exc:
        return list(rows.values()), {
            "status": "fallback",
            "code": exc.code,
            "source_url": exc.source_url,
            "message": str(exc),
        }

    for link in parse_links(page, final_url):
        slug = indicator_from_url(link["url"])
        if not slug:
            continue
        row = rows.get(slug, {"id": slug, "title": clean_text(link["text"]).split(" ", 1)[0] or slug, "url": link["url"]})
        row["url"] = link["url"]
        if link["text"]:
            row["page_text"] = link["text"]
        rows[slug] = row

    ordered = []
    for fallback in KPI_FALLBACKS:
        if fallback["id"] in rows:
            ordered.append(rows.pop(fallback["id"]))
    ordered.extend(sorted(rows.values(), key=lambda row: row["id"]))
    return ordered, {"status": "ok", "source_url": final_url, "content_type": content_type}


def select_indicator(raw: str, indicators: list[dict[str, Any]]) -> dict[str, Any]:
    wanted = slugify(raw)
    aliases = {"follow-up": "7-day-follow-up", "readmission": "28-day-readmission", "family-engagement": "whanau-engagement"}
    wanted = aliases.get(wanted, wanted)
    for item in indicators:
        if wanted in {item["id"], slugify(item.get("title", ""))}:
            return item
    known = ", ".join(item["id"] for item in indicators)
    raise CliError(f"unknown KPI indicator '{raw}'. Known indicators: {known}", code="unknown_indicator")


def page_title(page: str) -> str | None:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.I | re.S)
    if match:
        return clean_text(match.group(1))
    match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else None


def kpi_get_payload(args: argparse.Namespace) -> dict[str, Any]:
    indicators, discovery = kpi_indicator_list(args.timeout)
    indicator = select_indicator(args.indicator, indicators)
    try:
        page, final_url, content_type = fetch_text(indicator["url"], args.timeout)
        links = parse_links(page, final_url)
        dashboard_links = []
        resource_links = []
        for link in links:
            url = link["url"]
            lower = (url + " " + link.get("text", "")).lower()
            if "/dashboards" in lower:
                dashboard_links.append(link)
            if "/resources/" in lower or any(ext in lower for ext in (".pdf", ".docx", ".xlsx", ".csv")):
                resource_links.append(link)
        blocked_text = clean_text(page).lower()
        page_status = {
            "status": "ok",
            "source_url": final_url,
            "content_type": content_type,
        }
        title = page_title(page) or indicator.get("title") or indicator["id"]
        requires_registration = "must be registered" in blocked_text or "sign in" in blocked_text
    except UpstreamUnavailable as exc:
        dashboard_links = []
        resource_links = []
        page_status = {"status": "blocked", "code": exc.code, "source_url": exc.source_url, "message": str(exc)}
        title = indicator.get("title") or indicator["id"]
        requires_registration = True

    return {
        "command": "kpi get",
        "status": "ok" if page_status["status"] == "ok" else "partial",
        "indicator": {
            "id": indicator["id"],
            "title": title,
            "url": indicator["url"],
            "summary": indicator.get("summary") or indicator.get("page_text"),
        },
        "indicator_discovery": discovery,
        "page_fetch": page_status,
        "dashboard_links": dashboard_links,
        "resource_links": resource_links,
        "dashboard_access": {
            "public_data_status": "metadata_only",
            "requires_registration_or_sign_in": requires_registration,
            "caveat": "KPI Programme dashboard data is not treated as a stable unauthenticated export; use public metadata links or manual authorised export where appropriate.",
        },
    }


def inspection_payload(args: argparse.Namespace) -> dict[str, Any]:
    report = select_report(args.year) if args.year else report_rows(1)[0]
    try:
        paragraphs, tables, docx_meta = fetch_report_docx(report, args.timeout)
        table = None
        for candidate in tables:
            if len(candidate) >= 2 and all(re.match(r"^\d{4}/\d{2}$", cell or "") for cell in candidate[0][:3]):
                table = candidate
                break
        rows = inspection_records(table)
        narrative = [
            p
            for p in paragraphs
            if "section 95" in p.lower() or "section 99" in p.lower() or "district inspector" in p.lower()
        ][:8]
        fetch_status = {"status": "ok", **docx_meta}
    except UpstreamUnavailable as exc:
        rows = []
        narrative = []
        fetch_status = {"status": "blocked", "code": exc.code, "source_url": exc.source_url, "message": str(exc)}

    if args.year:
        rows = [row for row in rows if row.get("year") == report["year"]]

    return {
        "command": "inpatient-inspections",
        "status": "ok" if fetch_status["status"] == "ok" else "partial",
        "requested_year": args.year,
        "report": report,
        "docx": fetch_status,
        "inspection_counts": rows,
        "narrative_snippets": narrative,
        "inspection_and_district_inspector_sources": INSPECTION_SOURCES,
        "caveats": [
            "Section 95/99 rows combine inquiry and inspection reports received or completed as labelled in the ODMHAS table.",
            "Individual inspection publications are source links, not a normalised dataset.",
        ],
    }


def kpi_sources_payload(args: argparse.Namespace) -> dict[str, Any]:
    indicators, discovery = kpi_indicator_list(args.timeout)
    return {
        "command": "kpi-sources",
        "status": "ok",
        "source": {
            "name": "MH&A KPI Programme",
            "url": KPI_BASE,
            "indicators_url": KPI_INDICATORS,
            "dashboards_url": KPI_DASHBOARDS,
        },
        "indicator_discovery": discovery,
        "indicators": indicators,
        "caveats": [
            "Public HTML exposes metadata and dashboard links.",
            "Dashboard data may require registration/sign-in and is not scraped as an unauthenticated export.",
        ],
    }


def sources_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "command": args.command_name,
        "status": "ok",
        "generated_at": now_iso(),
        "sources": SOURCE_CATALOGUE,
        "known_odmhas_reports": report_rows(),
        "inspection_sources": INSPECTION_SOURCES,
    }


def reports_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "command": "odmhas-reports",
        "status": "ok",
        "generated_at": now_iso(),
        "live_discovery": live_report_discovery(args.timeout),
        "reports": report_rows(args.limit),
        "caveats": [
            "Known reports are retained because Ministry HTML listing pages can block automated clients.",
            "Use DOCX assets for structured table extraction; use PDFs for citation and manual visual checks.",
        ],
    }


def kpi_list_payload(args: argparse.Namespace) -> dict[str, Any]:
    indicators, discovery = kpi_indicator_list(args.timeout)
    return {
        "command": "kpi list",
        "status": "ok",
        "indicator_discovery": discovery,
        "indicators": indicators,
        "dashboard_access": {
            "dashboards_url": KPI_DASHBOARDS,
            "public_data_status": "metadata_only",
            "caveat": "Data dashboards can require registration/sign-in; this command lists public indicator metadata only.",
        },
    }


def print_table(title: str, rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> None:
    print(title)
    if not rows:
        print("  (none)")
        return
    for row in rows[:limit]:
        parts = [str(row.get(field, "")).strip() for field in fields if str(row.get(field, "")).strip()]
        print("  - " + " | ".join(parts))
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more")


def emit(payload: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "json_output", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    command = payload.get("command")
    if command == "odmhas-reports":
        print_table("ODMHAS regulatory reports", payload["reports"], ["year", "publication_date", "title", "pdf_url"])
        print(f"Discovery: {payload['live_discovery'].get('status')}")
    elif command == "seclusion":
        report = payload["report"]
        print(f"Seclusion tables for {report['year']}: {report['title']}")
        print_table("Appendix summary", payload.get("seclusion_summary", []), ["scope", "measure", "excluding_value", "including_value"])
        print_table("Forensic regional service", payload.get("forensic_regional_service", []), ["Regional service", "Number of people secluded", "Number of events", "Total hours", "Totalhours"])
        if payload.get("caveats"):
            print("Caveats:")
            for caveat in payload["caveats"]:
                print(f"  - {caveat}")
    elif command in {"kpi list", "kpi-sources"}:
        print_table("MH&A KPI indicators", payload["indicators"], ["id", "title", "url"])
        print(payload.get("dashboard_access", {}).get("caveat") or "Dashboard data may require registration/sign-in.")
    elif command == "kpi get":
        item = payload["indicator"]
        print(f"{item['title']} ({item['id']})")
        print(item["url"])
        print_table("Dashboard links", payload["dashboard_links"], ["text", "url"])
        print_table("Resource links", payload["resource_links"], ["text", "url"])
        print(payload["dashboard_access"]["caveat"])
    elif command == "inpatient-inspections":
        report = payload["report"]
        print(f"Inspection rows from {report['year']}: {report['title']}")
        print_table("Section 95/99 counts", payload.get("inspection_counts", []), ["year", "section_95_inquiry_or_section_99_inspection_reports_received_or_completed"])
        print_table("Source links", payload["inspection_and_district_inspector_sources"], ["title", "url"], limit=10)
    else:
        print_table("Sources", payload["sources"], ["id", "name", "url"])


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", dest="json_output", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help="network timeout in seconds (default: 10)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover NZ mental-health regulatory data sources")
    sub = parser.add_subparsers(dest="command", required=True)

    reports = sub.add_parser("odmhas-reports", help="list ODMHAS annual regulatory reports")
    add_common(reports)
    reports.add_argument("--limit", type=int, default=None, help="limit report rows")
    reports.set_defaults(func=reports_payload)

    seclusion = sub.add_parser("seclusion", help="extract seclusion summary tables from report DOCX")
    add_common(seclusion)
    seclusion.add_argument("--year", required=True, help="report year, e.g. 2023, 2024, or 2023/24")
    seclusion.add_argument("--district", help="filter district/regional-service rows")
    seclusion.set_defaults(func=seclusion_payload)

    kpi = sub.add_parser("kpi", help="MH&A KPI Programme metadata")
    kpi_sub = kpi.add_subparsers(dest="kpi_command", required=True)
    kpi_list = kpi_sub.add_parser("list", help="list public KPI indicators")
    add_common(kpi_list)
    kpi_list.set_defaults(func=kpi_list_payload)
    kpi_get = kpi_sub.add_parser("get", help="inspect one KPI indicator page")
    add_common(kpi_get)
    kpi_get.add_argument("indicator", help="indicator slug or title")
    kpi_get.set_defaults(func=kpi_get_payload)

    kpi_sources = sub.add_parser("kpi-sources", help="list KPI source metadata")
    add_common(kpi_sources)
    kpi_sources.set_defaults(func=kpi_sources_payload)

    inspections = sub.add_parser("inpatient-inspections", help="extract section 95/99 count table and source links")
    add_common(inspections)
    inspections.add_argument("--year", help="report year, e.g. 2023, 2024, or 2023/24")
    inspections.set_defaults(func=inspection_payload)

    for name in ("datasets", "sources"):
        p = sub.add_parser(name, help="list source catalogues and caveats")
        add_common(p)
        p.set_defaults(func=sources_payload, command_name=name)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        emit(payload, args)
        return 0
    except CliError as exc:
        if getattr(args, "json_output", False):
            print(
                json.dumps(
                    {
                        "status": "error",
                        "code": exc.code,
                        "message": str(exc),
                        "source_url": exc.source_url,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"mental-health-data-nz: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 1
    except Exception as exc:  # noqa: BLE001 - keep user-facing errors stacktrace-free.
        print(f"mental-health-data-nz: unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
