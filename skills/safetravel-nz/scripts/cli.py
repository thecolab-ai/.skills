#!/usr/bin/env python3
"""Read-only SafeTravel NZ destination-advice lookup CLI."""
from __future__ import annotations

import argparse
import html
import importlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
nzfetch = importlib.import_module("nzfetch")

SKILL = "safetravel-nz"
SOURCE_NAME = "MFAT SafeTravel"
SOURCE_OWNER = "Ministry of Foreign Affairs and Trade (MFAT)"
BASE_URL = "https://www.safetravel.govt.nz/"
SITEMAP_URL = urljoin(BASE_URL, "sitemap.xml")
DESTINATION_PREFIX = urljoin(BASE_URL, "destinations/")
ALLOWED_HOSTS = ("www.safetravel.govt.nz",)
TIMEOUT_SECONDS = 10
CHANGE_WARNING = "Travel advice can change. Consult the official SafeTravel page before travelling or making safety-critical decisions."
ADVICE_LEVEL_NUMBERS = {
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "avoid": 4,
    "extreme": 4,
}


class SkillError(Exception):
    """A clean expected CLI error with a documented exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


class SchemaError(SkillError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 6)


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


class VisibleTextParser(HTMLParser):
    """Extract visible text from an HTML fragment without a third-party parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and clean_text(data):
            self.parts.append(clean_text(data))


def html_to_text(value: str) -> str:
    parser = VisibleTextParser()
    parser.feed(value)
    parser.close()
    return clean_text(" ".join(parser.parts))


