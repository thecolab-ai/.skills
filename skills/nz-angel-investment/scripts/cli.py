#!/usr/bin/env python3
"""Read-only CLI for New Zealand angel and seed investment source discovery.

Sources:
- NZGCP Young Company Finance PDFs and NZGCP report listing pages.
- Angel Association New Zealand members and investment publication pages.

Standard library only. No login, paid Dealroom API access, browser automation, or mutation.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import pathlib
import re
import sys
import textwrap
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

NZGCP_BASE = "https://www.nzgcp.co.nz"
NZGCP_REPORTS_URL = NZGCP_BASE + "/about-us/news-and-media/view/reports"
NZGCP_YCF_URL = NZGCP_BASE + "/about-us/news-and-media/view/reports/startup-investment-magazine"
NZGCP_ANNUAL_URL = NZGCP_BASE + "/about-us/news-and-media/view/reports/annual-report"

AANZ_BASE = "https://www.angelassociation.co.nz"
AANZ_MEMBERS_URL = AANZ_BASE + "/members/"
AANZ_PUBLICATIONS_URL = AANZ_BASE + "/resources/investment-publications/"
AANZ_PUBLICATIONS_REST = AANZ_BASE + "/wp-json/wp/v2/pages/1124"
AANZ_DOWNLOAD_REST = AANZ_BASE + "/wp-json/wp/v2/dlm_download"

DEFAULT_TIMEOUT = 10
DEFAULT_LIMIT = 25
MAX_LIMIT = 100
UA = "nz-angel-investment-skill/1.0 (+https://github.com/thecolab-ai/.skills)"


class UpstreamUnavailable(RuntimeError):
    pass


YCF_RELEASES: list[dict[str, Any]] = [
    {
        "period": "2025",
        "aliases": ["2025", "calendar-2025", "autumn-2026", "nzgcp-ycf-autumn-2026"],
        "title": "Young Company Finance - Autumn 2026",
        "coverage": "Calendar year 2025",
        "published": "2026-04-15",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-YCF-Autumn-2026.pdf",
        "source_page": NZGCP_REPORTS_URL,
        "metrics": {
            "deal_count": 166,
            "investment_amount_nzd_millions": 754,
            "new_companies_funded": 47,
            "stage_split": None,
        },
        "extraction": {
            "status": "curated",
            "notes": [
                "Headline metrics are curated from the NZGCP YCF Autumn 2026 publication.",
                "Stage split is not exposed here because stdlib-only PDF parsing is not reliable enough for the chart layout.",
            ],
        },
    },
    {
        "period": "2025-H1",
        "aliases": ["2025-h1", "spring-2025", "nzgcp-ycf-spring-2025"],
        "title": "Young Company Finance - Spring 2025",
        "coverage": "First half 2025, verify exact convention in source PDF",
        "published": "2025-10-31",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-YCF-Spring-2025-v2.pdf",
        "source_page": NZGCP_YCF_URL,
        "metrics": {},
        "extraction": {
            "status": "source_discovery_only",
            "notes": ["Metrics require manual PDF/table extraction before reuse."],
        },
    },
    {
        "period": "2024",
        "aliases": ["2024", "calendar-2024", "autumn-2025", "nzgcp-ycf-autumn-2025"],
        "title": "Young Company Finance - Autumn 2025",
        "coverage": "Calendar year 2024 / second half 2024 commentary, verify exact convention in source PDF",
        "published": "2025-03-25",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-YCF-Autumn-2025.pdf",
        "source_page": NZGCP_YCF_URL,
        "metrics": {},
        "extraction": {
            "status": "source_discovery_only",
            "notes": ["Metrics require manual PDF/table extraction before reuse."],
        },
    },
    {
        "period": "2024-H1",
        "aliases": ["2024-h1", "spring-2024", "nzgcp-ycf-spring-2024"],
        "title": "Young Company Finance - Spring 2024",
        "coverage": "First half 2024, verify exact convention in source PDF",
        "published": "2024-11-18",
        "url": NZGCP_BASE + "/assets/Media/YCF-Spring-2024.pdf",
        "source_page": NZGCP_YCF_URL,
        "metrics": {},
        "extraction": {
            "status": "source_discovery_only",
            "notes": ["Metrics require manual PDF/table extraction before reuse."],
        },
    },
]

CURATED_NZGCP_REPORTS: list[dict[str, Any]] = [
    {
        "title": "NZGCP Annual Report 2025",
        "kind": "annual_report",
        "year": "2025",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-Annual-Report-2025-FINAL.pdf",
        "source_page": NZGCP_ANNUAL_URL,
    },
    {
        "title": "NZGCP Annual Report 2024",
        "kind": "annual_report",
        "year": "2024",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-Annual-Report-2024.pdf",
        "source_page": NZGCP_ANNUAL_URL,
    },
    {
        "title": "NZGCP Annual Report 2023",
        "kind": "annual_report",
        "year": "2023",
        "url": NZGCP_BASE + "/assets/Media/NZGCP-Annual-Report-2023_FINAL.pdf",
        "source_page": NZGCP_ANNUAL_URL,
    },
    {
        "title": "Dealroom NZ Report 2025",
        "kind": "dealroom_report",
        "year": "2025",
        "url": NZGCP_BASE + "/assets/Media/New-Zealand-2025-report.pdf",
        "source_page": NZGCP_REPORTS_URL,
    },
]

SOURCE_CATALOGUE: list[dict[str, Any]] = [
    {
        "name": "NZGCP Young Company Finance",
        "url": NZGCP_YCF_URL,
        "kind": "pdf_publication_series",
        "access": "keyless public PDF/HTML",
        "notes": "Headline early-stage deal count and dollars series. No public machine-readable feed; PDF tables/charts need conservative extraction.",
    },
    {
        "name": "NZGCP annual and ecosystem reports",
        "url": NZGCP_REPORTS_URL,
        "kind": "pdf_publication_index",
        "access": "keyless public PDF/HTML",
        "notes": "Annual reports, Dealroom ecosystem reports, Statements of Intent, and performance documents.",
    },
    {
        "name": "Angel Association NZ members",
        "url": AANZ_MEMBERS_URL,
        "kind": "html_member_directory",
        "access": "keyless public HTML/AJAX",
        "notes": "MyListing directory. The CLI uses the public page nonce and parses listing-preview cards.",
    },
    {
        "name": "Angel Association NZ investment publications",
        "url": AANZ_PUBLICATIONS_URL,
        "kind": "wordpress_page_and_downloads",
        "access": "keyless public HTML/REST/PDF",
        "notes": "Current and past Angel Market / startup investment publications. Download records are exposed through WordPress REST.",
    },
    {
        "name": "Dealroom NZ",
        "url": "https://nz.dealroom.co/",
        "kind": "commercial_database",
        "access": "paid/commercial API out of scope",
        "notes": "Useful primary database, but not keyless. This skill only links public NZGCP Dealroom reports.",
    },
]


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def absolute_url(base: str, url: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(url))


def limit_value(value: int) -> int:
    return max(1, min(MAX_LIMIT, value))


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(url, timeout=timeout, headers=headers)
        return body
    except nzfetch.Blocked as exc:
        raise UpstreamUnavailable(f"network error fetching {url}: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
    except TimeoutError as exc:
        raise UpstreamUnavailable(f"network error fetching {url}: timeout") from exc


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8", "replace")


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    raw = fetch_text(url, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpstreamUnavailable(f"invalid JSON from {url}: {exc}") from exc


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self._current = {"href": href, "text": ""}
                self._depth = 1
        elif self._current is not None:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        self._depth -= 1
        if tag.lower() == "a" or self._depth <= 0:
            self._current["text"] = clean_text(self._current["text"])
            self.links.append(self._current)
            self._current = None
            self._depth = 0

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data + " "


def extract_links(html_text: str) -> list[dict[str, str]]:
    parser = LinkExtractor()
    parser.feed(html_text)
    return parser.links


def record_basics(title: str, url: str, source_page: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    filename = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
    year_match = re.search(r"(20\d{2})", title + " " + filename)
    return {
        "title": clean_text(title),
        "url": url,
        "source_page": source_page,
        "filename": filename,
        "year": year_match.group(1) if year_match else None,
        "kind": kind_from_title(title + " " + filename),
    }


def kind_from_title(text: str) -> str:
    lower = text.lower()
    if "young company finance" in lower or re.search(r"\bycf\b", lower):
        return "young_company_finance"
    if "annual report" in lower:
        return "annual_report"
    if "dealroom" in lower:
        return "dealroom_report"
    if "angel market" in lower:
        return "angel_market_report"
    if "startup investment" in lower or "start-up investment" in lower:
        return "startup_investment_publication"
    if "statement of performance" in lower:
        return "statement_of_performance_expectations"
    if "statement of intent" in lower:
        return "statement_of_intent"
    return "publication"


def merge_by_url(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for record in records:
        url = record.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(record)
    return merged


def discover_nzgcp_report_links(url: str, timeout: int) -> list[dict[str, Any]]:
    text = fetch_text(url, timeout=timeout)
    records: list[dict[str, Any]] = []
    for href, title in re.findall(r'<h4>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>\s*</h4>', text, re.S):
        abs_url = absolute_url(NZGCP_BASE, href)
        title = clean_text(title)
        if not title or "/assets/Media/" not in abs_url:
            continue
        records.append(record_basics(title, abs_url, url))
    return records


def ycf_record_for(period: str) -> dict[str, Any] | None:
    wanted = period.strip().lower()
    for record in YCF_RELEASES:
        aliases = [str(record["period"]).lower(), *[str(a).lower() for a in record.get("aliases", [])]]
        if wanted in aliases:
            return record
    return None


def command_ycf_list(args: argparse.Namespace) -> dict[str, Any]:
    records = [dict(r) for r in YCF_RELEASES]
    warnings: list[str] = []
    if args.discover:
        try:
            discovered = discover_nzgcp_report_links(NZGCP_YCF_URL, args.timeout)
            ycf = [r for r in discovered if r["kind"] == "young_company_finance"]
            known_urls = {r["url"] for r in records}
            for record in ycf:
                if record["url"] not in known_urls:
                    record["period"] = infer_period(record["title"])
                    record["metrics"] = {}
                    record["extraction"] = {
                        "status": "source_discovery_only",
                        "notes": ["Discovered from NZGCP report page; metrics not extracted."],
                    }
                    records.append(record)
        except UpstreamUnavailable as exc:
            warnings.append(str(exc))
    records = records[: limit_value(args.limit)]
    return {
        "kind": "ycf_releases",
        "source": "NZGCP Young Company Finance PDFs",
        "source_url": NZGCP_YCF_URL,
        "count": len(records),
        "records": records,
        "warnings": warnings,
        "caveats": [
            "There is no keyless machine-readable YCF feed.",
            "Only curated headline metrics should be treated as extracted data; other records are source discovery entries.",
        ],
    }


def infer_period(title: str) -> str | None:
    lower = title.lower()
    year = re.search(r"(20\d{2})", title)
    if not year:
        return None
    if "spring" in lower:
        return year.group(1) + "-H1"
    if "autumn" in lower:
        return year.group(1)
    return year.group(1)


def command_ycf_get(args: argparse.Namespace) -> dict[str, Any]:
    record = ycf_record_for(args.period)
    if record is None:
        raise KeyError(f"YCF period not found: {args.period}")
    output = dict(record)
    output["kind"] = "ycf_release"
    output["caveats"] = [
        "YCF is PDF-first. Use url/source_page for audit trails and manually verify chart/table metrics before citation.",
        "Dealroom is a paid commercial database and is linked only as context, not queried.",
    ]
    return output


def command_nzgcp_reports(args: argparse.Namespace) -> dict[str, Any]:
    records = [dict(r) for r in CURATED_NZGCP_REPORTS]
    warnings: list[str] = []
    if args.discover:
        try:
            discovered = discover_nzgcp_report_links(NZGCP_REPORTS_URL, args.timeout)
            records = merge_by_url(discovered + records)
        except UpstreamUnavailable as exc:
            warnings.append(str(exc))
    if args.kind:
        records = [r for r in records if r.get("kind") == args.kind]
    records = records[: limit_value(args.limit)]
    return {
        "kind": "nzgcp_reports",
        "source": "NZGCP report pages and curated known report URLs",
        "source_url": NZGCP_REPORTS_URL,
        "count": len(records),
        "records": records,
        "warnings": warnings,
    }


def aanz_nonce(timeout: int) -> str:
    text = fetch_text(AANZ_MEMBERS_URL, timeout=timeout)
    match = re.search(r'"ajax_nonce"\s*:\s*"([^"]+)"', text)
    if not match:
        raise UpstreamUnavailable("could not find Angel Association member-directory nonce")
    return html.unescape(match.group(1))


def fetch_investor_page(page: int, nonce: str, timeout: int) -> dict[str, Any]:
    params = {
        "mylisting-ajax": "1",
        "action": "get_listings",
        "security": nonce,
        "listing_type": "place",
        "listing_wrap": "col-md-6 col-sm-6 grid-item",
        "form_data[page]": str(page),
        "form_data[preserve_page]": "false",
        "form_data[search_keywords]": "",
        "form_data[region]": "",
        "form_data[sort]": "a-z",
    }
    url = AANZ_BASE + "/?" + urllib.parse.urlencode(params)
    data = fetch_json(url, timeout=timeout)
    if not isinstance(data, dict) or "html" not in data:
        raise UpstreamUnavailable("unexpected Angel Association member-directory response")
    data["source_url"] = url
    return data


def parse_locations(raw: str) -> list[dict[str, Any]]:
    raw = html.unescape(raw or "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def parse_investor_cards(html_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    parts = re.split(r'(?=<div\s+class="lf-item-container\b)', html_text)
    for part in parts:
        if "lf-item-container" not in part:
            continue
        class_match = re.search(r'class="([^"]*\blf-item-container\b[^"]*)"', part, re.S)
        classes = class_match.group(1) if class_match else ""
        id_match = re.search(r'data-id="listing-id-(\d+)"', part)
        link_match = re.search(r'<a\s+href="([^"]+)"', part)
        title_match = re.search(r'<h4[^>]*listing-preview-title[^>]*>(.*?)</h4>', part, re.S)
        tagline_match = re.search(r"<h6[^>]*>(.*?)</h6>", part, re.S)
        locations_match = re.search(r'data-locations="([^"]*)"', part, re.S)
        email_match = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', clean_text(part))
        if not title_match:
            continue
        region_slugs = sorted(set(re.findall(r"\bregion-([a-z0-9-]+)\b", classes)))
        locations = parse_locations(locations_match.group(1) if locations_match else "")
        records.append(
            {
                "id": id_match.group(1) if id_match else None,
                "name": clean_text(title_match.group(1)),
                "url": html.unescape(link_match.group(1)) if link_match else None,
                "region_slugs": region_slugs,
                "regions": [slug.replace("-", " ").title() for slug in region_slugs],
                "focus": clean_text(tagline_match.group(1)) if tagline_match else "",
                "email": email_match.group(0) if email_match else None,
                "locations": locations,
            }
        )
    return records


def investor_matches(record: dict[str, Any], args: argparse.Namespace) -> bool:
    haystack = " ".join(
        [
            record.get("name") or "",
            record.get("focus") or "",
            " ".join(record.get("regions") or []),
            " ".join(record.get("region_slugs") or []),
        ]
    ).lower()
    if args.query and args.query.lower() not in haystack:
        return False
    if args.region:
        region = args.region.lower().replace(" ", "-")
        if region not in {str(r).lower() for r in record.get("region_slugs", [])}:
            if args.region.lower() not in haystack:
                return False
    return True


def command_investors(args: argparse.Namespace) -> dict[str, Any]:
    nonce = aanz_nonce(args.timeout)
    records: list[dict[str, Any]] = []
    found_posts = None
    max_pages = 1
    source_urls: list[str] = []
    for page in range(MAX_LIMIT):
        data = fetch_investor_page(page, nonce, args.timeout)
        source_urls.append(data.get("source_url", AANZ_MEMBERS_URL))
        found_posts = data.get("found_posts", found_posts)
        max_pages = int(data.get("max_num_pages") or max_pages)
        for record in parse_investor_cards(str(data.get("html") or "")):
            if investor_matches(record, args):
                records.append(record)
                if len(records) >= limit_value(args.limit):
                    break
        if len(records) >= limit_value(args.limit) or page + 1 >= max_pages:
            break
    return {
        "kind": "angel_investors",
        "source": "Angel Association NZ member directory",
        "source_url": AANZ_MEMBERS_URL,
        "ajax_source_urls": source_urls,
        "count": len(records),
        "found_posts": found_posts,
        "filters": {k: getattr(args, k) for k in ("query", "region") if getattr(args, k, None)},
        "records": records,
    }


def download_records(search: str, timeout: int) -> list[dict[str, Any]]:
    params = {"search": search, "per_page": 30}
    url = AANZ_DOWNLOAD_REST + "?" + urllib.parse.urlencode(params)
    data = fetch_json(url, timeout=timeout)
    if not isinstance(data, list):
        raise UpstreamUnavailable("unexpected Angel Association downloads REST response")
    records = []
    for item in data:
        title = clean_text(urllib.parse.unquote_plus(item.get("title", {}).get("rendered", "")))
        link = item.get("link")
        if not title or not link:
            continue
        record = record_basics(title, link, url)
        record.update(
            {
                "id": item.get("id"),
                "date": item.get("date"),
                "modified": item.get("modified"),
                "source": "Angel Association NZ WordPress downloads",
            }
        )
        records.append(record)
    return records


def publication_links_from_page(timeout: int) -> list[dict[str, Any]]:
    data = fetch_json(AANZ_PUBLICATIONS_REST, timeout=timeout)
    rendered = data.get("content", {}).get("rendered", "") if isinstance(data, dict) else ""
    records: list[dict[str, Any]] = []
    for link in extract_links(rendered):
        href = absolute_url(AANZ_BASE, link["href"])
        title = clean_text(link["text"]) or href.rsplit("/", 1)[-1]
        if not href or href.startswith("mailto:"):
            continue
        lower = (title + " " + href).lower()
        if not any(term in lower for term in ("angel market", "young company", "ycf", "startup", "start-up", "catalist", "pwc")):
            continue
        record = record_basics(title, href, AANZ_PUBLICATIONS_URL)
        record["source"] = "Angel Association NZ investment-publications page"
        records.append(record)
    return records


def command_publications(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    try:
        records.extend(publication_links_from_page(args.timeout))
    except UpstreamUnavailable as exc:
        warnings.append(str(exc))
    for search in ("Angel Market", "NZGCP YCF", "Catalist"):
        try:
            records.extend(download_records(search, args.timeout))
        except UpstreamUnavailable as exc:
            warnings.append(str(exc))
    records = merge_by_url(records)
    if args.kind:
        records = [r for r in records if r.get("kind") == args.kind]
    records = records[: limit_value(args.limit)]
    if not records and warnings:
        raise UpstreamUnavailable("; ".join(warnings))
    return {
        "kind": "investment_publications",
        "source": "Angel Association NZ investment publications and download records",
        "source_url": AANZ_PUBLICATIONS_URL,
        "count": len(records),
        "records": records,
        "warnings": warnings,
        "caveats": [
            "Download URLs may be WordPress download handlers rather than permanent PDF asset URLs.",
            "The CLI discovers publications and metadata; it does not parse full PDF tables.",
        ],
    }


def command_sources(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "kind": "source_catalogue",
        "count": len(SOURCE_CATALOGUE),
        "sources": SOURCE_CATALOGUE,
        "caveats": [
            "No public keyless transactional database exists for these figures.",
            "PDF chart/table extraction should remain evidence-backed and manually verified before citation.",
        ],
    }


def emit(data: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_human(data)


def emit_error(error: str, message: str, args: argparse.Namespace, code: int) -> None:
    if getattr(args, "json", False):
        print(json.dumps({"error": error, "message": message}, indent=2), file=sys.stderr if code != 1 else sys.stdout)
    else:
        print(f"nz-angel-investment: {message}", file=sys.stderr)
    raise SystemExit(code)


def print_human(data: dict[str, Any]) -> None:
    print(f"{data.get('source', data.get('kind'))}: {data.get('count', 0)} record(s)")
    for warning in data.get("warnings", []):
        print(f"Warning: {warning}")
    records = data.get("records") or data.get("sources") or []
    for record in records[:DEFAULT_LIMIT]:
        title = record.get("title") or record.get("name")
        url = record.get("url") or record.get("source_page")
        detail = record.get("period") or record.get("year") or ", ".join(record.get("regions") or [])
        if detail:
            print(f"- {title} ({detail})")
        else:
            print(f"- {title}")
        if record.get("focus"):
            print(textwrap.fill("  " + record["focus"], width=88))
        if url:
            print(f"  {url}")


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout in seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nz-angel-investment",
        description="Discover NZGCP and Angel Association NZ angel/seed investment publications and investor sources.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ycf = sub.add_parser("ycf", help="Young Company Finance releases")
    ycf_sub = ycf.add_subparsers(dest="ycf_command", required=True)
    ycf_list = ycf_sub.add_parser("list", help="list known YCF releases")
    add_common(ycf_list)
    ycf_list.add_argument("--discover", action="store_true", help="refresh from the NZGCP YCF reports page")
    ycf_list.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ycf_list.set_defaults(func=command_ycf_list)
    ycf_get = ycf_sub.add_parser("get", help="get one YCF release by period or alias")
    add_common(ycf_get)
    ycf_get.add_argument("period", help="period or alias, e.g. 2025, autumn-2026, 2025-H1")
    ycf_get.set_defaults(func=command_ycf_get)

    reports = sub.add_parser("nzgcp-reports", help="list NZGCP annual/ecosystem reports")
    add_common(reports)
    reports.add_argument("--no-discover", dest="discover", action="store_false", help="use curated report URLs only")
    reports.set_defaults(discover=True)
    reports.add_argument("--kind", help="filter by kind, e.g. annual_report, dealroom_report, young_company_finance")
    reports.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    reports.set_defaults(func=command_nzgcp_reports)

    investors = sub.add_parser("investors", help="list Angel Association NZ member/investor directory entries")
    add_common(investors)
    investors.add_argument("--query", help="filter by text in name/focus/region")
    investors.add_argument("--region", help="filter by region slug or name")
    investors.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    investors.set_defaults(func=command_investors)

    pubs = sub.add_parser("publications", help="list Angel Association NZ investment publications")
    add_common(pubs)
    pubs.add_argument("--kind", help="filter by kind, e.g. angel_market_report, young_company_finance")
    pubs.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    pubs.set_defaults(func=command_publications)

    sources = sub.add_parser("sources", help="show source catalogue and caveats")
    sources.add_argument("--json", action="store_true", help="print machine-readable JSON")
    sources.set_defaults(func=command_sources)
    datasets = sub.add_parser("datasets", help="alias for sources")
    datasets.add_argument("--json", action="store_true", help="print machine-readable JSON")
    datasets.set_defaults(func=command_sources)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = args.func(args)
    except UpstreamUnavailable as exc:
        emit_error("upstream_unavailable", str(exc), args, 2)
    except KeyError as exc:
        emit_error("not_found", str(exc).strip("'"), args, 1)
    except ValueError as exc:
        emit_error("invalid_request", str(exc), args, 1)
    emit(data, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
