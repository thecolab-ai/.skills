#!/usr/bin/env python3
"""Read-only SafeTravel NZ destination-advice lookup CLI."""

from __future__ import annotations

import argparse
import html
import importlib
import json
import math
import posixpath
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

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
MAX_JSON_DEPTH = 100
SITEMAP_NAMESPACE_SCHEME = "http"
SITEMAP_NAMESPACE_LOCATION = "www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_FIELD_NAMES = frozenset(("loc", "lastmod", "changefreq", "priority"))
VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
TIMEOUT_SECONDS = 10
CHANGE_WARNING = (
    "Travel advice can change. Consult the official SafeTravel page before "
    "travelling or making safety-critical decisions."
)
ADVICE_LEVEL_NUMBERS = {
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "avoid": 4,
    "extreme": 4,
}
ADVICE_LEVEL_TITLES = {
    1: "exercise normal safety and security precautions",
    2: "exercise increased caution",
    3: "avoid non-essential travel",
    4: "do not travel",
}


class SkillError(Exception):
    """A clean expected CLI error with a documented exit code."""

    error_name: str | None = None

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code

    def _default_error_name(self) -> str:
        return {
            2: "invalid_input",
            4: "blocked",
            5: "upstream_unavailable",
            6: "source_schema_failure",
            7: "unsupported_operation",
        }.get(self.code, "error")

    def error_payload(self) -> dict[str, Any]:
        return {
            "error": self.error_name or self._default_error_name(),
            "message": str(self),
        }


class RateLimitedError(SkillError):
    error_name = "rate_limited"

    def __init__(self, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message, 4)
        self.retry_after = retry_after

    def error_payload(self) -> dict[str, Any]:
        payload = super().error_payload()
        payload["retry_after"] = self.retry_after
        return payload


class BlockedError(SkillError):
    error_name = "blocked"

    def __init__(self, message: str) -> None:
        super().__init__(message, 4)


class SchemaError(SkillError):
    error_name = "source_schema_failure"

    def __init__(self, message: str) -> None:
        super().__init__(message, 6)


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


