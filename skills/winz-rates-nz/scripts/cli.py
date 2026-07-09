#!/usr/bin/env python3
"""Work and Income NZ benefit rates and A-Z entitlement pages CLI.

This is a small stdlib-only reader for public Work and Income pages. It does
not use the partner-gated MSD API and performs no login or eligibility decision.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE = "https://www.workandincome.govt.nz"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146 Safari/537.36"
DEFAULT_TIMEOUT = 30


class UpstreamBlocked(RuntimeError):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"winz-rates-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def urljoin(path_or_url: str) -> str:
    return urllib.parse.urljoin(BASE, path_or_url)


def fetch(path_or_url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, int]:
    url = urljoin(path_or_url)
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            headers={"Accept-Language": "en-NZ,en;q=0.9"},
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        )
        return body.decode("utf-8", "replace"), final_url, 200
    except nzfetch.Blocked as e:
        raise UpstreamBlocked(f"HTTP block from Work and Income, likely bot/data-centre protection: {e}") from e
    except nzfetch.FetchError as e:
        die(f"{e}")
        raise


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", " | ", value, flags=re.I)
    value = re.sub(r"</(p|li|h[1-6]|tr|div)>", " | ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" |\t\r\n")


def slugify(text: str) -> str:
    text = html.unescape(text).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return re.sub(r"-+", "-", text)


def attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}=['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return html.unescape(m.group(1)) if m else None


def page_title(page_html: str) -> str | None:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    return strip_tags(m.group(1)) if m else None


def meta_description(page_html: str) -> str | None:
    m = re.search(r'<meta\s+[^>]*name=["\']description["\'][^>]*>', page_html, flags=re.I)
    if not m:
        m = re.search(r'<meta\s+[^>]*name=["\']DC\.Description["\'][^>]*>', page_html, flags=re.I)
    return attr(m.group(0), "content") if m else None


def parse_rows(table_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
        cells = [strip_tags(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.I | re.S)]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)
    return rows


def rows_to_dicts(rows: list[list[str]]) -> tuple[list[str], list[dict[str, str]]]:
    if not rows:
        return [], []
    headers = rows[0]
    # Some WINZ tables use an empty first column heading; keep a useful name.
    headers = [h if h else f"column_{i + 1}" for i, h in enumerate(headers)]
    data_rows = rows[1:]
    out: list[dict[str, str]] = []
    for row in data_rows:
        if len(row) != len(headers):
            keys = [f"column_{i + 1}" for i in range(len(row))]
        else:
            keys = headers
        out.append({keys[i]: row[i] for i in range(len(row))})
    return headers, out


def nearest_heading(block: str, table_start: int) -> str | None:
    before = block[:table_start]
    found = re.findall(r"<h([34])\b[^>]*>(.*?)</h\1>", before, flags=re.I | re.S)
    if not found:
        return None
    return strip_tags(found[-1][1]) or None


def parse_rate_section(title: str, body: str) -> dict[str, Any]:
    tables = []
    for index, m in enumerate(re.finditer(r"<table\b[^>]*>.*?</table>", body, flags=re.I | re.S), start=1):
        raw_rows = parse_rows(m.group(0))
        headers, rows = rows_to_dicts(raw_rows)
        if rows:
            tables.append({
                "index": index,
                "context": nearest_heading(body, m.start()),
                "headers": headers,
                "rows": rows,
            })
    notes = [strip_tags(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", body, flags=re.I | re.S)]
    notes = [n for n in notes if n and not n.startswith("Last updated")][:8]
    return {"slug": slugify(title), "title": title, "tables": tables, "notes": notes}


def parse_rates_page(page_html: str, year: int, source_url: str, status: int, elapsed_ms: int) -> dict[str, Any]:
    sections = []
    pattern = re.compile(
        r'<div\b[^>]*class=["\'][^"\']*wi-accordion--section[^"\']*["\'][^>]*>\s*'
        r'<h2\b[^>]*>.*?<span>(.*?)</span>.*?</h2>\s*'
        r'<div\b[^>]*class=["\'][^"\']*wi-accordion--content[^"\']*["\'][^>]*>(.*?)</div>\s*<!--\s*widget-content',
        flags=re.I | re.S,
    )
    for m in pattern.finditer(page_html):
        title = strip_tags(m.group(1))
        if title:
            sections.append(parse_rate_section(title, m.group(2)))
    if not sections:
        die("could not find benefit-rate sections in Work and Income HTML")
    return {
        "source_url": source_url,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "year": year,
        "title": page_title(page_html),
        "payments": sections,
    }


def get_rates(year: int) -> dict[str, Any]:
    started = time.perf_counter()
    body, final_url, status = fetch(f"/products/benefit-rates/benefit-rates-april-{year}.html")
    return parse_rates_page(body, year, final_url, status, round((time.perf_counter() - started) * 1000))


def parse_benefit_list(page_html: str, source_url: str, status: int, elapsed_ms: int) -> dict[str, Any]:
    benefits = []
    for m in re.finditer(r'<div\b[^>]*class=["\'][^"\']*links\s+default[^"\']*["\'][^>]*>\s*<a\s+([^>]+)>(.*?)</a>\s*<p[^>]*>(.*?)</p>', page_html, flags=re.I | re.S):
        href = attr(m.group(1), "href") or ""
        if not re.search(r"/products/a-z-benefits/[^/]+\.html$", href):
            continue
        title = strip_tags(m.group(2))
        benefits.append({
            "slug": href.rsplit("/", 1)[-1].removesuffix(".html"),
            "title": title,
            "summary": strip_tags(m.group(3)),
            "url": urljoin(href),
        })
    return {
        "source_url": source_url,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "title": page_title(page_html),
        "benefits": benefits,
    }


def get_benefit_list() -> dict[str, Any]:
    started = time.perf_counter()
    body, final_url, status = fetch("/products/a-z-benefits/")
    return parse_benefit_list(body, final_url, status, round((time.perf_counter() - started) * 1000))


def main_content(page_html: str) -> str:
    m = re.search(r"<main\b[^>]*>(.*?)</main>", page_html, flags=re.I | re.S)
    return m.group(1) if m else page_html


def parse_sections(content: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"<h2\b[^>]*>(.*?)</h2>", content, flags=re.I | re.S))
    sections = []
    for i, m in enumerate(matches):
        title = strip_tags(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end]
        text = strip_tags(block)
        if title and text:
            sections.append({"title": title, "slug": slugify(title), "text": text[:4000]})
    return sections


def parse_links(content: str) -> list[dict[str, str]]:
    links = []
    seen = set()
    for m in re.finditer(r"<a\s+([^>]+)>(.*?)</a>", content, flags=re.I | re.S):
        href = attr(m.group(1), "href")
        label = strip_tags(m.group(2))
        if not href or not label or href.startswith("#"):
            continue
        absolute = urljoin(href)
        key = (label, absolute)
        if key not in seen:
            seen.add(key)
            links.append({"text": label, "url": absolute})
    return links[:40]


def get_benefit(slug: str) -> dict[str, Any]:
    slug = slug.removesuffix(".html").strip("/")
    started = time.perf_counter()
    body, final_url, status = fetch(f"/products/a-z-benefits/{urllib.parse.quote(slug)}.html")
    content = main_content(body)
    sections = parse_sections(content)
    eligibility = [s for s in sections if re.search(r"(who can get|can get|qualify|eligible|criteria)", s["title"], flags=re.I)]
    overview = ""
    h1 = re.search(r"</h1>(.*?)(?:<h2\b|<div\b[^>]*class=[\"'][^\"']*block|</main>)", content, flags=re.I | re.S)
    if h1:
        overview = strip_tags(h1.group(1))[:2000]
    return {
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "slug": slug,
        "title": page_title(body),
        "description": meta_description(body),
        "overview": overview,
        "eligibility_sections": eligibility,
        "sections": sections,
        "links": parse_links(content),
    }


def emit(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if isinstance(data, dict) and "payments" in data:
        print(f"{data.get('title') or 'Benefit rates'}: {len(data['payments'])} payment/rate sections")
        print(data["source_url"])
        for p in data["payments"]:
            print(f"- {p['slug']}: {p['title']} ({len(p['tables'])} tables)")
    elif isinstance(data, dict) and "benefits" in data:
        print(f"{data.get('title') or 'A-Z benefits'}: {len(data['benefits'])} A-Z benefit pages")
        print(data["source_url"])
        for b in data["benefits"]:
            print(f"- {b['slug']}: {b['title']} — {b['summary']}")
    elif isinstance(data, dict) and "tables" in data:
        print(f"{data['title']} ({data['slug']})")
        for table in data["tables"]:
            ctx = f" — {table['context']}" if table.get("context") else ""
            print(f"Table {table['index']}{ctx}: {len(table['rows'])} rows")
            for row in table["rows"][:8]:
                print("  " + "; ".join(f"{k}: {v}" for k, v in row.items()))
    elif isinstance(data, dict) and "sections" in data:
        print(data.get("title") or data.get("slug"))
        print(data.get("source_url"))
        if data.get("description"):
            print(data["description"])
        for section in data.get("eligibility_sections") or data.get("sections", [])[:4]:
            print(f"\n## {section['title']}\n{section['text'][:800]}")
    else:
        print(data)


def cmd_rates(args: argparse.Namespace) -> None:
    try:
        data = get_rates(args.year)
    except UpstreamBlocked as e:
        die(str(e), 2)
    if args.rates_command == "get":
        wanted = args.payment_slug
        payment = next((p for p in data["payments"] if p["slug"] == wanted), None)
        if not payment:
            matches = [p["slug"] for p in data["payments"] if wanted in p["slug"]]
            hint = f"; close matches: {', '.join(matches[:8])}" if matches else ""
            die(f"payment slug not found: {wanted}{hint}")
        payment = {**payment, "year": data["year"], "source_url": data["source_url"], "elapsed_ms": data["elapsed_ms"]}
        emit(payment, args.json)
    else:
        emit(data, args.json)


def cmd_benefits(args: argparse.Namespace) -> None:
    try:
        if args.benefits_command == "get":
            data = get_benefit(args.slug)
        else:
            data = get_benefit_list()
    except UpstreamBlocked as e:
        die(str(e), 2)
    emit(data, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query public Work and Income NZ benefit rates and A-Z benefit pages")
    sub = parser.add_subparsers(dest="command", required=True)

    rates = sub.add_parser("rates", help="List or inspect annual Work and Income benefit-rate tables")
    rates.add_argument("--year", type=int, default=2026, help="April rates page year, e.g. 2026")
    rates.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    rates_sub = rates.add_subparsers(dest="rates_command")
    rates_get = rates_sub.add_parser("get", help="Inspect one payment/rate section by slug")
    rates_get.add_argument("payment_slug", help="Section slug, e.g. jobseeker-support")
    rates_get.add_argument("--year", type=int, default=2026, help="April rates page year, e.g. 2026")
    rates_get.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    rates.set_defaults(func=cmd_rates)

    benefits = sub.add_parser("benefits", help="List or inspect Work and Income A-Z benefit entitlement pages")
    benefits.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    benefits_sub = benefits.add_subparsers(dest="benefits_command")
    benefits_list = benefits_sub.add_parser("list", help="List A-Z benefit pages")
    benefits_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    benefits_list.set_defaults(benefits_command="list")
    benefits_get = benefits_sub.add_parser("get", help="Inspect one A-Z benefit page by slug")
    benefits_get.add_argument("slug", help="Benefit page slug, e.g. accommodation-supplement")
    benefits_get.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    benefits.set_defaults(func=cmd_benefits, benefits_command="list")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
