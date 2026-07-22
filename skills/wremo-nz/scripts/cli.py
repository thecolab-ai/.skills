#!/usr/bin/env python3
"""Read WREMO (Wellington Region Emergency Management Office) public news.

Parses the public wremo.nz news pages: listings with titles, dates, and
snippets, plus full article text. Read-only HTML access, no authentication.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE = "https://www.wremo.nz"
NEWS_PATH = "/news-and-events/wremo-news"
SOURCE_NAME = "WREMO news (wremo.nz)"
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
# Each news card starts with its title anchor; snippet and date are searched
# only within that card's segment (up to the next title) so a card missing a
# field can never steal the next card's date or snippet.
TITLE_LINK_RE = re.compile(r'card-title"><a href="(?P<href>/news-and-events/[^"]+)"[^>]*>(?P<title>.*?)</a></h2>', re.S)
SNIPPET_RE = re.compile(r'card-text[^>]*>(?P<snippet>.*?)</div>', re.S)
DATE_RE = re.compile(r'article-date">(?P<date>[^<]*)<')
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
BOILERPLATE_MARKERS = (
    "Toggle child menu",
    "Toggle site navigation",
    "Visit our Facebook page",
    "WREMO > News and Events",
)


def die(message: str, code: int = 1) -> None:
    print(f"wremo-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_page(path: str) -> tuple[str, str]:
    url = urllib.parse.urljoin(BASE, path)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.port is not None or parsed.hostname not in ("www.wremo.nz", "wremo.nz"):
        die(f"unsupported URL: only https wremo.nz pages are read ({url})", 7)
    try:
        text = nzfetch.fetch_text(url, timeout=30, accept="text/html,*/*", allowed_hosts=["www.wremo.nz", "wremo.nz"])
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        if "HTTP 404" in str(exc):
            die(f"no page at {url}; check the slug with the news command", 2)
        die(f"upstream unavailable: {exc}", 5)
    return text, url


def clean(text: str) -> str:
    return " ".join(html_module.unescape(TAG_RE.sub(" ", text)).split())


def parse_date(raw: str) -> str | None:
    """'6 Sept 2024' -> '2024-09-06'."""
    parts = raw.strip().split()
    if len(parts) != 3:
        return None
    day, month_name, year = parts
    month = MONTHS.get(month_name.rstrip(".").lower())
    if not month or not day.isdigit() or not year.isdigit() or not 1 <= int(day) <= 31:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def parse_news_listing(page: str) -> list[dict[str, Any]]:
    items = []
    titles = list(TITLE_LINK_RE.finditer(page))
    for index, match in enumerate(titles):
        segment_end = titles[index + 1].start() if index + 1 < len(titles) else len(page)
        segment = page[match.end():segment_end]
        snippet_match = SNIPPET_RE.search(segment)
        date_match = DATE_RE.search(segment)
        raw_date = date_match.group("date").strip() if date_match else ""
        items.append(
            {
                "title": clean(match.group("title")),
                "url": urllib.parse.urljoin(BASE, match.group("href")),
                "slug": match.group("href").rstrip("/").rsplit("/", 1)[-1],
                "snippet": clean(snippet_match.group("snippet")) if snippet_match else None,
                "date": parse_date(raw_date),
                "date_text": raw_date or None,
            }
        )
    return items


def parse_article(page: str) -> dict[str, Any]:
    title_match = TITLE_RE.search(page)
    title = clean(title_match.group(1)) if title_match else None
    if title:
        title = re.sub(r"\s*[|»].*$", "", title).strip() or None
    paragraphs = []
    page = SCRIPT_STYLE_RE.sub(" ", page)
    for raw in PARAGRAPH_RE.findall(page):
        text = clean(raw)
        # Drop short fragments and site-chrome blobs (nav, breadcrumbs, footer).
        if len(text) < 40 or any(marker in text for marker in BOILERPLATE_MARKERS):
            continue
        paragraphs.append(text)
    return {"title": title, "paragraphs": paragraphs}


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_news(args: argparse.Namespace) -> None:
    page, url = fetch_page(NEWS_PATH)
    items = parse_news_listing(page)
    if not items:
        die("source schema failure: no news cards found on the WREMO news page; the site markup may have changed", 6)
    if args.search:
        needle = args.search.casefold()
        items = [i for i in items if needle in i["title"].casefold() or needle in (i["snippet"] or "").casefold()]
    items.sort(key=lambda i: i["date"] or "", reverse=True)
    total = len(items)
    items = items[: args.limit]
    payload = {
        "kind": "news",
        "source": SOURCE_NAME,
        "source_url": url,
        "search": args.search,
        "total_matches": total,
        "note": "first listing page only; older items require the site's pagination",
        "items": items,
    }
    lines = [f"WREMO news: {len(items)} shown of {total}"]
    for item in items:
        lines.append(f"- {item['date'] or item['date_text'] or '(undated)'} {item['title']}")
        lines.append(f"    {item['url']}")
    emit(payload, args.json, lines)


def cmd_article(args: argparse.Namespace) -> None:
    reference = args.article
    if reference.startswith(("http://", "https://")):
        path = reference
    elif re.fullmatch(r"[a-z0-9][a-z0-9-]*", reference):
        path = f"{NEWS_PATH}/{reference}"
    else:
        die(f"invalid article reference {reference!r}: pass a slug from news output or a wremo.nz URL", 2)
    page, url = fetch_page(path)
    article = parse_article(page)
    if not article["paragraphs"]:
        die(f"no article text found at {url}; check the slug with the news command", 2)
    payload = {
        "kind": "article",
        "source": SOURCE_NAME,
        "source_url": url,
        "title": article["title"],
        "paragraph_count": len(article["paragraphs"]),
        "paragraphs": article["paragraphs"],
    }
    emit(payload, args.json, [article["title"] or url, ""] + article["paragraphs"])


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def main() -> None:
    parser = argparse.ArgumentParser(description="WREMO public news and updates (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("news", help="list WREMO news items, newest first")
    s.add_argument("--search", help="case-insensitive title/snippet filter")
    s.add_argument("--limit", type=positive_int(100), default=15, help="maximum items (default 15)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_news)

    s = sub.add_parser("article", help="full text of one news article")
    s.add_argument("article", help="article slug from news output, or a wremo.nz URL")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_article)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