class DestinationPageParser(HTMLParser):
    """Capture the supported SafeTravel page surfaces with deterministic stdlib parsing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.visible_parts: list[str] = []
        self.h1_depth = 0
        self.h1_parts: list[str] = []
        self.description: str | None = None
        self.data_content: dict[str, str] = {}
        self.anchor_stack: list[dict[str, Any]] = []
        self.news_links: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.description = clean_text(attrs_dict.get("content", "")) or None
        element_id = attrs_dict.get("id", "")
        if element_id in {"js-advice-level-accordion", "js-accordion"} and "data-content" in attrs_dict:
            self.data_content[element_id] = attrs_dict["data-content"]
        if tag == "h1":
            self.h1_depth += 1
        if tag == "a":
            href = attrs_dict.get("href", "")
            if href.startswith("/news/"):
                self.anchor_stack.append(
                    {
                        "href": href,
                        "aria": clean_text(attrs_dict.get("aria-label", "")),
                        "parts": [],
                        "heading_parts": [],
                        "heading_depth": 0,
                    }
                )
        elif self.anchor_stack and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.anchor_stack[-1]["heading_depth"] += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "h1" and self.h1_depth:
            self.h1_depth -= 1
        if tag == "a" and self.anchor_stack:
            self.news_links.append(self.anchor_stack.pop())
        elif self.anchor_stack and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            active = self.anchor_stack[-1]
            if active["heading_depth"]:
                active["heading_depth"] -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = clean_text(data)
        if not text:
            return
        self.visible_parts.append(text)
        if self.h1_depth:
            self.h1_parts.append(text)
        if self.anchor_stack:
            active = self.anchor_stack[-1]
            active["parts"].append(text)
            if active["heading_depth"]:
                active["heading_parts"].append(text)


def parse_sitemap(source: str) -> list[dict[str, str | None]]:
    """Return destination pages from the official sitemap, sorted by display name."""
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise SchemaError(f"official sitemap XML could not be parsed: {exc}") from exc

    destinations: list[dict[str, str | None]] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "url":
            continue
        fields = {
            child.tag.rsplit("}", 1)[-1]: clean_text(child.text or "")
            for child in node
        }
        url = fields.get("loc", "")
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() not in ALLOWED_HOSTS
            or len(parts) != 2
            or parts[0] != "destinations"
            or parts[1] == "about-our-travel-advice"
            or not re.fullmatch(r"[a-z0-9-]+", parts[1])
        ):
            continue
        slug = parts[1]
        destinations.append(
            {
                "name": slug.replace("-", " ").title(),
                "slug": slug,
                "url": url,
                "sitemap_last_modified": fields.get("lastmod") or None,
            }
        )
    if not destinations:
        raise SchemaError("official sitemap contained no destination pages")
    return sorted(destinations, key=lambda item: (str(item["name"]).casefold(), str(item["slug"])))


def normalise_destination(value: str) -> str:
    """Accept a destination slug, friendly name, or canonical SafeTravel URL."""
    candidate = value.strip()
    if not candidate:
        raise SkillError("destination must not be empty", 2)
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() not in ALLOWED_HOSTS
            or parsed.query
            or parsed.fragment
        ):
            raise SkillError("destination URL must be a canonical www.safetravel.govt.nz destination URL", 2)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2 or parts[0] != "destinations":
            raise SkillError("destination URL must have the form /destinations/<slug>", 2)
        candidate = parts[1]
    candidate = re.sub(r"\s+", "-", candidate.strip().casefold())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate):
        raise SkillError("destination must be a SafeTravel destination name or hyphenated slug", 2)
    return candidate


def parse_advice_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SchemaError("advice-level data included a non-object item")
    title = clean_text(str(item.get("title", "")))
    body = html_to_text(str(item.get("body", "")))
    raw_level = clean_text(str(item.get("level", ""))).casefold()
    level_number_match = re.search(r"\blevel\s+([1-4])\s+of\s+4\b", body, re.IGNORECASE)
    if not title or not body or not raw_level:
        raise SchemaError("advice-level data is missing a title, level, or advice body")
    expected_level_number = ADVICE_LEVEL_NUMBERS.get(raw_level)
    if expected_level_number is None:
        raise SchemaError(f"advice-level data used an unsupported level value: {raw_level!r}")
    if level_number_match is None:
        raise SchemaError(f"advice body did not contain a recognised level marker for {title!r}")
    level_number = int(level_number_match.group(1))
    if level_number != expected_level_number:
        raise SchemaError(
            f"advice-level data disagreed: {title!r} had level {raw_level!r} but body level {level_number}"
        )
    return {
        "title": title,
        "subtitle": clean_text(str(item.get("subtitle", ""))),
        "level": raw_level,
        "number": level_number,
        "last_updated": clean_text(str(item.get("lastUpdated", ""))) or None,
        "still_current_at": clean_text(str(item.get("stillCurrentAt", ""))) or None,
        "body": body,
    }


def parse_related_news(parser: DestinationPageParser, page_url: str) -> list[dict[str, str | None]]:
    results: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()
    for anchor in parser.news_links:
        url = urljoin(page_url, str(anchor["href"]))
        if url in seen_urls:
            continue
        text = clean_text(" ".join(anchor["parts"]))
        headings = clean_text(" ".join(anchor["heading_parts"]))
        title = headings or str(anchor["aria"]) or text
        title = re.sub(r"\bUpdated\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", "", title, flags=re.IGNORECASE)
        title = clean_text(title).replace("read article", "").strip()
        updated_match = re.search(r"\bUpdated\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text, re.IGNORECASE)
        summary = text
        if updated_match:
            summary = summary.replace(updated_match.group(0), "")
        if title:
            summary = summary.replace(title, "", 1)
        summary = clean_text(re.sub(r"\bread article\b", "", summary, flags=re.IGNORECASE)) or None
        if not title:
            continue
        # Footer registration material uses a /news/ instructional URL but is not
        # destination-related news; this skill intentionally excludes registration workflows.
        if title.casefold() == "register your travel" or "registering-on-safetravel" in url.casefold():
            continue
        seen_urls.add(url)
        results.append(
            {
                "title": title,
                "updated": updated_match.group(1) if updated_match else None,
                "url": url,
                "summary": summary,
            }
        )
    return results[:10]


def parse_destination_page(source: str, *, slug: str, url: str) -> dict[str, Any]:
    parser = DestinationPageParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:  # HTMLParser is permissive, but retain a clean parser failure.
        raise SchemaError(f"destination page HTML could not be parsed: {exc}") from exc
    raw_advice = parser.data_content.get("js-advice-level-accordion")
    if not raw_advice:
        raise SchemaError("destination page did not contain SafeTravel advice-level data")
    try:
        raw_items = json.loads(html.unescape(raw_advice))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"destination advice-level data was not valid JSON: {exc}") from exc
    if not isinstance(raw_items, list) or not raw_items:
        raise SchemaError("destination advice-level data was empty")
    advice_items = [parse_advice_item(item) for item in raw_items]
    primary_items = [item for index, item in enumerate(advice_items) if not bool(raw_items[index].get("regional"))]
    if len(primary_items) != 1:
        raise SchemaError("destination advice-level data must contain exactly one non-regional primary item")
    primary = primary_items[0]
    regional = [
        item for index, item in enumerate(advice_items) if bool(raw_items[index].get("regional"))
    ]
    page_text = clean_text(" ".join(parser.visible_parts))
    page_updated_match = re.search(r"\bPage updated\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", page_text, re.IGNORECASE)
    name = clean_text(" ".join(parser.h1_parts)) or slug.replace("-", " ").title()
    return {
        "destination": {
            "name": name,
            "slug": slug,
            "url": url,
            "page_updated": page_updated_match.group(1) if page_updated_match else None,
            "summary": parser.description,
        },
        "advice_level": primary,
        "regional_cautions": regional,
        "related_alerts_news": parse_related_news(parser, url),
    }


def fetch_text(url: str, *, accept: str) -> tuple[str, str]:
    """Fetch one official source page under the skill's bounded allowlist."""
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            accept=accept,
            allowed_hosts=ALLOWED_HOSTS,
        )
    except nzfetch.RateLimited as exc:
        raise SkillError(f"source blocked or rate-limited: {exc}", 4) from exc
    except nzfetch.Blocked as exc:
        raise SkillError(f"source blocked: {exc}", 4) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(f"network error: upstream unavailable: {exc}", 5) from exc
    try:
        return body.decode("utf-8"), final_url
    except UnicodeDecodeError as exc:
        raise SchemaError(f"official source returned non-UTF-8 content: {exc}") from exc


