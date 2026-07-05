#!/usr/bin/env python3
"""Public CAB NZ / CABNET source discovery CLI.

This skill intentionally does not pretend that national CABNET client-enquiry
counts are public. It exposes public CAB discovery surfaces and returns explicit
blocked-state JSON when a structured CABNET count export is unavailable.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

CAB_BASE = "https://www.cab.org.nz"
CATEGORY_URL = f"{CAB_BASE}/assets/data/categories.json"
CAB_SEARCH_URL = f"{CAB_BASE}/api/v1/search"
CAB_REPORTING_URL = f"{CAB_BASE}/api/v1/reporting"
CAB_INTERVIEW_SEARCH_URL = f"{CAB_BASE}/api/v1/interview/search"
DATA_GOVT_API = "https://catalogue.data.govt.nz/api/3/action/package_search"
DEFAULT_TIMEOUT = 10
UA = "cab-cabnet-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

STRUCTURED_EXPORT_MESSAGE = (
    "No keyless structured CABNET enquiry-count export was found. Public CAB "
    "pages and reports can be discovered, but authenticated reporting endpoints "
    "are forbidden without a CAB session."
)

TAXONOMY_CAVEAT = (
    "Public CAB website advice taxonomy; counts are article/tag counts, not "
    "CABNET client enquiry counts."
)

WELFARE_REPORT = {
    "title": "Mana Aki - Dignity for all",
    "page_url": f"{CAB_BASE}/what-we-do/social-justice/cab-spotlight-reports",
    "news_url": f"{CAB_BASE}/news/cab-report-reveals-harmful-gaps-in-nzs-welfare-support-system",
    "period": "1 November 2023 to 30 April 2025",
    "dataset_summary": "Over 10,000 welfare-related CAB enquiries.",
}

TREND_EVIDENCE = [
    {
        "category": "Core and secondary benefits",
        "aliases": ["benefit", "benefits", "core benefits", "secondary benefits", "income support"],
        "report": WELFARE_REPORT,
        "evidence_type": "pdf_chart_label_and_report_text",
        "period": "May 2020 to April 2025",
        "note": (
            "The welfare spotlight report lists this in Figure 1 as one of five "
            "economic-hardship enquiry indicators over five years."
        ),
    },
    {
        "category": "Budgeting and debt management",
        "aliases": ["budget", "budgeting", "debt", "financial difficulties"],
        "report": WELFARE_REPORT,
        "evidence_type": "pdf_chart_label_and_report_text",
        "period": "May 2020 to April 2025",
        "note": (
            "The report says budgeting, debt management, and hardship-related "
            "KiwiSaver withdrawal enquiries continued rising over recent years."
        ),
    },
    {
        "category": "KiwiSaver withdrawal for hardship",
        "aliases": ["kiwisaver", "hardship withdrawal", "kiwisaver withdrawal"],
        "report": WELFARE_REPORT,
        "evidence_type": "pdf_chart_label_and_report_text",
        "period": "May 2020 to April 2025",
        "note": (
            "The report groups hardship-related KiwiSaver withdrawals with "
            "financial stress indicators that rose over recent years."
        ),
    },
    {
        "category": "Emergency accommodation",
        "aliases": ["emergency accommodation", "emergency housing", "homelessness"],
        "report": WELFARE_REPORT,
        "evidence_type": "pdf_chart_label_and_report_text",
        "period": "May 2020 to April 2025",
        "note": (
            "The report discusses emergency accommodation policy changes and "
            "warns that homelessness need is also spread across related housing "
            "and food categories."
        ),
    },
    {
        "category": "Food assistance",
        "aliases": ["food", "food assistance", "food parcels", "food banks", "foodbanks"],
        "report": WELFARE_REPORT,
        "evidence_type": "pdf_chart_label_and_report_text",
        "period": "May 2020 to April 2025",
        "note": (
            "The report says some food assistance enquiries decreased where local "
            "food banks closed or food-support funding changed, so lower counts "
            "do not necessarily mean lower need."
        ),
    },
    {
        "category": "Rental Housing",
        "aliases": ["rental", "rental housing", "tenancy", "residential tenancy"],
        "report": WELFARE_REPORT,
        "evidence_type": "ranked_level_2_category",
        "period": WELFARE_REPORT["period"],
        "rank": 2,
        "note": (
            "The welfare report says Rental Housing ranked 2nd among nearly 100 "
            "Level 2 CAB categories associated with welfare support."
        ),
    },
    {
        "category": "Income Support",
        "aliases": ["income support", "winz", "work and income", "beneficiary advocacy"],
        "report": WELFARE_REPORT,
        "evidence_type": "ranked_level_2_category",
        "period": WELFARE_REPORT["period"],
        "rank": 12,
        "note": (
            "The welfare report says Income Support ranked 12th overall among "
            "nearly 100 Level 2 CAB categories."
        ),
    },
    {
        "category": "Budgeting and General Financial Difficulties",
        "aliases": ["budgeting and general financial difficulties", "financial hardship"],
        "report": WELFARE_REPORT,
        "evidence_type": "ranked_level_2_category",
        "period": WELFARE_REPORT["period"],
        "rank": 10,
        "note": (
            "The welfare report lists this as one of the five Level 2 categories "
            "most associated with welfare support."
        ),
    },
]


class UpstreamUnavailable(Exception):
    """Raised when a public upstream cannot be reached or parsed."""


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.getcode()), response.read(), response.geturl()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), url
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise UpstreamUnavailable(f"network error calling {url}: {exc}") from exc


def read_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[Any, str, int]:
    status, raw, final_url = fetch(url, timeout=timeout)
    if status >= 400:
        detail = raw.decode("utf-8", "replace")[:220].strip()
        raise UpstreamUnavailable(f"HTTP {status} from {url}: {detail}")
    try:
        return json.loads(raw.decode("utf-8", "replace")), final_url, status
    except json.JSONDecodeError as exc:
        raise UpstreamUnavailable(f"invalid JSON from {url}: {exc}") from exc


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def output(payload: dict[str, Any], as_json: bool, render: Callable[[dict[str, Any]], None]) -> None:
    if as_json:
        emit_json(payload)
    else:
        render(payload)


def blocked(payload: dict[str, Any], as_json: bool, code: int = 2) -> None:
    if as_json:
        emit_json(payload)
    else:
        print(f"cab-cabnet-nz: {payload.get('message') or payload.get('error')}", file=sys.stderr)
        if payload.get("next_steps"):
            print("Next steps:", file=sys.stderr)
            for step in payload["next_steps"]:
                print(f"- {step}", file=sys.stderr)
    raise SystemExit(code)


def upstream_error(message: str, as_json: bool) -> None:
    payload = {
        "kind": "cab-upstream-error",
        "error": "upstream_unavailable",
        "message": message,
    }
    blocked(payload, as_json, code=2)


def die(message: str, code: int = 1) -> None:
    print(f"cab-cabnet-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def clean_text(text: Any, limit: int = 260) -> str:
    plain = re.sub(r"<[^>]+>", " ", str(text or ""))
    plain = html.unescape(re.sub(r"\s+", " ", plain)).strip()
    return plain[:limit].rstrip()


def absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urllib.parse.urljoin(CAB_BASE, url)


def validate_year(raw: str) -> int:
    if not re.fullmatch(r"\d{4}", raw or ""):
        die("--year must be a four-digit year like 2025")
    return int(raw)


def cab_search(query: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    url = f"{CAB_SEARCH_URL}?" + urllib.parse.urlencode({"q": query})
    data, final_url, _status = read_json(url)
    container = data.get("results") if isinstance(data, dict) else {}
    results = container.get("results", []) if isinstance(container, dict) else []
    rows = []
    for item in results:
        rows.append(
            {
                "title": item.get("title"),
                "type": item.get("type"),
                "url": absolute_url(item.get("url")),
                "description": clean_text(item.get("description") or item.get("content")),
                "tags": item.get("tags") or [],
            }
        )
    counts = container.get("counts", {}) if isinstance(container, dict) else {}
    return rows, {"query": data.get("query"), "total_results": data.get("totalResults"), "counts": counts}, final_url


def data_gov_search(query: str, limit: int) -> dict[str, Any]:
    url = DATA_GOVT_API + "?" + urllib.parse.urlencode({"q": query, "rows": limit})
    try:
        data, final_url, _status = read_json(url)
    except UpstreamUnavailable as exc:
        return {"query": query, "error": "upstream_unavailable", "message": str(exc)}
    if not data.get("success"):
        return {"query": query, "error": "api_failure", "message": str(data.get("error"))}
    result = data.get("result", {})
    datasets = []
    for package in result.get("results", []):
        org = package.get("organization") or {}
        datasets.append(
            {
                "name": package.get("name"),
                "title": package.get("title"),
                "organisation": org.get("title") or org.get("name"),
                "url": f"https://catalogue.data.govt.nz/dataset/{package.get('name')}",
            }
        )
    return {
        "query": query,
        "source_url": final_url,
        "count": result.get("count"),
        "datasets": datasets,
    }


def probe_endpoint(url: str) -> dict[str, Any]:
    try:
        status, raw, final_url = fetch(url)
    except UpstreamUnavailable as exc:
        return {"url": url, "public_status": "unavailable", "message": str(exc)}
    text = raw.decode("utf-8", "replace").strip()
    payload: Any = None
    try:
        payload = json.loads(text) if text else None
    except json.JSONDecodeError:
        payload = None
    if status == 403 or (isinstance(payload, dict) and str(payload.get("error")).lower() == "forbidden"):
        public_status = "forbidden"
    elif status >= 400:
        public_status = f"http_{status}"
    else:
        public_status = "reachable"
    return {
        "url": final_url,
        "http_status": status,
        "public_status": public_status,
        "response_preview": clean_text(text, 120),
    }


def flatten_categories(nodes: list[dict[str, Any]], parents: list[str] | None = None) -> list[dict[str, Any]]:
    parents = parents or []
    rows: list[dict[str, Any]] = []
    for node in nodes:
        name = str(node.get("name") or "")
        path_parts = [*parents, name]
        level = len(path_parts)
        row = {
            "id": node.get("id"),
            "level": level,
            "name": name,
            "slug": node.get("slug"),
            "path": " > ".join(path_parts),
            "url": absolute_url(node.get("url")),
            "article_count": node.get("relatedArticleCount", node.get("count")),
        }
        rows.append(row)
        children = node.get("children") or []
        if isinstance(children, list):
            rows.extend(flatten_categories(children, path_parts))
    return rows


def load_categories() -> tuple[list[dict[str, Any]], str]:
    data, final_url, _status = read_json(CATEGORY_URL)
    if not isinstance(data, list):
        raise UpstreamUnavailable("CAB category payload was not a list")
    return flatten_categories(data), final_url


def blocked_enquiries_payload(year: int, category: str | None) -> dict[str, Any]:
    return {
        "kind": "cabnet-enquiries",
        "status": "blocked",
        "error": "structured_export_unavailable",
        "source": "CAB NZ CABNET",
        "year": year,
        "category": category,
        "message": STRUCTURED_EXPORT_MESSAGE,
        "checked_public_sources": [
            {
                "name": "CAB public search",
                "url": CAB_SEARCH_URL,
                "status": "public discovery only, not aggregate enquiry counts",
            },
            {
                "name": "CAB reporting API",
                "url": CAB_REPORTING_URL,
                "status": "forbidden without authenticated CAB session",
            },
            {
                "name": "CAB interview search API",
                "url": CAB_INTERVIEW_SEARCH_URL,
                "status": "forbidden without authenticated CAB session",
            },
            {
                "name": "data.govt.nz",
                "url": "https://catalogue.data.govt.nz/",
                "status": "no CABNET enquiry-statistics dataset found during implementation",
            },
        ],
        "next_steps": [
            "Use the sources command to discover public CAB reports and pages.",
            "Request a CAB CSV/XLSX/JSON release if exact national enquiry counts are required.",
        ],
    }


def cmd_sources(args: argparse.Namespace) -> None:
    try:
        results, meta, source_url = cab_search(args.query)
    except UpstreamUnavailable as exc:
        upstream_error(str(exc), args.json)
    public_results = results[: args.limit]
    payload = {
        "kind": "cab-source-discovery",
        "source": "cab.org.nz and data.govt.nz",
        "query": args.query,
        "cab_search": {
            **meta,
            "source_url": source_url,
            "returned": len(public_results),
        },
        "public_search_results": public_results,
        "cabnet_reporting": probe_endpoint(CAB_REPORTING_URL),
        "cabnet_interview_search": probe_endpoint(CAB_INTERVIEW_SEARCH_URL),
        "data_govt_nz_checks": [
            data_gov_search("Citizens Advice Bureau CABNET enquiries", args.limit),
            data_gov_search("CAB client enquiry statistics", args.limit),
        ],
        "structured_export_status": "not_found_publicly",
        "message": STRUCTURED_EXPORT_MESSAGE,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"CAB public source discovery for {p['query']!r}")
        print(f"CAB search results shown: {len(p['public_search_results'])}")
        for row in p["public_search_results"]:
            print(f"- {row.get('title')} [{row.get('type')}]")
            print(f"  {row.get('url')}")
        print(f"CABNET reporting endpoint: {p['cabnet_reporting']['public_status']}")
        print(f"CABNET interview endpoint: {p['cabnet_interview_search']['public_status']}")
        print(p["message"])

    output(payload, args.json, render)


def cmd_categories(args: argparse.Namespace) -> None:
    try:
        rows, source_url = load_categories()
    except UpstreamUnavailable as exc:
        upstream_error(str(exc), args.json)
    if args.query:
        wanted = norm(args.query)
        rows = [row for row in rows if wanted in norm(row.get("path", ""))]
    rows = rows[: args.limit]
    payload = {
        "kind": "cab-category-taxonomy",
        "source": "cab-public-website-categories",
        "source_url": source_url,
        "taxonomy_caveat": TAXONOMY_CAVEAT,
        "query": args.query,
        "count": len(rows),
        "categories": rows,
    }

    def render(p: dict[str, Any]) -> None:
        print("CAB public website categories")
        print(p["taxonomy_caveat"])
        for row in p["categories"]:
            count = "" if row.get("article_count") is None else f" ({row['article_count']})"
            print(f"- L{row['level']} {row['path']}{count}")

    output(payload, args.json, render)


def cmd_enquiries(args: argparse.Namespace) -> None:
    year = validate_year(args.year)
    blocked(blocked_enquiries_payload(year, args.category), args.json, code=2)


def cmd_trends(args: argparse.Namespace) -> None:
    wanted = norm(args.category)
    matches = []
    for item in TREND_EVIDENCE:
        haystack = [item["category"], *item.get("aliases", [])]
        if any(wanted in norm(value) or norm(value) in wanted for value in haystack):
            record = {k: v for k, v in item.items() if k != "aliases"}
            report = record.get("report", {})
            if isinstance(report, dict):
                record["report"] = {
                    "title": report.get("title"),
                    "period": report.get("period"),
                    "dataset_summary": report.get("dataset_summary"),
                    "page_url": report.get("page_url"),
                    "news_url": report.get("news_url"),
                }
            matches.append(record)
    payload = {
        "kind": "cabnet-trends",
        "source": "CAB public spotlight reports",
        "category_query": args.category,
        "status": "partial_report_evidence" if matches else "no_public_structured_trend",
        "exact_counts_available": False,
        "message": (
            "Public reports contain useful trend evidence, but no public "
            "machine-readable CABNET time series was found."
        ),
        "trends": matches,
    }

    def render(p: dict[str, Any]) -> None:
        print(f"CAB trend evidence for {p['category_query']!r}")
        print(p["message"])
        if not p["trends"]:
            print("No matching public report-backed trend was bundled for this category.")
            return
        for row in p["trends"]:
            print(f"- {row['category']} ({row['period']})")
            if row.get("rank"):
                print(f"  rank: {row['rank']}")
            print(f"  {row['note']}")

    output(payload, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover public CAB NZ CABNET enquiry evidence and source availability"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="discover public CAB pages/reports and blocked CABNET endpoints")
    sources.add_argument("--query", default="CAB Spotlight Reports enquiry data")
    sources.add_argument("--limit", type=int, default=5)
    sources.add_argument("--json", action="store_true")
    sources.set_defaults(func=cmd_sources)

    categories = sub.add_parser("categories", help="list public CAB website advice categories")
    categories.add_argument("--query", help="filter category paths")
    categories.add_argument("--limit", type=int, default=200)
    categories.add_argument("--json", action="store_true")
    categories.set_defaults(func=cmd_categories)

    enquiries = sub.add_parser("enquiries", help="CABNET enquiry counts by year/category when public export exists")
    enquiries.add_argument("--year", required=True, help="four-digit year, e.g. 2025")
    enquiries.add_argument("--category", help="category name to request")
    enquiries.add_argument("--json", action="store_true")
    enquiries.set_defaults(func=cmd_enquiries)

    trends = sub.add_parser("trends", help="report-backed CAB enquiry trend evidence for a category")
    trends.add_argument("--category", required=True)
    trends.add_argument("--json", action="store_true")
    trends.set_defaults(func=cmd_trends)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "limit", 1) is not None and getattr(args, "limit", 1) < 1:
        die("--limit must be at least 1")
    args.func(args)


if __name__ == "__main__":
    main()
