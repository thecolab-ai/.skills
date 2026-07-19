"""Structured parsers for Product Safety New Zealand recall HTML."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin


def clean(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())


def parse_list(text: str, base: str, retrieved_at: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in re.findall(r'<article\b[^>]*class="[^"]*\brecall\b[^"]*".*?</article>', text, re.S | re.I):
        link = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*>', block, re.I)
        published = re.search(r'<time\b[^>]*datetime="([^"]+)"', block, re.I)
        title = re.search(r'<h1\b[^>]*class="[^"]*\brecall__title\b[^"]*"[^>]*>(.*?)</h1>', block, re.S | re.I)
        if not (link and published and title):
            continue
        url = urljoin(base, link.group(1))
        rows.append({
            "id": url.rstrip("/").split("/")[-1], "title": clean(title.group(1)), "published": published.group(1),
            "categories": [clean(value) for value in re.findall(r'<li\b[^>]*class="[^"]*\brecall__category\b[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.S | re.I)],
            "status": "published", "active": None, "source_url": url, "retrieved_at": retrieved_at,
        })
    if not rows and not re.search(r"no recalls", text, re.I):
        raise ValueError("Product Safety listing contained no recognisable recall articles")
    return rows


def _section(text: str, heading: str) -> str | None:
    match = re.search(
        rf'<h[2-4][^>]*>\s*{re.escape(heading)}\s*</h[2-4]>\s*(.*?)'
        r'(?=<h[2-4]\b|<div\b[^>]*class="[^"]*\brecall__info(?:--|\b)|</(?:section|article)>|$)',
        text,
        re.S | re.I,
    )
    return clean(match.group(1)) if match else None


def matches_filter(row: dict[str, object], command: str, term: str) -> bool:
    """Match a CLI filter only against its declared structured field."""
    field = {"supplier": "supplier", "category": "categories", "hazard": "hazard"}.get(command)
    haystack: object = row.get(field) if field else row
    return term.casefold() in str(haystack).casefold()


def parse_detail(text: str, source: str, retrieved_at: str) -> dict[str, object]:
    title = re.search(r'<h1\b[^>]*>(.*?)</h1>', text, re.S | re.I)
    if not title:
        raise ValueError("Product Safety detail missing title")
    date_match = re.search(r'<(?:time|div)\b[^>]*class="[^"]*\brecall__date\b[^"]*"[^>]*(?:datetime="([^"]+)")?[^>]*>(.*?)</(?:time|div)>', text, re.S | re.I)
    plain = clean(text)
    if re.search(r"recall (?:is |has been )?(?:closed|ended|withdrawn|no longer active)", plain, re.I):
        status, active = "closed", False
    elif re.search(r"(?:active|current) recall", plain, re.I):
        status, active = "active", True
    else:
        status, active = "published", None
    hazard_match = re.search(r'<div\b[^>]*class="[^"]*\brecall__info--hazard\b[^"]*"[^>]*>(.*?)</div>', text, re.S | re.I)
    action_match = re.search(r'<div\b[^>]*class="[^"]*\brecall__info--whattodo\b[^"]*"[^>]*>(.*?)</div>', text, re.S | re.I)
    return {
        "id": source.rstrip("/").split("/")[-1], "title": clean(title.group(1)),
        "published": (date_match.group(1) or clean(date_match.group(2))) if date_match else None,
        "status": status, "active": active,
        "product_identifiers": _section(text, "Product Identifiers"),
        "supplier": _section(text, "Supplier Contact"), "responsible_agency": _section(text, "Responsible Agency"),
        "hazard": clean(hazard_match.group(1)) if hazard_match else _section(text, "Hazard"),
        "remedy": clean(action_match.group(1)) if action_match else _section(text, "What to do"),
        "source_url": source, "retrieved_at": retrieved_at,
    }