def source_metadata(url: str, retrieved_at: str, *, page_updated: str | None = None) -> dict[str, str | None]:
    return {
        "name": SOURCE_NAME,
        "owner": SOURCE_OWNER,
        "url": url,
        "retrieved_at": retrieved_at,
        "page_updated": page_updated,
    }


def result_envelope(*, source: dict[str, str | None], query: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "ok": True,
        "source": source,
        "query": query,
        "data": data,
        "warnings": [CHANGE_WARNING],
        "blocked": False,
    }


def get_destinations() -> tuple[list[dict[str, str | None]], str, str]:
    retrieved_at = utc_now()
    text, final_url = fetch_text(SITEMAP_URL, accept="application/xml,text/xml;q=0.9,*/*;q=0.8")
    return parse_sitemap(text), final_url, retrieved_at


def cmd_search(args: argparse.Namespace) -> dict[str, Any]:
    query = clean_text(args.query)
    if not query:
        raise SkillError("search query must not be empty", 2)
    destinations, sitemap_url, retrieved_at = get_destinations()
    terms = query.casefold().split()
    matches = [
        item
        for item in destinations
        if all(term in f"{item['name']} {item['slug']}".casefold() for term in terms)
    ][: args.limit]
    return result_envelope(
        source=source_metadata(sitemap_url, retrieved_at),
        query={"command": "search", "text": query, "limit": args.limit},
        data={
            "kind": "destination_search",
            "count": len(matches),
            "destinations": matches,
            "sitemap_url": sitemap_url,
        },
    )


def cmd_advice(args: argparse.Namespace) -> dict[str, Any]:
    slug = normalise_destination(args.destination)
    destinations, sitemap_url, sitemap_retrieved_at = get_destinations()
    destination = next((item for item in destinations if item["slug"] == slug), None)
    if destination is None:
        raise SkillError(f"destination '{slug}' was not found in the official SafeTravel sitemap; use search first", 2)
    page_url = str(destination["url"])
    retrieved_at = utc_now()
    source, final_url = fetch_text(page_url, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
    data = parse_destination_page(source, slug=slug, url=final_url)
    return result_envelope(
        source=source_metadata(final_url, retrieved_at, page_updated=data["destination"]["page_updated"]),
        query={"command": "advice", "destination": slug, "sitemap_url": sitemap_url, "sitemap_retrieved_at": sitemap_retrieved_at},
        data={"kind": "destination_advice", **data},
    )


def positive_limit(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("limit must be between 1 and 100")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read official MFAT SafeTravel NZ destination advice (read-only)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search official SafeTravel destination pages")
    search.add_argument("query", help="destination name or words")
    search.add_argument("--limit", type=positive_limit, default=20, help="maximum matches, 1-100 (default: 20)")
    search.add_argument("--json", action="store_true", help="emit the result envelope as JSON")
    search.set_defaults(handler=cmd_search)

    advice = subparsers.add_parser("advice", help="fetch current advice for one official destination")
    advice.add_argument("destination", help="destination name, slug, or canonical SafeTravel destination URL")
    advice.add_argument("--json", action="store_true", help="emit the result envelope as JSON")
    advice.set_defaults(handler=cmd_advice)
    return parser


def print_human(result: dict[str, Any]) -> None:
    data = result["data"]
    source = result["source"]
    if data["kind"] == "destination_search":
        query = result["query"]["text"]
        print(f"SafeTravel destinations matching {query!r}: {data['count']}")
        for item in data["destinations"]:
            print(f"- {item['name']} ({item['slug']}): {item['url']}")
        if not data["destinations"]:
            print("No official destination pages matched. Try fewer or different words.")
        print(f"Sitemap retrieved: {source['retrieved_at']} — {source['url']}")
    else:
        destination = data["destination"]
        level = data["advice_level"]
        print(destination["name"])
        print(f"Advice level {level['number']} of 4 ({level['level']}): {level['title']}")
        print(level["body"])
        if destination.get("page_updated"):
            print(f"Page updated: {destination['page_updated']}")
        if data["regional_cautions"]:
            print("Regional cautions:")
            for item in data["regional_cautions"]:
                print(f"- Level {item['number']} ({item['level']}): {item['title']} {item['subtitle']}")
        if data["related_alerts_news"]:
            print("Related alerts/news:")
            for item in data["related_alerts_news"]:
                date = f" — updated {item['updated']}" if item.get("updated") else ""
                print(f"- {item['title']}{date}: {item['url']}")
        print(f"Source retrieved: {source['retrieved_at']} — {source['url']}")
    print(f"Warning: {CHANGE_WARNING}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except SkillError as exc:
        print(f"{SKILL}: {exc}", file=sys.stderr)
        return exc.code
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