class VisibleTextParser(HTMLParser):
    """Validate and extract visible text from a safety-critical HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._element_stack: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in VOID_HTML_TAGS:
            self._element_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        if tag not in VOID_HTML_TAGS:
            raise SchemaError(
                "advice body HTML fragment used self-closing syntax for "
                f"non-void {tag} element"
            )
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_HTML_TAGS:
            return
        if not self._element_stack or self._element_stack[-1] != tag:
            raise SchemaError(
                "advice body HTML fragment had an unmatched or misnested "
                f"{tag} closing element"
            )
        self._element_stack.pop()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and clean_text(data):
            self.parts.append(clean_text(data))

    def validate_complete_fragment(self) -> None:
        if self._element_stack or self._skip_depth:
            raise SchemaError(
                "advice body HTML fragment contained unclosed structural elements"
            )


def html_to_text(value: str) -> str:
    parser = VisibleTextParser()
    parser.feed(value)
    parser.close()
    parser.validate_complete_fragment()
    return clean_text(" ".join(parser.parts))


def destination_identity_key(value: str) -> str:
    """Normalise legitimate display punctuation without accepting another place."""
    value = unicodedata.normalize("NFKD", clean_text(value).casefold())
    value = value.replace("&", " and ")
    return "".join(
        character
        for character in value
        if character.isascii() and character.isalnum()
    )


class DestinationPageParser(HTMLParser):
    (
        "Capture the supported SafeTravel page surfaces with deterministic "
        "stdlib parsing."
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.visible_parts: list[str] = []
        self.h1_depth = 0
        self.h1_parts: list[str] = []
        self.description: str | None = None
        self.data_content: dict[str, str] = {}
        self._advice_container_ids_seen: set[str] = set()
        self.anchor_stack: list[dict[str, Any]] = []
        self.news_links: list[dict[str, Any]] = []
        self._related_news_section_depth: int | None = None
        self._related_news_section_seen = False
        self._element_stack: list[str] = []
        self._document_stack: list[str] = []
        self._document_tags_seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attribute_names: set[str] = set()
        for key, _value in attrs:
            normalised_key = key.casefold()
            if normalised_key in attribute_names:
                raise SchemaError(
                    "destination page HTML had a duplicate HTML attribute name: "
                    f"{normalised_key}"
                )
            attribute_names.add(normalised_key)
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag not in VOID_HTML_TAGS:
            self._element_stack.append(tag)
        if tag in {"html", "head", "body"}:
            if tag in self._document_tags_seen:
                raise SchemaError(f"destination page HTML repeated its {tag} element")
            expected_parent = {"html": None, "head": "html", "body": "html"}[tag]
            actual_parent = self._document_stack[-1] if self._document_stack else None
            if actual_parent != expected_parent:
                raise SchemaError(
                    f"destination page HTML had an invalid {tag} element structure"
                )
            self._document_tags_seen.add(tag)
            self._document_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.description = clean_text(attrs_dict.get("content", "")) or None
        element_id = attrs_dict.get("id", "")
        if element_id in {"js-advice-level-accordion", "js-accordion"}:
            if element_id in self._advice_container_ids_seen:
                raise SchemaError(
                    "destination page HTML had a duplicate advice container: "
                    f"{element_id}"
                )
            self._advice_container_ids_seen.add(element_id)
            if "data-content" in attrs_dict:
                self.data_content[element_id] = attrs_dict["data-content"]
        if tag == "section" and element_id == "relatedNews":
            if self._related_news_section_seen:
                raise SchemaError(
                    "destination page HTML had duplicate Related News surfaces"
                )
            self._related_news_section_seen = True
            self._related_news_section_depth = len(self._element_stack)
        if tag == "h1":
            self.h1_depth += 1
        if tag == "a" and self._related_news_section_depth is not None:
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
        if tag in VOID_HTML_TAGS:
            return
        if not self._element_stack or self._element_stack[-1] != tag:
            raise SchemaError(
                f"destination page HTML had an unmatched or misnested {tag} "
                "closing element"
            )
        closed_related_news = (
            tag == "section"
            and self._related_news_section_depth == len(self._element_stack)
        )
        self._element_stack.pop()
        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"html", "head", "body"}:
            if not self._document_stack or self._document_stack[-1] != tag:
                raise SchemaError(
                    f"destination page HTML had an unmatched {tag} closing element"
                )
            self._document_stack.pop()
        if tag == "h1" and self.h1_depth:
            self.h1_depth -= 1
        if tag == "a" and self.anchor_stack:
            self.news_links.append(self.anchor_stack.pop())
        elif self.anchor_stack and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            active = self.anchor_stack[-1]
            if active["heading_depth"]:
                active["heading_depth"] -= 1
        if closed_related_news:
            self._related_news_section_depth = None

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

    def validate_complete_document(self) -> None:
        if self._document_tags_seen != {"html", "head", "body"}:
            raise SchemaError(
                "destination page HTML was missing html/head/body structure"
            )
        if (
            self._element_stack
            or self._document_stack
            or self.h1_depth
            or self.anchor_stack
            or self._skip_depth
        ):
            raise SchemaError(
                "destination page HTML contained unclosed structural elements"
            )


def is_unsupported_canonical_destination_slug(slug: str) -> bool:
    """Recognise canonical punctuation slugs that this strict CLI cannot accept."""
    if not re.fullmatch(r"(?:[a-z0-9,-]|%[0-9A-Fa-f]{2})+", slug):
        return False
    try:
        decoded = unquote(slug, errors="strict")
    except UnicodeDecodeError:
        return False
    return (
        decoded == decoded.casefold()
        and re.fullmatch(r"[a-z0-9]+(?:(?:-|['’]|,-)[a-z0-9]+)*", decoded)
        is not None
        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", decoded) is None
    )


def parse_sitemap(source: str) -> list[dict[str, str | None]]:
    """Return destination pages from the official sitemap, sorted by display name."""
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise SchemaError(f"official sitemap XML could not be parsed: {exc}") from exc

    root_namespace, namespace_end, root_name = (
        root.tag[1:].partition("}") if root.tag.startswith("{") else ("", "", "")
    )
    namespace_scheme, scheme_end, namespace_location = root_namespace.partition(
        "://"
    )
    if (
        namespace_end != "}"
        or root_name != "urlset"
        or namespace_scheme != SITEMAP_NAMESPACE_SCHEME
        or scheme_end != "://"
        or namespace_location != SITEMAP_NAMESPACE_LOCATION
        or root.attrib
    ):
        raise SchemaError("official sitemap had an invalid urlset root")
    if root.text and root.text.strip():
        raise SchemaError(
            "official sitemap contained unexpected text outside a url entry"
        )

    destinations: list[dict[str, str | None]] = []
    seen_slugs: set[str] = set()
    namespace_prefix = f"{{{root_namespace}}}"
    for node in root:
        if node.tag != f"{namespace_prefix}url" or node.attrib:
            raise SchemaError("official sitemap contained an invalid url entry")
        if (node.text and node.text.strip()) or (node.tail and node.tail.strip()):
            raise SchemaError("official sitemap url entry contained unexpected text")

        fields: dict[str, str] = {}
        for child in node:
            if not child.tag.startswith(namespace_prefix):
                raise SchemaError(
                    "official sitemap url entry contained an unexpected field"
                )
            field_name = child.tag.removeprefix(namespace_prefix)
            if field_name not in SITEMAP_FIELD_NAMES:
                raise SchemaError(
                    "official sitemap url entry contained an unexpected field"
                )
            if field_name in fields:
                raise SchemaError(
                    "official sitemap url entry contained duplicate field "
                    f"{field_name!r}"
                )
            if child.attrib:
                raise SchemaError(
                    f"official sitemap field {field_name!r} had unexpected attributes"
                )
            if len(child):
                raise SchemaError(
                    f"official sitemap field {field_name!r} contained nested content"
                )
            if child.tail and child.tail.strip():
                raise SchemaError(
                    "official sitemap url entry contained unexpected text"
                )
            fields[field_name] = clean_text(child.text or "")

        if "loc" not in fields or not fields["loc"]:
            raise SchemaError(
                "official sitemap url entry must contain exactly one loc field"
            )
        url = fields["loc"]
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        destination_shaped = parsed.path.startswith("/destinations/")
        if (
            len(parts) != 2
            or parts[0] != "destinations"
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", parts[1])
        ):
            if destination_shaped and not (
                len(parts) == 2
                and parts[0] == "destinations"
                and url == f"{DESTINATION_PREFIX}{parts[1]}"
                and is_unsupported_canonical_destination_slug(parts[1])
            ):
                raise SchemaError(
                    "official sitemap contained a malformed destination URL: "
                    f"{url!r}"
                )
            continue
        slug = parts[1]
        if slug == "about-our-travel-advice":
            continue
        canonical_url = f"{DESTINATION_PREFIX}{slug}"
        if url != canonical_url:
            raise SchemaError(
                f"official sitemap contained a non-canonical destination URL: {url!r}"
            )
        if slug in seen_slugs:
            raise SchemaError(
                f"official sitemap contained a duplicate destination slug: {slug!r}"
            )
        seen_slugs.add(slug)
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
    return sorted(
        destinations, key=lambda item: (str(item["name"]).casefold(), str(item["slug"]))
    )


def canonical_destination_slug(url: str) -> str | None:
    """Return the slug only for an exact literal canonical destination URL."""
    match = re.fullmatch(
        re.escape(DESTINATION_PREFIX) + r"([a-z0-9]+(?:-[a-z0-9]+)*)", url
    )
    return match.group(1) if match else None


def normalise_destination(value: str) -> str:
    """Accept a destination slug, friendly name, or canonical SafeTravel URL."""
    candidate = value.strip()
    if not candidate:
        raise SkillError("destination must not be empty", 2)
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        slug = canonical_destination_slug(candidate)
        if slug is None or candidate != f"{DESTINATION_PREFIX}{slug}":
            raise SkillError(
                "destination URL must be a canonical www.safetravel.govt.nz "
                "destination URL",
                2,
            )
        candidate = slug
    candidate = re.sub(r"\s+", "-", candidate.strip().casefold())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate):
        raise SkillError(
            "destination must be a SafeTravel destination name or hyphenated slug", 2
        )
    return candidate


def advice_string_field(item: dict[str, Any], field: str) -> str:
    if field not in item:
        return ""
    value = item[field]
    if not isinstance(value, str):
        raise SchemaError(f"advice-level data had an invalid {field} field")
    return value


def parse_advice_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SchemaError("advice-level data included a non-object item")
    title = clean_text(advice_string_field(item, "title"))
    body = html_to_text(advice_string_field(item, "body"))
    raw_level = clean_text(advice_string_field(item, "level")).casefold()
    body_level_numbers = [
        int(value)
        for value in re.findall(r"\blevel\s+(\d+)\s+of\s+4\b", body, re.IGNORECASE)
    ]
    if not title or not body or not raw_level:
        raise SchemaError("advice-level data is missing a title, level, or advice body")
    expected_level_number = ADVICE_LEVEL_NUMBERS.get(raw_level)
    if expected_level_number is None:
        raise SchemaError(
            f"advice-level data used an unsupported level value: {raw_level!r}"
        )
    if not body_level_numbers:
        raise SchemaError(
            f"advice body did not contain a recognised level marker for {title!r}"
        )
    if any(number != expected_level_number for number in body_level_numbers):
        raise SchemaError(
            f"advice-level data disagreed: {title!r} had level {raw_level!r} "
            "but its body contained conflicting level markers "
            f"{sorted(set(body_level_numbers))!r}"
        )
    expected_title = ADVICE_LEVEL_TITLES[expected_level_number]
    normalised_title = title.casefold().removesuffix(".")
    if normalised_title != expected_title:
        raise SchemaError(
            f"advice-level title disagreed: {title!r} did not match "
            f"level {expected_level_number} of 4"
        )
    level_number = expected_level_number
    return {
        "title": title,
        "subtitle": clean_text(advice_string_field(item, "subtitle")),
        "level": raw_level,
        "number": level_number,
        "last_updated": clean_text(advice_string_field(item, "lastUpdated")) or None,
        "still_current_at": clean_text(advice_string_field(item, "stillCurrentAt"))
        or None,
        "body": body,
    }


def required_regional_classification(item: Any) -> bool:
    if not isinstance(item, dict) or "regional" not in item:
        raise SchemaError("advice-level data is missing a regional classification")
    regional = item["regional"]
    if not isinstance(regional, bool):
        raise SchemaError("advice-level data has an invalid regional classification")
    return regional


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def reject_duplicate_json_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object member: {key}")
        result[key] = value
    return result


def parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number is not finite: {value}")
    return parsed


def ensure_bounded_json_depth(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise SchemaError(
                "destination advice-level JSON exceeded the supported nesting depth"
            )
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def is_canonical_news_path(path: str) -> bool:
    if "%" in path or "\\" in path:
        return False
    if any(segment in {".", ".."} for segment in path.split("/")):
        return False
    normalised = posixpath.normpath(path)
    return (
        normalised == path
        and normalised != "/news"
        and normalised.startswith("/news/")
    )


def canonical_related_news_url(page_url: str, href: str) -> str:
    if (
        not href
        or not href.isascii()
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in href)
    ):
        raise SchemaError(
            f"destination page contained a non-canonical related-news URL: {href!r}"
        )
    url = urljoin(page_url, href)
    parsed = urlparse(url)
    href_path = urlparse(href).path
    canonical_url = f"{BASE_URL.rstrip('/')}{parsed.path}"
    if (
        parsed.scheme != "https"
        or parsed.netloc not in ALLOWED_HOSTS
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not is_canonical_news_path(href_path)
        or not is_canonical_news_path(parsed.path)
        or url != canonical_url
    ):
        raise SchemaError(
            f"destination page contained a non-canonical related-news URL: {url!r}"
        )
    return url


def parse_related_news(
    parser: DestinationPageParser, page_url: str
) -> list[dict[str, str | None]]:
    results: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()
    for anchor in parser.news_links:
        url = canonical_related_news_url(page_url, str(anchor["href"]))
        if url in seen_urls:
            continue
        text = clean_text(" ".join(anchor["parts"]))
        headings = clean_text(" ".join(anchor["heading_parts"]))
        title = headings or str(anchor["aria"]) or text
        title = re.sub(
            r"\bUpdated\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", "", title, flags=re.IGNORECASE
        )
        title = clean_text(title).replace("read article", "").strip()
        updated_match = re.search(
            r"\bUpdated\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text, re.IGNORECASE
        )
        summary = text
        if updated_match:
            summary = summary.replace(updated_match.group(0), "")
        if title:
            summary = summary.replace(title, "", 1)
        summary = (
            clean_text(re.sub(r"\bread article\b", "", summary, flags=re.IGNORECASE))
            or None
        )
        if not title:
            continue
        # Footer registration material uses a /news/ instructional URL but is not
        # destination-related news; this skill intentionally excludes registration
        # workflows.
        if (
            title.casefold() == "register your travel"
            or "registering-on-safetravel" in url.casefold()
        ):
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
        parser.validate_complete_document()
    except SchemaError:
        raise
    except (
        Exception
    ) as exc:  # HTMLParser is permissive, but retain a clean parser failure.
        raise SchemaError(f"destination page HTML could not be parsed: {exc}") from exc
    raw_advice = parser.data_content.get("js-advice-level-accordion")
    if not raw_advice:
        raise SchemaError(
            "destination page did not contain SafeTravel advice-level data"
        )
    try:
        raw_items = json.loads(
            html.unescape(raw_advice),
            object_pairs_hook=reject_duplicate_json_members,
            parse_constant=reject_json_constant,
            parse_float=parse_finite_json_float,
        )
    except RecursionError as exc:
        raise SchemaError(
            "destination advice-level JSON exceeded the supported nesting depth"
        ) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise SchemaError(
            f"destination advice-level data was not valid JSON: {exc}"
        ) from exc
    ensure_bounded_json_depth(raw_items)
    if not isinstance(raw_items, list) or not raw_items:
        raise SchemaError("destination advice-level data was empty")
    advice_items = [parse_advice_item(item) for item in raw_items]
    regional_flags = [required_regional_classification(item) for item in raw_items]
    primary_items = [
        item
        for index, item in enumerate(advice_items)
        if not regional_flags[index]
    ]
    if len(primary_items) != 1:
        raise SchemaError(
            "destination advice-level data must contain exactly one non-regional "
            "primary item"
        )
    primary = primary_items[0]
    regional = [
        item
        for index, item in enumerate(advice_items)
        if regional_flags[index]
    ]
    page_text = clean_text(" ".join(parser.visible_parts))
    page_updated_match = re.search(
        r"\bPage updated\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", page_text, re.IGNORECASE
    )
    name = clean_text(" ".join(parser.h1_parts))
    if not name:
        raise SchemaError(
            "destination page identity was missing its destination heading"
        )
    if destination_identity_key(name) != destination_identity_key(slug):
        raise SchemaError(
            "destination page identity did not match the requested destination: "
            f"expected {slug!r}, found {name!r}"
        )
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
        retry_after = exc.retry_after
        retry_hint = f"; retry after {retry_after}" if retry_after else ""
        raise RateLimitedError(
            f"source rate-limited: {exc}{retry_hint}", retry_after=retry_after
        ) from exc
    except nzfetch.Blocked as exc:
        raise BlockedError(f"source blocked: {exc}") from exc
    except nzfetch.FetchError as exc:
        raise SkillError(f"network error: upstream unavailable: {exc}", 5) from exc
    try:
        return body.decode("utf-8"), final_url
    except UnicodeDecodeError as exc:
        raise SchemaError(f"official source returned non-UTF-8 content: {exc}") from exc


def source_metadata(
    url: str, retrieved_at: str, *, page_updated: str | None = None
) -> dict[str, str | None]:
    return {
        "name": SOURCE_NAME,
        "owner": SOURCE_OWNER,
        "url": url,
        "retrieved_at": retrieved_at,
        "page_updated": page_updated,
    }


def result_envelope(
    *, source: dict[str, str | None], query: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
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
    text, final_url = fetch_text(
        SITEMAP_URL, accept="application/xml,text/xml;q=0.9,*/*;q=0.8"
    )
    if final_url != SITEMAP_URL:
        raise SchemaError(
            "sitemap fetch did not resolve to the canonical SafeTravel sitemap URL"
        )
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
        raise SkillError(
            f"destination '{slug}' was not found in the official SafeTravel "
            "sitemap; use search first",
            2,
        )
    page_url = str(destination["url"])
    retrieved_at = utc_now()
    source, final_url = fetch_text(
        page_url, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
    )
    if final_url != page_url:
        canonical_final_slug = canonical_destination_slug(final_url)
        if (
            canonical_final_slug is not None
            and final_url == f"{DESTINATION_PREFIX}{canonical_final_slug}"
            and canonical_final_slug != slug
        ):
            raise SchemaError(
                "destination fetch resolved to a different canonical destination: "
                f"requested {slug!r}, received {canonical_final_slug!r}"
            )
        raise SchemaError(
            "destination fetch did not resolve to the exact canonical destination URL"
        )
    final_slug = canonical_destination_slug(final_url)
    if final_slug is None:
        raise SchemaError(
            "destination fetch did not resolve to a canonical SafeTravel "
            "destination URL"
        )
    if final_slug != slug:
        raise SchemaError(
            "destination fetch resolved to a different canonical destination: "
            f"requested {slug!r}, received {final_slug!r}"
        )
    data = parse_destination_page(source, slug=slug, url=final_url)
    return result_envelope(
        source=source_metadata(
            final_url, retrieved_at, page_updated=data["destination"]["page_updated"]
        ),
        query={
            "command": "advice",
            "destination": slug,
            "sitemap_url": sitemap_url,
            "sitemap_retrieved_at": sitemap_retrieved_at,
        },
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

    search = subparsers.add_parser(
        "search", help="search official SafeTravel destination pages"
    )
    search.add_argument("query", help="destination name or words")
    search.add_argument(
        "--limit",
        type=positive_limit,
        default=20,
        help="maximum matches, 1-100 (default: 20)",
    )
    search.add_argument(
        "--json", action="store_true", help="emit the result envelope as JSON"
    )
    search.set_defaults(handler=cmd_search)

    advice = subparsers.add_parser(
        "advice", help="fetch current advice for one official destination"
    )
    advice.add_argument(
        "destination",
        help="destination name, slug, or canonical SafeTravel destination URL",
    )
    advice.add_argument(
        "--json", action="store_true", help="emit the result envelope as JSON"
    )
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
            print(
                "No official destination pages matched. Try fewer or different words."
            )
        print(f"Sitemap retrieved: {source['retrieved_at']} — {source['url']}")
    else:
        destination = data["destination"]
        level = data["advice_level"]
        print(destination["name"])
        print(
            f"Advice level {level['number']} of 4 ({level['level']}): {level['title']}"
        )
        print(level["body"])
        if destination.get("page_updated"):
            print(f"Page updated: {destination['page_updated']}")
        if data["regional_cautions"]:
            print("Regional cautions:")
            for item in data["regional_cautions"]:
                print(
                    f"- Level {item['number']} ({item['level']}): {item['title']} "
                    f"{item['subtitle']}"
                )
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
    except nzfetch.RateLimited as exc:
        retry_after = exc.retry_after
        retry_hint = f"; retry after {retry_after}" if retry_after else ""
        error = RateLimitedError(
            f"source rate-limited: {exc}{retry_hint}", retry_after=retry_after
        )
        if args.json:
            print(
                json.dumps(error.error_payload(), indent=2, ensure_ascii=False),
                file=sys.stderr,
            )
        else:
            print(f"{SKILL}: {error}", file=sys.stderr)
        return error.code
    except nzfetch.Blocked as exc:
        error = BlockedError(f"source blocked: {exc}")
        if args.json:
            print(
                json.dumps(error.error_payload(), indent=2, ensure_ascii=False),
                file=sys.stderr,
            )
        else:
            print(f"{SKILL}: {error}", file=sys.stderr)
        return error.code
    except SkillError as exc:
        if args.json:
            print(
                json.dumps(exc.error_payload(), indent=2, ensure_ascii=False),
                file=sys.stderr,
            )
        else:
            print(f"{SKILL}: {exc}", file=sys.stderr)
        return exc.code
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
