#!/usr/bin/env python3
"""SEEK.co.nz lightweight public job-search CLI.

Read-only stdlib wrapper around SEEK NZ public search/detail pages. No login,
account, application, saved-search, or job-application mutation.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NoReturn

BASE = "https://nz.seek.com"
UA = os.environ.get(
    "SEEK_CO_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(message: str, code: int = 1) -> NoReturn:
    print(f"seek-co-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_text(url: str, *, timeout: int = 30) -> tuple[str, str]:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
        "Referer": "https://www.seek.co.nz/",
        "Upgrade-Insecure-Requests": "1",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return raw, resp.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {strip_tags(raw)[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def slug(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def search_url(keywords: str, where: str | None = None, page: int = 1) -> str:
    if not keywords.strip():
        die("search requires non-empty keywords")
    path = f"/{slug(keywords)}-jobs"
    if where and where.strip():
        path += f"/in-{slug(where)}"
    params: dict[str, str] = {}
    if page > 1:
        params["page"] = str(page)
    return BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<style\b.*?</style>", " ", fragment, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def attr(fragment: str, name: str) -> str | None:
    m = re.search(rf"\b{name}=(['\"])(.*?)\1", fragment, flags=re.S)
    return html.unescape(m.group(2)) if m else None


def first_data_text(fragment: str, automation: str) -> str | None:
    m = re.search(
        rf"<(?P<tag>[a-z0-9]+)\b(?=[^>]*\bdata-automation=(['\"]){re.escape(automation)}\2)[^>]*>(?P<body>.*?)</(?P=tag)>",
        fragment,
        flags=re.S | re.I,
    )
    return strip_tags(m.group("body")) if m else None


def all_data_text(fragment: str, automation: str) -> list[str]:
    values: list[str] = []
    for m in re.finditer(
        rf"<(?P<tag>[a-z0-9]+)\b(?=[^>]*\bdata-automation=(['\"]){re.escape(automation)}\2)[^>]*>(?P<body>.*?)</(?P=tag)>",
        fragment,
        flags=re.S | re.I,
    ):
        value = strip_tags(m.group("body"))
        if value and value not in values:
            values.append(value)
    return values


def extract_article_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for m in re.finditer(r"<article\b(?=[^>]*\bdata-testid=(['\"])job-card\1)", text):
        start = m.start()
        end = text.find("</article>", start)
        if end != -1:
            blocks.append(text[start : end + len("</article>")])
    return blocks


def clean_location(parts: list[str]) -> str | None:
    out: list[str] = []
    for part in parts:
        part = re.sub(r"\(\s*", "(", part)
        if part and part not in out:
            out.append(part)
    if not out:
        return None
    value = ", ".join(out)
    value = value.replace(", ,", ",")
    return re.sub(r"\s+", " ", value).strip(" ,")


def parse_job_card(block: str) -> dict[str, Any]:
    job_id = attr(block, "data-job-id")
    title = first_data_text(block, "jobTitle") or attr(block, "aria-label")
    company = first_data_text(block, "jobCompany")
    locations = all_data_text(block, "jobLocation")
    location = clean_location(locations)
    work_arrangement = first_data_text(block, "work-arrangement") or None
    if not work_arrangement:
        m = re.search(r"data-testid=(['\"])work-arrangement\1[^>]*>(.*?)</span>", block, flags=re.S)
        work_arrangement = strip_tags(m.group(2)).strip("()") if m else None
    if work_arrangement:
        work_arrangement = work_arrangement.strip().strip("()")
    work_type = None
    for candidate in re.findall(r"This is a ([^<]+?) job", block, flags=re.I):
        candidate = html.unescape(candidate).strip()
        if candidate.lower() != "featured":
            work_type = candidate
            break
    href = None
    m = re.search(r"<a\b(?=[^>]*\bdata-automation=(['\"])jobTitle\1)[^>]*\bhref=(['\"])(.*?)\2", block, flags=re.S)
    if m:
        href = html.unescape(m.group(3))
    url = urllib.parse.urljoin(BASE, href) if href else (f"{BASE}/job/{job_id}" if job_id else None)
    salary = first_data_text(block, "jobSalary")
    summary = first_data_text(block, "jobShortDescription")
    subclassification = first_data_text(block, "jobSubClassification")
    classification = first_data_text(block, "jobClassification")
    if classification:
        classification = classification.strip("()")
    listed = first_data_text(block, "jobListingDate")
    promoted = "data-automation=\"premiumJob\"" in block or "This is a featured job" in block
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "work_type": work_type,
        "work_arrangement": work_arrangement,
        "salary": salary,
        "summary": summary,
        "classification": classification,
        "subclassification": subclassification,
        "listed": listed,
        "promoted": promoted,
        "url": url,
    }


def parse_total_count(text: str) -> int | None:
    for pattern in [
        r"<h1[^>]*>\s*([0-9,]+)\s+[^<]*jobs?",
        r"Find your ideal job at SEEK with\s*([0-9,]+)",
        r"epn\.jobs_count=([0-9,]+)",
    ]:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def parse_search_page(text: str, *, source_url: str, elapsed_ms: int, limit: int) -> dict[str, Any]:
    jobs = [parse_job_card(block) for block in extract_article_blocks(text)]
    jobs = [job for job in jobs if job.get("job_id") or job.get("title")]
    return {
        "source_url": source_url,
        "total_count": parse_total_count(text),
        "returned_count": len(jobs[:limit]),
        "elapsed_ms": elapsed_ms,
        "jobs": jobs[:limit],
    }


def extract_assignment(text: str, name: str) -> dict[str, Any] | None:
    m = re.search(rf"window\.{re.escape(name)}\s*=\s*(\{{.*?\}});\n", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def parse_detail_page(text: str, *, source_url: str, elapsed_ms: int) -> dict[str, Any]:
    sk_dl = extract_assignment(text, "SK_DL") or {}
    title = first_data_text(text, "job-detail-title") or sk_dl.get("jobTitle")
    company = first_data_text(text, "advertiser-name") or sk_dl.get("advertiserName")
    detail_match = re.search(r"<div\b(?=[^>]*\bdata-automation=(['\"])jobAdDetails\1)[^>]*>(.*?)</div>\s*</div>\s*</section>", text, flags=re.S)
    description = strip_tags(detail_match.group(2)) if detail_match else None
    return {
        "source_url": source_url,
        "elapsed_ms": elapsed_ms,
        "job": {
            "job_id": sk_dl.get("jobId"),
            "title": title,
            "company": company,
            "status": sk_dl.get("jobStatus"),
            "posted": sk_dl.get("jobPostedTime"),
            "area": sk_dl.get("jobArea"),
            "location": sk_dl.get("jobLocation"),
            "classification": sk_dl.get("jobClassification"),
            "classification_id": sk_dl.get("jobClassificationId"),
            "subclassification": sk_dl.get("jobSubClassification"),
            "subclassification_id": sk_dl.get("jobSubClassificationId"),
            "description": description,
            "url": source_url,
        },
    }


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if "jobs" in data:
        total = data.get("total_count")
        print(f"SEEK.co.nz jobs: {data.get('returned_count')} shown" + (f" of {total}" if total is not None else ""))
        print(f"Source: {data.get('source_url')}")
        for job in data.get("jobs", []):
            bits = [job.get("company"), job.get("location"), job.get("work_type"), job.get("salary")]
            meta = " · ".join(str(x) for x in bits if x)
            print(f"- {job.get('title') or '(untitled)'} [{job.get('job_id') or '?'}]")
            if meta:
                print(f"  {meta}")
            if job.get("summary"):
                print(f"  {job['summary']}")
            if job.get("url"):
                print(f"  {job['url']}")
        return
    job = data.get("job") or {}
    print(f"{job.get('title') or 'SEEK job'} [{job.get('job_id') or '?'}]")
    for label, key in [("Company", "company"), ("Location", "location"), ("Area", "area"), ("Posted", "posted"), ("Status", "status"), ("Classification", "classification"), ("Subclassification", "subclassification")]:
        if job.get(key):
            print(f"{label}: {job[key]}")
    if job.get("description"):
        desc = job["description"]
        print("Description: " + (desc[:600] + ("…" if len(desc) > 600 else "")))
    print(f"Source: {data.get('source_url')}")


def cmd_search(args: argparse.Namespace) -> None:
    url = search_url(args.keywords, args.where, args.page)
    started = time.perf_counter()
    text, final_url = fetch_text(url)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    emit(parse_search_page(text, source_url=final_url, elapsed_ms=elapsed_ms, limit=args.limit), args.json)


def cmd_job(args: argparse.Namespace) -> None:
    job_id = re.sub(r"\D", "", args.job_id)
    if not job_id:
        die("job id must contain digits")
    url = f"{BASE}/job/{job_id}"
    started = time.perf_counter()
    text, final_url = fetch_text(url)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    emit(parse_detail_page(text, source_url=final_url, elapsed_ms=elapsed_ms), args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search and inspect public SEEK.co.nz job listings.")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search public SEEK.co.nz job listings")
    search.add_argument("keywords", help="role, skill, or keyword search, e.g. 'python developer'")
    search.add_argument("--where", default="All New Zealand", help="location text, e.g. Auckland, Wellington, Remote")
    search.add_argument("--page", type=int, default=1, help="result page number")
    search.add_argument("--limit", type=int, default=10, help="max jobs to print from the page")
    search.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    search.set_defaults(func=cmd_search)

    job = sub.add_parser("job", help="Fetch public detail for a SEEK job id")
    job.add_argument("job_id", help="numeric SEEK job id")
    job.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    job.set_defaults(func=cmd_job)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.limit = max(1, min(args.limit, 32)) if hasattr(args, "limit") else None
    args.page = max(1, args.page) if hasattr(args, "page") else None
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
