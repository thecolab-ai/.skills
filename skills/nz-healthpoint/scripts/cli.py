#!/usr/bin/env python3
"""Healthpoint NZ lightweight read-only service directory CLI.

Self-contained stdlib wrapper around public Healthpoint search, branch,
nearby, and detail pages. No login, booking, referral, triage, or mutation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import time
import unicodedata
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


BASE = "https://www.healthpoint.co.nz"
UA = os.environ.get(
    "HEALTHPOINT_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)
PAGE_SIZE = 40

BRANCHES: list[dict[str, Any]] = [
    {"slug": "immunisation", "name": "Immunisation", "aliases": ["vaccine", "vaccination"]},
    {
        "slug": "gps-accident-urgent-medical-care",
        "name": "GPs / Accident & Urgent Medical Care",
        "aliases": ["gp", "general-practice", "doctor", "urgent-care", "a-and-m", "accident-medical"],
    },
    {"slug": "pharmacy", "name": "Pharmacy", "aliases": ["chemist", "pharmacies"]},
    {"slug": "public", "name": "Public Hospital Services", "aliases": ["hospital", "public-hospital", "ed"]},
    {"slug": "private", "name": "Private Hospitals & Specialists", "aliases": ["specialist", "private-hospital"]},
    {"slug": "specialised-primary-health-care", "name": "Specialised Primary Health Care", "aliases": []},
    {"slug": "mental-health-addictions", "name": "Mental Health & Addictions", "aliases": ["mental-health"]},
    {"slug": "kaupapa-maori-7", "name": "Kaupapa Maori", "aliases": ["kaupapa-maori"]},
    {"slug": "pacific-people-3", "name": "Pacific People", "aliases": ["pasifika"]},
    {"slug": "community-health-and-social-services", "name": "Community Health and Social Services", "aliases": ["social"]},
    {"slug": "aged-residential-care-1", "name": "Aged Residential Care", "aliases": ["aged-care"]},
    {"slug": "dentistry", "name": "Dentistry", "aliases": ["dentist", "dental"]},
    {"slug": "maternity", "name": "Maternity Services", "aliases": ["midwife", "midwives"]},
    {"slug": "allied-health", "name": "Allied Health", "aliases": ["physio", "physiotherapy"]},
    {"slug": "eye-care", "name": "Eye Care Providers", "aliases": ["optometrist", "optometry"]},
]

TYPE_ALIASES: dict[str, dict[str, str | None]] = {
    "pharmacy": {"branch": "pharmacy", "service_type": None},
    "pharmacies": {"branch": "pharmacy", "service_type": None},
    "chemist": {"branch": "pharmacy", "service_type": None},
    "gp": {"branch": "gps-accident-urgent-medical-care", "service_type": "gp"},
    "gps": {"branch": "gps-accident-urgent-medical-care", "service_type": "gp"},
    "general-practice": {"branch": "gps-accident-urgent-medical-care", "service_type": "gp"},
    "doctor": {"branch": "gps-accident-urgent-medical-care", "service_type": "gp"},
    "urgent-care": {"branch": "gps-accident-urgent-medical-care", "service_type": "accident-urgent-medical-care-ae"},
    "accident-medical": {"branch": "gps-accident-urgent-medical-care", "service_type": "accident-urgent-medical-care-ae"},
    "a-and-m": {"branch": "gps-accident-urgent-medical-care", "service_type": "accident-urgent-medical-care-ae"},
    "ae": {"branch": "gps-accident-urgent-medical-care", "service_type": "accident-urgent-medical-care-ae"},
    "hospital": {"branch": "public", "service_type": None},
    "hospitals": {"branch": "public", "service_type": None},
    "ed": {"branch": "public", "service_type": "emergency"},
    "emergency-department": {"branch": "public", "service_type": "emergency"},
    "dentist": {"branch": "dentistry", "service_type": None},
    "dentistry": {"branch": "dentistry", "service_type": None},
    "dental": {"branch": "dentistry", "service_type": None},
    "optometrist": {"branch": "eye-care", "service_type": None},
    "optometry": {"branch": "eye-care", "service_type": None},
    "physio": {"branch": "allied-health", "service_type": None},
    "physiotherapy": {"branch": "allied-health", "service_type": None},
}

for branch in BRANCHES:
    TYPE_ALIASES.setdefault(branch["slug"], {"branch": branch["slug"], "service_type": None})
    for alias in branch.get("aliases", []):
        TYPE_ALIASES.setdefault(alias, {"branch": branch["slug"], "service_type": None})

REGIONS: list[tuple[str, str]] = [
    ("northland", "Northland"),
    ("north-auckland", "North Auckland"),
    ("east-auckland", "East Auckland"),
    ("central-auckland", "Central Auckland"),
    ("west-auckland", "West Auckland"),
    ("south-auckland", "South Auckland"),
    ("waikato", "Waikato"),
    ("bay-of-plenty", "Bay of Plenty"),
    ("lakes", "Lakes"),
    ("tairawhiti", "Tairawhiti"),
    ("taranaki", "Taranaki"),
    ("hawkes-bay", "Hawke's Bay"),
    ("whanganui", "Whanganui"),
    ("midcentral", "MidCentral"),
    ("wairarapa", "Wairarapa"),
    ("hutt", "Hutt"),
    ("wellington", "Wellington"),
    ("nelson-marlborough", "Nelson Marlborough"),
    ("west-coast", "West Coast"),
    ("canterbury", "Canterbury"),
    ("south-canterbury", "South Canterbury"),
    ("waitaki", "Waitaki"),
    ("dunedin-south-otago", "Dunedin - South Otago"),
    ("central-lakes", "Central Lakes"),
    ("southland", "Southland"),
]
AUCKLAND_REGIONS = ["north-auckland", "east-auckland", "central-auckland", "west-auckland", "south-auckland"]


def die(message: str, code: int = 1) -> None:
    print(f"nz-healthpoint: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|li|div|h[1-6]|tr|summary|td|th)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(value: str, length: int = 180) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= length:
        return value
    return value[: length - 1].rstrip() + "..."


def slugish(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def abs_url(value: str | None) -> str | None:
    if not value:
        return None
    value = html.unescape(value.strip())
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("/"):
        return BASE + value
    if value.startswith("http://www.healthpoint.co.nz"):
        return "https://" + value[len("http://") :]
    return value


def request_text(path_or_url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> tuple[str, str]:
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    if params:
        clean: dict[str, Any] = {}
        for key, value in params.items():
            if value is None or value is False or value == "":
                continue
            clean[key] = value
        if clean:
            sep = "&" if "?" in url else "?"
            url += sep + urllib.parse.urlencode(clean, doseq=True)
    # Healthpoint serves HTML pages (and JSON from /nearme.do). Keep the Accept
    # HTML-shaped so nzfetch's challenge check never mistakes a real page for a
    # JSON interstitial; the one JSON endpoint still parses fine via request_json.
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            headers={"User-Agent": UA, "Referer": BASE + "/"},
        )
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    return body.decode("utf-8", "replace"), final_url


def request_json(path_or_url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    raw, url = request_text(path_or_url, params=params, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def nz_now() -> dt.datetime:
    if ZoneInfo is None:
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.now(ZoneInfo("Pacific/Auckland"))


def parse_clock(text: str) -> int | None:
    text = text.strip().lower().replace(".", "")
    if text == "midnight":
        return 0
    match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text, flags=re.I)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridian = match.group(3).lower()
    if hour == 12:
        hour = 0
    if meridian == "pm":
        hour += 12
    if hour >= 24 or minute >= 60:
        return None
    return hour * 60 + minute


def time_ranges_from_text(text: str) -> list[tuple[int, int]]:
    text = clean_text(text)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    pattern = re.compile(
        r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM)|midnight)\s*(?:to|-)\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM)|midnight)",
        flags=re.I,
    )
    ranges: list[tuple[int, int]] = []
    for start_text, end_text in pattern.findall(text):
        start = parse_clock(start_text)
        end = parse_clock(end_text)
        if start is None or end is None:
            continue
        if start == end:
            end = start + 24 * 60
        elif end < start:
            end += 24 * 60
        ranges.append((start, end))
    return ranges


def open_now_from_status(status: str, now: dt.datetime | None = None) -> bool | None:
    status_clean = clean_text(status).lower()
    if not status_clean:
        return None
    if "closed" in status_clean:
        return False
    ranges = time_ranges_from_text(status)
    if not ranges:
        return True if "open" in status_clean and "today" in status_clean else None
    now = now or nz_now()
    minute = now.hour * 60 + now.minute
    for start, end in ranges:
        if start <= minute <= end:
            return True
        if end > 24 * 60 and minute + 24 * 60 <= end:
            return True
    return False


def closes_after(status: str, hour: int = 21) -> bool | None:
    ranges = time_ranges_from_text(status)
    if not ranges:
        return None
    threshold = hour * 60
    return any(end >= threshold or end >= 24 * 60 for _, end in ranges)


def resolve_type(value: str | None) -> dict[str, str | None]:
    if not value:
        return {"branch": "pharmacy", "service_type": None}
    key = slugish(value)
    config = TYPE_ALIASES.get(key)
    if not config:
        available = ", ".join(sorted(TYPE_ALIASES.keys())[:35])
        die(f"unknown type {value!r}; run `categories` for branches and aliases. Known aliases include: {available}")
    return dict(config)


def resolve_regions(value: str | None) -> list[str | None]:
    if not value:
        return [None]
    key = slugish(value)
    if key in {"auckland", "all-auckland", "tamaki-makaurau"}:
        return AUCKLAND_REGIONS[:]
    region_map = {slug: slug for slug, _ in REGIONS}
    region_map.update({slugish(name): slug for slug, name in REGIONS})
    if key not in region_map:
        names = ", ".join(name for _, name in REGIONS)
        die(f"unknown region {value!r}; supported regions: {names}; use 'Auckland' to search all Auckland subregions")
    return [region_map[key]]


def geocode_near(value: str | None, lat: float | None = None, lng: float | None = None) -> dict[str, Any] | None:
    if lat is not None or lng is not None:
        if lat is None or lng is None:
            die("--lat and --lng must be supplied together")
        return {"value": f"{lat},{lng}", "lat": lat, "lon": lng, "source": "cli"}
    if not value:
        return None
    payload = request_json("/nearme.do", {"q": value})
    if not isinstance(payload, list) or not payload:
        die(f"Healthpoint returned no address matches for {value!r}")
    query_tokens = [token for token in slugish(value).split("-") if token]

    def score(row: Any) -> tuple[int, int]:
        if not isinstance(row, dict):
            return (-999, 0)
        fields = " ".join(str(row.get(k) or "") for k in ("value", "street", "suburb", "city", "region", "postcode"))
        haystack = slugish(fields)
        row_score = 0
        row_score += sum(4 for token in query_tokens if token in haystack)
        if query_tokens and all(token in haystack for token in query_tokens):
            row_score += 20
        city = slugish(str(row.get("city") or ""))
        region = slugish(str(row.get("region") or ""))
        if city and city in query_tokens:
            row_score += 18
        if region and region in query_tokens:
            row_score += 10
        if str(row.get("value") or "").lower().startswith(str(row.get("street") or "").lower()):
            row_score += 2
        return (row_score, -len(str(row.get("value") or "")))

    first = max(payload, key=score)
    if not isinstance(first, dict) or first.get("lat") is None or first.get("lon") is None:
        die(f"Healthpoint returned an unusable address match for {value!r}")
    first = dict(first)
    first["source"] = "/nearme.do"
    first["query"] = value
    return first


def section_by_id(source: str, section_id: str) -> str:
    marker = f'id="{section_id}"'
    idx = source.find(marker)
    if idx < 0:
        return ""
    start = source.rfind("<section", 0, idx)
    if start < 0:
        start = idx
    end = source.find("</section>", idx)
    if end < 0:
        end = source.find("</article>", idx)
    if end < 0:
        end = len(source) - len("</section>")
    return source[start : end + len("</section>")]


def count_from_section(section: str) -> int | None:
    match = re.search(r'<small[^>]*class="count"[^>]*>\s*([0-9,]+)', section, flags=re.I)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def id_from_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(abs_url(url) or url)
    return parsed.path.strip("/")


def branch_from_url(url: str | None) -> str:
    path = urllib.parse.urlparse(abs_url(url) or "").path.strip("/")
    first = path.split("/", 1)[0] if path else ""
    return first


def extract_h4_link(block: str) -> tuple[str | None, str | None]:
    match = re.search(r"<h4[^>]*>.*?<a\s+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.I | re.S)
    if match:
        return match.group(1), clean_text(match.group(2))
    return None, None


def extract_first_link(block: str) -> tuple[str | None, str | None]:
    match = re.search(r"<a\s+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.I | re.S)
    if match:
        return match.group(1), clean_text(match.group(2))
    return None, None


def extract_opening_status(block: str) -> str:
    match = re.search(r'<span[^>]*class="openingstatus"[^>]*>(.*?)</span>\s*</span>', block, flags=re.I | re.S)
    if match:
        return clean_text(match.group(1))
    match = re.search(r'<p[^>]*class="opening-hours"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def extract_phone(block: str) -> str:
    match = re.search(r'href="tel:([^"]+)"', block, flags=re.I)
    if match:
        return urllib.parse.unquote(html.unescape(match.group(1))).strip()
    match = re.search(r"<h4[^>]*>\s*Phone\s*</h4>\s*<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def extract_search_address(block: str) -> str:
    match = re.search(r'<div[^>]*class="search-result-locations"[^>]*>(.*?)</div>', block, flags=re.I | re.S)
    if match:
        return clean_text(match.group(1))
    return ""


def normalize_item(block: str, source_url: str, *, fallback_section: str = "services") -> dict[str, Any] | None:
    href, name = extract_h4_link(block)
    if not href and fallback_section == "locations":
        href, name = extract_first_link(block)
    if not href or not name:
        return None
    status = extract_opening_status(block)
    item = {
        "id": id_from_url(href),
        "name": name,
        "type": branch_from_url(href),
        "url": abs_url(href),
        "address": extract_search_address(block),
        "phone": extract_phone(block),
        "opening_status": status,
        "computed_open_now": open_now_from_status(status),
        "open_late_today_after_9pm": closes_after(status, 21),
        "source_page": source_url,
    }
    return item


def parse_branch_results(source: str, source_url: str, *, section_id: str = "paginator-services") -> dict[str, Any]:
    section = section_by_id(source, section_id)
    if not section:
        return {"source_url": source_url, "source_count": 0, "results": []}
    kind = "locations" if section_id == "paginator-locations" else "services"
    results: list[dict[str, Any]] = []
    if kind == "services":
        chunks = re.split(r"(?=<h4\b)", section, flags=re.I)
    else:
        chunks = re.findall(r"<li\b[^>]*>.*?</li>", section, flags=re.I | re.S)
    for chunk in chunks:
        item = normalize_item(chunk, source_url, fallback_section=kind)
        if item:
            results.append(item)
    return {"source_url": source_url, "source_count": count_from_section(section), "results": results}


def parse_search_results(source: str, source_url: str) -> dict[str, Any]:
    heading = re.search(r"<h1[^>]*>\s*Search results for.*?<small>\s*&ndash;\s*([0-9,]+)\s*found", source, flags=re.I | re.S)
    source_count = int(heading.group(1).replace(",", "")) if heading else None
    chunks = re.split(r'(?=<li[^>]*class="search-result\b)', source, flags=re.I)
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        item = normalize_item(chunk, source_url)
        if item:
            branch_match = re.search(r'<ul[^>]*class="search-result-branches[^"]*"[^>]*>(.*?)</ul>', chunk, flags=re.I | re.S)
            if branch_match:
                item["category"] = clean_text(branch_match.group(1))
            results.append(item)
    return {"source_url": source_url, "source_count": source_count if source_count is not None else len(results), "results": results}


def build_branch_path(branch: str, near: dict[str, Any] | None = None) -> str:
    if near:
        return f"/{branch}/near/{near['lat']},{near['lon']}/"
    return f"/{branch}/"


def fetch_branch(
    *,
    branch: str,
    region: str | None = None,
    near: dict[str, Any] | None = None,
    service_type: str | None = None,
    service_area: str | None = None,
    open_now: bool = False,
    options: list[str] | None = None,
    limit: int = 10,
    section_id: str = "paginator-services",
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    source_total: int | None = None
    pages = 0
    offset = 0
    while len(results) < limit:
        params: dict[str, Any] = {
            "region": region if not near else None,
            "serviceType": service_type,
            "serviceArea": service_area,
            "openNow": "true" if open_now else None,
            "options": options or None,
            "addr": near.get("query") or near.get("value") if near else None,
        }
        if offset:
            params["services" if section_id != "paginator-locations" else "locations"] = offset
        raw, url = request_text(build_branch_path(branch, near), params)
        page = parse_branch_results(raw, url, section_id=section_id)
        pages += 1
        if source_total is None and page.get("source_count") is not None:
            source_total = page["source_count"]
        batch = page["results"]
        if open_now:
            batch = [item for item in batch if item.get("computed_open_now") is not False]
        results.extend(batch)
        if not batch or source_total is not None and offset + PAGE_SIZE >= source_total:
            break
        offset += PAGE_SIZE
        if pages >= 8:
            break
    return {
        "source_count": source_total,
        "pages_fetched": pages,
        "results": results[:limit],
    }


def fetch_typed_results(
    *,
    type_value: str | None,
    query: str | None = None,
    region: str | None = None,
    near_text: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    open_now: bool = False,
    options: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    config = resolve_type(type_value)
    query_filter = query
    if query and type_value:
        branch_aliases = {str(config["branch"]), slugish(type_value)}
        for branch in BRANCHES:
            if branch["slug"] == config["branch"]:
                branch_aliases.add(slugish(branch["name"]))
                branch_aliases.update(slugish(alias) for alias in branch.get("aliases", []))
        if slugish(query) in branch_aliases:
            query_filter = None
    near = geocode_near(near_text, lat, lng)
    regions = [None] if near else resolve_regions(region)
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_count = 0
    pages = 0
    for resolved_region in regions:
        page = fetch_branch(
            branch=str(config["branch"]),
            region=resolved_region,
            near=near,
            service_type=config.get("service_type"),
            open_now=open_now,
            options=options or [],
            limit=max(limit, PAGE_SIZE if query else limit),
        )
        source_count += int(page.get("source_count") or 0)
        pages += int(page.get("pages_fetched") or 0)
        for item in page["results"]:
            if query_filter:
                haystack = " ".join(str(item.get(k) or "") for k in ("name", "address", "opening_status", "type")).lower()
                if query_filter.lower() not in haystack:
                    continue
            key = item["id"]
            if key not in seen:
                item["region_filter"] = resolved_region
                combined.append(item)
                seen.add(key)
            if len(combined) >= limit:
                break
        if len(combined) >= limit:
            break
    return {
        "query": query,
        "type": type_value or "pharmacy",
        "branch": config["branch"],
        "service_type": config.get("service_type"),
        "region": region,
        "near": near,
        "open_now_filter": open_now,
        "options": options or [],
        "source_count": source_count or None,
        "count": len(combined),
        "pages_fetched": pages,
        "results": combined[:limit],
    }


def detail_path(identifier: str) -> str:
    value = identifier.strip()
    if value.startswith("http"):
        path = urllib.parse.urlparse(value).path
    elif value.startswith("/"):
        path = value
    else:
        path = "/" + value
    if not path.endswith("/"):
        path += "/"
    return path


def extract_meta_content(source: str, prop: str) -> str:
    match = re.search(rf'<meta[^>]+itemprop="{re.escape(prop)}"[^>]+content="([^"]*)"', source, flags=re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def extract_title(source: str) -> str:
    for value in re.findall(r"<h1[^>]*>(.*?)</h1>", source, flags=re.I | re.S):
        text = clean_text(value)
        if text and text.lower() != "healthpoint":
            return text
    return ""


def extract_hours(source: str) -> dict[str, Any]:
    status = ""
    first_status = re.search(r'<p[^>]*class="opening-hours"[^>]*>(.*?)</p>', source, flags=re.I | re.S)
    if first_status:
        status = clean_text(first_status.group(1))
    table = re.search(r'<table[^>]*class="hours"[^>]*>(.*?)</table>', source, flags=re.I | re.S)
    rows: list[dict[str, str]] = []
    if table:
        for day, value in re.findall(r"<tr[^>]*>\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>\s*</tr>", table.group(1), flags=re.I | re.S):
            rows.append({"days": clean_text(day), "hours": clean_text(value)})
    holidays = ""
    hol_match = re.search(r'<p[^>]*class="hours-holidays"[^>]*>(.*?)</p>', source, flags=re.I | re.S)
    if hol_match:
        holidays = clean_text(hol_match.group(1))
    open_late = any(closes_after(row["hours"], 21) for row in rows)
    return {
        "today": status,
        "computed_open_now": open_now_from_status(status),
        "rows": rows,
        "public_holidays": holidays,
        "open_late_after_9pm_any_listed_day": open_late,
    }


def extract_label_values(source: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in re.findall(r"<li\b[^>]*>.*?</li>", source, flags=re.I | re.S):
        label_match = re.search(r'<h4[^>]*class="label-text"[^>]*>(.*?)</h4>', block, flags=re.I | re.S)
        if not label_match:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", clean_text(label_match.group(1)).lower()).strip("_")
        if key == "phone":
            text = extract_phone(block)
        else:
            text_block = re.sub(r'<h4[^>]*class="label-text"[^>]*>.*?</h4>', " ", block, count=1, flags=re.I | re.S)
            text = clean_text(text_block)
        if key and text and key not in out:
            out[key] = text
    return out


def extract_address(source: str) -> str:
    match = re.search(
        r'<h4[^>]*class="label-text"[^>]*>\s*Street Address\s*</h4>\s*<div[^>]*itemprop="address"[^>]*>(.*?)</div>',
        source,
        flags=re.I | re.S,
    )
    if match:
        return clean_text(match.group(1))
    match = re.search(r'<div[^>]*itemprop="address"[^>]*>(.*?)</div>', source, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def extract_website(source: str) -> str:
    match = re.search(r'<a\s+href="([^"]+)"[^>]*itemprop="url"', source, flags=re.I | re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    return ""


def extract_description(source: str) -> str:
    match = re.search(r'<h3[^>]*class="section-header"[^>]*>\s*Description\s*</h3>\s*</div>\s*<div[^>]*class="content"[^>]*>(.*?)</div>', source, flags=re.I | re.S)
    if match:
        return truncate(clean_text(match.group(1)), 700)
    match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', source, flags=re.I)
    return truncate(html.unescape(match.group(1)), 700) if match else ""


def extract_services(source: str) -> list[str]:
    names = [clean_text(x) for x in re.findall(r'<span[^>]*class="practice-name"[^>]*>(.*?)</span>', source, flags=re.I | re.S)]
    names += [clean_text(x) for x in re.findall(r'<div[^>]*class="collapsible-title-en"[^>]*>(.*?)</div>', source, flags=re.I | re.S)]
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def extract_fees(source: str) -> list[str]:
    match = re.search(
        r"<h3[^>]*>\s*Fees and Charges Categorisation\s*</h3>\s*<div[^>]*class=\"content\"[^>]*>(.*?)</div>",
        source,
        flags=re.I | re.S,
    )
    text = clean_text(match.group(1)) if match else ""
    fees: list[str] = []
    for part in re.split(r",|\n", text):
        value = clean_text(part)
        if value and value not in fees:
            fees.append(value)
    return fees


def parse_detail(identifier: str) -> dict[str, Any]:
    raw, url = request_text(detail_path(identifier))
    contacts = extract_label_values(raw)
    lat_text = extract_meta_content(raw, "latitude")
    lng_text = extract_meta_content(raw, "longitude")
    services = extract_services(raw)
    detail = {
        "id": id_from_url(url),
        "name": extract_title(raw),
        "url": url,
        "type": branch_from_url(url),
        "description": extract_description(raw),
        "address": extract_address(raw),
        "phone": contacts.get("phone", ""),
        "contacts": contacts,
        "website": extract_website(raw),
        "latitude": float(lat_text) if lat_text else None,
        "longitude": float(lng_text) if lng_text else None,
        "hours": extract_hours(raw),
        "services": services,
        "fees": extract_fees(raw),
        "has_emergency_department": any("emergency department" in name.lower() for name in services)
        or "Emergency Department" in raw,
    }
    return detail


def enrich_open_late(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        late = item.get("open_late_today_after_9pm")
        if late is not True:
            try:
                detail = parse_detail(item["id"])
                item["hours"] = detail.get("hours")
                late = bool((detail.get("hours") or {}).get("open_late_after_9pm_any_listed_day"))
            except SystemExit:
                late = item.get("open_late_today_after_9pm")
        item["open_late_after_9pm"] = bool(late)
        if item["open_late_after_9pm"]:
            enriched.append(item)
    return enriched


def fetch_hospitals(region: str | None, limit: int, ed_only: bool) -> dict[str, Any]:
    regions = resolve_regions(region)
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_count = 0
    for resolved_region in regions:
        page = fetch_branch(
            branch="public",
            region=resolved_region,
            limit=max(limit * (3 if ed_only else 1), 10),
            section_id="paginator-locations",
        )
        source_count += int(page.get("source_count") or 0)
        for item in page["results"]:
            if item["id"] in seen:
                continue
            detail = parse_detail(item["id"])
            item.update(
                {
                    "address": detail.get("address") or item.get("address"),
                    "phone": detail.get("phone") or item.get("phone"),
                    "latitude": detail.get("latitude"),
                    "longitude": detail.get("longitude"),
                    "has_emergency_department": detail.get("has_emergency_department"),
                    "emergency_services": [s for s in detail.get("services", []) if "emergency" in s.lower()],
                    "region_filter": resolved_region,
                }
            )
            if ed_only and not item.get("has_emergency_department"):
                seen.add(item["id"])
                continue
            combined.append(item)
            seen.add(item["id"])
            if len(combined) >= limit:
                break
        if len(combined) >= limit:
            break
    return {
        "type": "hospital",
        "region": region,
        "ed_only": ed_only,
        "source_count": source_count or None,
        "count": len(combined),
        "results": combined[:limit],
    }


def emit(data: dict[str, Any], as_json: bool, printer: Any) -> None:
    if as_json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        printer(data)


def print_results(data: dict[str, Any]) -> None:
    label = data.get("type") or data.get("query") or "results"
    bits = [str(label), f"{data.get('count', 0)} results"]
    if data.get("source_count") is not None:
        bits.append(f"{data.get('source_count')} source matches")
    if data.get("near"):
        bits.append(f"near {data['near'].get('value')}")
    if data.get("region"):
        bits.append(f"region {data.get('region')}")
    print(": ".join([bits[0], ", ".join(bits[1:])]))
    print()
    for item in data.get("results") or []:
        status = item.get("opening_status") or ""
        open_now = item.get("computed_open_now")
        state = "open now" if open_now is True else "closed now" if open_now is False else "hours unknown"
        print(item.get("name", ""))
        meta = [state]
        if status:
            meta.append(status)
        if item.get("phone"):
            meta.append(item["phone"])
        print("  " + " | ".join(meta))
        if item.get("address"):
            print(f"  {item['address']}")
        print(f"  id: {item.get('id')}")
        print(f"  {item.get('url')}")
        print()


def print_categories(data: dict[str, Any]) -> None:
    print("Healthpoint NZ categories")
    for branch in data["categories"]:
        aliases = ", ".join(branch.get("aliases") or [])
        suffix = f" ({aliases})" if aliases else ""
        print(f"{branch['slug']:<40} {branch['name']}{suffix}")
    print()
    print("Regions: " + ", ".join(name for _, name in REGIONS))


def print_detail(data: dict[str, Any]) -> None:
    print(data.get("name") or data.get("id"))
    print(data.get("url"))
    if data.get("address"):
        print(f"Address: {data['address']}")
    if data.get("phone"):
        print(f"Phone: {data['phone']}")
    hours = data.get("hours") or {}
    if hours.get("today"):
        state = "open now" if hours.get("computed_open_now") else "closed now"
        print(f"Today: {hours['today']} ({state})")
    if hours.get("rows"):
        print("Hours:")
        for row in hours["rows"]:
            print(f"  {row['days']}: {row['hours']}")
    if data.get("services"):
        print("Services:")
        for service in data["services"][:20]:
            print(f"  - {service}")
    if data.get("has_emergency_department"):
        print("Emergency Department: listed")
    if data.get("description"):
        print(f"Description: {data['description']}")


def print_hospitals(data: dict[str, Any]) -> None:
    print(f"hospitals: {data.get('count', 0)} results")
    print()
    for item in data.get("results") or []:
        ed = "yes" if item.get("has_emergency_department") else "no"
        print(item.get("name", ""))
        print(f"  ED listed: {ed}")
        if item.get("emergency_services"):
            print("  " + "; ".join(item["emergency_services"]))
        if item.get("phone"):
            print(f"  Phone: {item['phone']}")
        if item.get("address"):
            print(f"  Address: {item['address']}")
        print(f"  id: {item.get('id')}")
        print(f"  {item.get('url')}")
        print()


def cmd_categories(args: argparse.Namespace) -> None:
    data = {"categories": BRANCHES, "regions": [{"slug": slug, "name": name} for slug, name in REGIONS]}
    emit(data, args.json, print_categories)


def cmd_search(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    options = []
    if getattr(args, "open_saturday", False):
        options.append("openWeekends")
    if getattr(args, "open_sunday", False):
        options.append("openSundays")
    if getattr(args, "open_weekends", False):
        options.append("openWeekends")
    if args.type or args.region or args.near or args.lat is not None or args.open_now:
        data = fetch_typed_results(
            type_value=args.type,
            query=args.query,
            region=args.region,
            near_text=args.near,
            lat=args.lat,
            lng=args.lng,
            open_now=args.open_now,
            options=options,
            limit=args.limit,
        )
    else:
        if not args.query:
            die("search requires a query unless --type, --region, --near, or --open-now is supplied")
        raw, url = request_text("/search", {"q": args.query})
        data = parse_search_results(raw, url)
        if args.open_now:
            data["results"] = [item for item in data["results"] if item.get("computed_open_now") is not False]
        data.update({"query": args.query, "count": len(data["results"][: args.limit]), "results": data["results"][: args.limit]})
    data["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    emit(data, args.json, print_results)


def cmd_practice(args: argparse.Namespace) -> None:
    data = parse_detail(args.id)
    emit(data, args.json, print_detail)


def cmd_open_now(args: argparse.Namespace) -> None:
    data = fetch_typed_results(
        type_value=args.type,
        region=args.region,
        near_text=args.near,
        lat=args.lat,
        lng=args.lng,
        open_now=True,
        limit=args.limit,
    )
    data["command"] = "open-now"
    emit(data, args.json, print_results)


def cmd_urgent_care(args: argparse.Namespace) -> None:
    data = fetch_typed_results(
        type_value="urgent-care",
        region=args.region,
        near_text=args.near,
        lat=args.lat,
        lng=args.lng,
        open_now=args.open_now,
        limit=args.limit,
    )
    data["command"] = "urgent-care"
    emit(data, args.json, print_results)


def cmd_pharmacies(args: argparse.Namespace) -> None:
    options = ["openLate"] if args.open_late else []
    fetch_limit = max(args.limit * 8, PAGE_SIZE) if args.open_late else args.limit
    data = fetch_typed_results(
        type_value="pharmacy",
        region=args.region,
        near_text=args.near,
        lat=args.lat,
        lng=args.lng,
        open_now=args.open_now,
        options=options,
        limit=fetch_limit,
    )
    if args.open_late:
        data["results"] = enrich_open_late(data["results"])[: args.limit]
        data["count"] = len(data["results"])
        data["open_late_filter"] = "after 9pm on at least one listed day where detail hours are available"
    else:
        data["results"] = data["results"][: args.limit]
        data["count"] = len(data["results"])
    data["command"] = "pharmacies"
    emit(data, args.json, print_results)


def cmd_hospitals(args: argparse.Namespace) -> None:
    data = fetch_hospitals(args.region, args.limit, args.ed_only)
    emit(data, args.json, print_hospitals)


def add_common_location_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--region", help="Healthpoint region name or slug; 'Auckland' searches all Auckland subregions")
    sp.add_argument("--near", help="address/place text resolved through Healthpoint /nearme.do; first suggestion is used")
    sp.add_argument("--lat", type=float, help="latitude for nearby search; use with --lng")
    sp.add_argument("--lng", type=float, help="longitude for nearby search; use with --lat")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight read-only Healthpoint NZ service directory CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("categories", help="list supported Healthpoint categories and regions")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)

    sp = sub.add_parser("search", help="search Healthpoint services or typed branch listings")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--type", help="service type, e.g. pharmacy, gp, urgent-care, hospital, dentist")
    sp.add_argument("--open-now", action="store_true")
    sp.add_argument("--open-saturday", action="store_true", help="typed branch filter for services open Saturdays where Healthpoint exposes it")
    sp.add_argument("--open-sunday", action="store_true", help="typed branch filter for services open Sundays where Healthpoint exposes it")
    sp.add_argument("--open-weekends", action="store_true", help="typed branch filter for services open weekends where Healthpoint exposes it")
    add_common_location_flags(sp)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("practice", help="fetch one Healthpoint service/hospital detail page by id/path/url")
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_practice)

    sp = sub.add_parser("open-now", help="list services currently open; defaults to pharmacies")
    sp.add_argument("--type", default="pharmacy", help="service type, e.g. pharmacy, gp, urgent-care, dentist")
    add_common_location_flags(sp)
    sp.set_defaults(func=cmd_open_now)

    sp = sub.add_parser("urgent-care", help="list Accident & Urgent Medical Care providers")
    sp.add_argument("--open-now", action="store_true")
    add_common_location_flags(sp)
    sp.set_defaults(func=cmd_urgent_care)

    sp = sub.add_parser("pharmacies", help="list pharmacies, optionally open now or late night")
    sp.add_argument("--open-now", action="store_true")
    sp.add_argument("--open-late", action="store_true", help="filter to pharmacies with detail hours open after 9pm")
    add_common_location_flags(sp)
    sp.set_defaults(func=cmd_pharmacies)

    sp = sub.add_parser("hospitals", help="list public hospital locations and Emergency Department indicator")
    sp.add_argument("--region", help="Healthpoint region name or slug; 'Auckland' searches all Auckland subregions")
    sp.add_argument("--ed-only", action="store_true", help="only return hospitals where an ED is listed on the detail page")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_hospitals)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) < 1:
        die("--limit must be at least 1")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
