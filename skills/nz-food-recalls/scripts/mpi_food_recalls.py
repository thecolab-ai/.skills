"""Parsers for MPI's recalled-food list and detail pages."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin


def clean(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())


def parse_list(text: str, base: str, retrieved_at: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    headings = list(re.finditer(r'<h2[^>]*>\s*(20\d{2}) recalls\s*</h2>', text, re.S | re.I))
    for index, heading in enumerate(headings):
        block = text[heading.end() : headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        for href, title_html in re.findall(r'<a[^>]+href="([^"]*recalled-food-products/[^"]+)"[^>]*>(.*?)</a>', block, re.S | re.I):
            title = clean(title_html)
            if title:
                rows.append({
                    "id": href.rstrip("/").split("/")[-1], "title": title, "year": int(heading.group(1)),
                    "status": "published", "active": None, "source_url": urljoin(base, href), "retrieved_at": retrieved_at,
                })
    if not rows and not re.search(r"no recalls", text, re.I):
        raise ValueError("MPI recalled-food list contained no recognisable yearly recall links")
    return rows


def _sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r'<h[23][^>]*>(.*?)</h[23]>', text, re.S | re.I))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = clean(match.group(1)).casefold()
        value = clean(text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        if name and value:
            result[name] = value
    return result


def _first(sections: dict[str, str], *names: str) -> str | None:
    for candidate in names:
        for heading, value in sections.items():
            if candidate in heading:
                return value
    return None


def parse_detail(text: str, source: str, retrieved_at: str) -> dict[str, object]:
    heading = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S | re.I)
    if not heading:
        raise ValueError("MPI recall detail missing title")
    sections = _sections(text)
    plain = clean(text)
    reviewed = re.search(r"Last reviewed:\s*(\d{1,2}[./ -](?:\d{1,2}|[A-Za-z]+)[./ -]\d{4})", plain, re.I)
    if re.search(r"(?:recall|notice) (?:is |has been )?(?:closed|ended|withdrawn|no longer active)", plain, re.I):
        status, active = "closed", False
    elif re.search(r"(?:active|current) recall", plain, re.I):
        status, active = "active", True
    else:
        status, active = "published", None
    title = clean(heading.group(1))
    product_information = _first(sections, "product information", "affected product")
    hazard = _first(sections, "reason for the recall", "food safety risk", "hazard") or title
    return {
        "id": source.rstrip("/").split("/")[-1], "title": title, "updated": reviewed.group(1) if reviewed else None,
        "status": status, "active": active, "product_information": product_information,
        "package_and_batch": _first(sections, "batch", "date marking", "package size"),
        "allergen_or_hazard": hazard,
        "distribution": _first(sections, "where the products were sold", "where the product was sold", "distribution"),
        "consumer_action": _first(sections, "what to do if you bought", "consumer action"),
        "contact": _first(sections, "who to contact", "contact"),
        "source_url": source, "retrieved_at": retrieved_at,
    }
