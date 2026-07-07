#!/usr/bin/env python3
"""Bookme NZ lightweight deals CLI.

Self-contained stdlib wrapper around Bookme's public read-only deal endpoints.
No login, booking, checkout, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_WEB = "https://www.bookme.co.nz"
CONTEXT = "/things-to-do"
UA = os.environ.get(
    "BOOKME_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

REGIONS = [
    {"slug": "new-zealand", "name": "New Zealand"},
    {"slug": "northland-bay-of-islands", "name": "Northland - Bay of Islands"},
    {"slug": "auckland", "name": "Auckland - Waiheke Island - Warkworth"},
    {"slug": "coromandel-great-barrier", "name": "Coromandel Peninsula - Great Barrier Island"},
    {"slug": "waikato-hamilton-raglan", "name": "Hamilton & Raglan - Waikato"},
    {"slug": "tauranga", "name": "BOP - Tauranga - Maunganui - Whakatane"},
    {"slug": "rotorua-taupo", "name": "Rotorua - Taupo - Waitomo"},
    {"slug": "gisborne-east-cape", "name": "Gisborne - East Cape to Mahia"},
    {"slug": "hawkes-bay-napier-hastings", "name": "Hawkes Bay - Napier & Hastings"},
    {"slug": "taranaki-new-plymouth", "name": "Taranaki - New Plymouth"},
    {"slug": "manawatu", "name": "Manawatu - Whanganui to Masterton & Martinborough"},
    {"slug": "wellington-wairarapa", "name": "Wellington - Wairarapa"},
    {"slug": "abel-tasman-nelson-picton", "name": "Abel Tasman - Nelson - Picton"},
    {"slug": "west-coast-glacier-country", "name": "West Coast - Glacier Country"},
    {"slug": "christchurch-canterbury-kaikoura", "name": "Christchurch - Canterbury - Kaikoura"},
    {"slug": "queenstown", "name": "Queenstown - Southern Lakes - Fiordland"},
    {"slug": "queenstown/milford-sound", "name": "Milford Sound"},
    {"slug": "dunedin", "name": "Dunedin - Coastal Otago - Oamaru"},
    {"slug": "new-zealand/franz_josefwaiau", "name": "Franz Josef Glacier / Waiau"},
    {"slug": "southland", "name": "Southland & Te Anau"},
]

REGION_ALIASES = {
    "nz": "new-zealand",
    "new zealand": "new-zealand",
    "northland": "northland-bay-of-islands",
    "bay of islands": "northland-bay-of-islands",
    "auckland": "auckland",
    "waiheke": "auckland",
    "coromandel": "coromandel-great-barrier",
    "great barrier": "coromandel-great-barrier",
    "waikato": "waikato-hamilton-raglan",
    "hamilton": "waikato-hamilton-raglan",
    "raglan": "waikato-hamilton-raglan",
    "tauranga": "tauranga",
    "bay of plenty": "tauranga",
    "bop": "tauranga",
    "rotorua": "rotorua-taupo",
    "taupo": "rotorua-taupo",
    "waitomo": "rotorua-taupo",
    "gisborne": "gisborne-east-cape",
    "east cape": "gisborne-east-cape",
    "hawkes bay": "hawkes-bay-napier-hastings",
    "hawke's bay": "hawkes-bay-napier-hastings",
    "napier": "hawkes-bay-napier-hastings",
    "hastings": "hawkes-bay-napier-hastings",
    "taranaki": "taranaki-new-plymouth",
    "new plymouth": "taranaki-new-plymouth",
    "manawatu": "manawatu",
    "whanganui": "manawatu",
    "wellington": "wellington-wairarapa",
    "wairarapa": "wellington-wairarapa",
    "nelson": "abel-tasman-nelson-picton",
    "abel tasman": "abel-tasman-nelson-picton",
    "picton": "abel-tasman-nelson-picton",
    "west coast": "west-coast-glacier-country",
    "glacier country": "west-coast-glacier-country",
    "christchurch": "christchurch-canterbury-kaikoura",
    "canterbury": "christchurch-canterbury-kaikoura",
    "kaikoura": "christchurch-canterbury-kaikoura",
    "queenstown": "queenstown",
    "milford sound": "queenstown/milford-sound",
    "dunedin": "dunedin",
    "franz josef": "new-zealand/franz_josefwaiau",
    "franz josef glacier": "new-zealand/franz_josefwaiau",
    "southland": "southland",
    "te anau": "southland",
}

CATEGORIES = [
    {"id": 154, "slug": "aquariums", "name": "Aquariums", "classification": "Activities"},
    {"id": 268, "slug": "beer-tours", "name": "Beer Tours", "classification": "Activities"},
    {"id": 136, "slug": "boat-tours-day-cruises", "name": "Boat Tours & Day Cruises", "classification": "Activities"},
    {"id": 271, "slug": "boat-hire", "name": "Boat hire", "classification": "Activities"},
    {"id": 100, "slug": "bungy-jumping", "name": "Bungy Jumping", "classification": "Activities"},
    {"id": 130, "slug": "climbing", "name": "Climbing", "classification": "Activities"},
    {"id": 151, "slug": "cultural-attractions", "name": "Cultural Attractions", "classification": "Activities"},
    {"id": 249, "slug": "cultural-experiences", "name": "Cultural Experiences", "classification": "Activities"},
    {"id": 123, "slug": "cycling", "name": "Cycling", "classification": "Activities"},
    {"id": 132, "slug": "day-spa-massage", "name": "Day Spa & Massage", "classification": "Activities"},
    {"id": 134, "slug": "entertainment", "name": "Entertainment", "classification": "Activities"},
    {"id": 117, "slug": "fishing", "name": "Fishing", "classification": "Activities"},
    {"id": 126, "slug": "golf", "name": "Golf", "classification": "Activities"},
    {"id": 116, "slug": "horse-trekking", "name": "Horse Trekking", "classification": "Activities"},
    {"id": 104, "slug": "jet-boating", "name": "Jet Boating", "classification": "Activities"},
    {"id": 122, "slug": "kayaking", "name": "Kayaking", "classification": "Activities"},
    {"id": 135, "slug": "lessons-learn-to", "name": "Lessons & Learn to", "classification": "Activities"},
    {"id": 107, "slug": "mountain-biking", "name": "Mountain Biking", "classification": "Activities"},
    {"id": 149, "slug": "museums", "name": "Museums", "classification": "Activities"},
    {"id": 150, "slug": "natural-wonders", "name": "Natural Wonders", "classification": "Activities"},
    {"id": 248, "slug": "nature-wildlife", "name": "Nature & Wildlife", "classification": "Activities"},
    {"id": 127, "slug": "paintball", "name": "Paintball", "classification": "Activities"},
    {"id": 146, "slug": "private-tours", "name": "Private Tours", "classification": "Activities"},
    {"id": 113, "slug": "rock-climbing", "name": "Rock Climbing", "classification": "Activities"},
    {"id": 115, "slug": "sailing-cruises", "name": "Sailing & Cruises", "classification": "Activities"},
    {"id": 137, "slug": "sightseeing-scenic-tours", "name": "Sightseeing & Scenic Tours", "classification": "Activities"},
    {"id": 106, "slug": "skydiving", "name": "Skydiving", "classification": "Activities"},
    {"id": 114, "slug": "snowboarding-skiing", "name": "Snowboarding & Skiing", "classification": "Activities"},
    {"id": 128, "slug": "sports-hire", "name": "Sports Hire", "classification": "Activities"},
    {"id": 152, "slug": "theme-parks", "name": "Theme Parks", "classification": "Activities"},
    {"id": 147, "slug": "transport", "name": "Transport", "classification": "Activities"},
    {"id": 158, "slug": "waiheke-island", "name": "Waiheke Island", "classification": "Activities"},
    {"id": 124, "slug": "walking-hiking", "name": "Walking & Hiking", "classification": "Activities"},
    {"id": 140, "slug": "walking-tours", "name": "Walking Tours", "classification": "Activities"},
    {"id": 139, "slug": "wine-tours", "name": "Wine Tours", "classification": "Activities"},
    {"id": 102, "slug": "zip-lines-flying-fox-and-rope-courses", "name": "Zip Lines, Flying Fox and Rope Courses", "classification": "Activities"},
    {"id": 148, "slug": "zoos-animal-parks", "name": "Zoos & Animal Parks", "classification": "Activities"},
    {"id": 177, "slug": "breakfast", "name": "Breakfast", "classification": "Dining", "subclassification": "breakfast"},
    {"id": 178, "slug": "lunch", "name": "Lunch", "classification": "Dining", "subclassification": "lunch"},
    {"id": 179, "slug": "dinner", "name": "Dinner", "classification": "Dining", "subclassification": "dinner"},
    {"id": None, "slug": "restaurants", "name": "Restaurants", "classification": "Dining"},
    {"id": None, "slug": "dining", "name": "Dining", "classification": "Dining"},
    {"id": None, "slug": "movies", "name": "Movies", "classification": "Activities", "query_hint": "movie"},
]

DINING_SUBCLASSIFICATIONS = ["breakfast", "lunch", "dinner"]


def die(message: str, code: int = 1) -> None:
    print(f"bookme-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = BASE_WEB + path
    if params:
        clean = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in params.items() if v not in (None, "")}
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE_WEB + "/",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(url, headers=headers, timeout=timeout, accept="application/json, text/plain, */*")
        raw = body.decode("utf-8", "replace")
        return json.loads(raw) if raw else None
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def request_text(url_or_path: str, timeout: int = 25) -> str:
    url = absolute_url(url_or_path)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} from {url}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def absolute_url(path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if path_or_url.startswith("//"):
        return "https:" + path_or_url
    if path_or_url.startswith("/"):
        return BASE_WEB + path_or_url
    return BASE_WEB + "/" + path_or_url.lstrip("/")


def slugish(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def resolve_region(region: str | None) -> tuple[str, str | None, str | None]:
    raw = (region or "new-zealand").strip()
    key = raw.lower().replace("_", " ").replace("-", " ")
    slug = REGION_ALIASES.get(key) or raw.strip("/").lower().replace(" ", "-")
    known_slugs = {r["slug"] for r in REGIONS}
    warning = None if slug in known_slugs else f"unknown region '{region}', passed through as '{slug}'"
    if "/" in slug:
        region_slug, subregion = slug.split("/", 1)
        return region_slug, subregion, warning
    return slug, None, warning


def resolve_category(category: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not category:
        return None, None
    raw = category.strip()
    needle = raw.lower().strip("/")
    tail = needle.split("/")[-1]
    for c in CATEGORIES:
        values = {str(c.get("id") or ""), c["slug"], c["name"].lower(), slugish(c["name"])}
        if needle in values or tail in values:
            return c, None
    return None, f"unknown category '{category}'"


def parse_money_text(value: Any) -> float | None:
    if value is None:
        return None
    m = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", str(value).replace(",", ""))
    return float(m.group(1)) if m else None


def parse_percent(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("%", "").strip() or 0)
    except Exception:
        return 0.0


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        amount = float(value)
    except Exception:
        return str(value)
    if amount.is_integer():
        return f"${int(amount)}"
    return f"${amount:.2f}"


def normal_price(price: float | None, saving: float | None) -> float | None:
    if price is None or saving is None or saving <= 0:
        return None
    return round(price + saving, 2)


def region_from_ref(ref: str) -> str | None:
    m = re.match(r"/things-to-do/([^/]+)/(?:activity|activities)/", ref or "")
    if m:
        return m.group(1)
    m = re.match(r"/restaurants/([^/]+)/", ref or "")
    return m.group(1) if m else None


def normalize_deal(item: dict[str, Any]) -> dict[str, Any]:
    price = item.get("price_raw")
    try:
        price = float(price) if price is not None else None
    except Exception:
        price = None
    saving_text = str(item.get("deal_saving") or "")
    saving = parse_money_text(saving_text) if saving_text.lower().startswith("save") else None
    percent = parse_percent(item.get("reduction_raw") if item.get("reduction_raw") is not None else item.get("deal_reduction"))
    ref = item.get("activity_ref") or item.get("href")
    url = absolute_url(ref)
    deal_id = item.get("deal_id")
    classification = "Dining" if str(ref or "").startswith("/restaurants/") else "Activities"
    out = {
        "id": deal_id,
        "title": html.unescape(str(item.get("deal_name") or "")).strip(),
        "classification": classification,
        "region": region_from_ref(str(ref or "")),
        "price": price,
        "price_display": money(price) if price is not None else item.get("deal_price"),
        "normal_price": normal_price(price, saving),
        "saving": saving,
        "saving_display": item.get("deal_saving"),
        "discount_percent": percent,
        "has_price_reduction": bool(percent > 0),
        "coupon": bool(item.get("coupon")),
        "sold_out": bool(item.get("soldOut") or item.get("deal_sold_out")),
        "spaces": item.get("deal_spaces"),
        "date_from": item.get("deal_date_from"),
        "date_to": item.get("deal_date_to"),
        "rating": item.get("review_rating"),
        "review_count": item.get("review_count"),
        "image": absolute_url(item.get("img")),
        "url": url,
        "source": "Bookme",
    }
    return out


def has_real_discount(deal: dict[str, Any]) -> bool:
    return bool(deal.get("discount_percent") and float(deal["discount_percent"]) > 0)


def build_deal_params(
    region: str,
    subregion: str | None,
    *,
    classification: str = "Activities",
    sort: str = "featured",
    begin: int = 0,
    end: int = 25,
    category: dict[str, Any] | None = None,
    require_deals: bool = True,
    subclassification: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "region": region,
        "begin": begin,
        "end": end,
        "filter": sort,
        "classification": classification,
        "requiredeals": str(bool(require_deals)).lower(),
    }
    if subregion:
        params["subregion"] = subregion
    if classification == "Activities" and category and category.get("id"):
        params["activityTypeDetails"] = category["id"]
    if classification == "Dining":
        params["subclassification"] = subclassification or "dinner"
        params["restaurantDate"] = ""
        params["restaurantDateYear"] = "2026"
    return params


def fetch_deal_page(
    region: str,
    subregion: str | None,
    *,
    classification: str,
    category: dict[str, Any] | None,
    sort: str,
    limit: int,
    require_deals: bool = True,
    subclassification: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    deals: list[dict[str, Any]] = []
    begin = 0
    # The browser starts at end=25 and then appends 20-row windows. Larger
    # category windows can return 405, so keep the public payload shape exact.
    page_size = 25
    list_complete = False
    for _ in range(6):
        params = build_deal_params(
            region,
            subregion,
            classification=classification,
            sort=sort,
            begin=begin,
            end=begin + page_size,
            category=category,
            require_deals=require_deals,
            subclassification=subclassification,
        )
        payload = request_json(CONTEXT + "/json/home/getdeals", params)
        batch = [normalize_deal(x) for x in (payload or {}).get("deals", []) if isinstance(x, dict)]
        deals.extend(batch)
        list_complete = bool((payload or {}).get("list_complete"))
        if list_complete or len(deals) >= limit:
            break
        begin += page_size
    return deals, list_complete


def fetch_deals(
    region_input: str | None,
    *,
    category: dict[str, Any] | None = None,
    sort: str = "discount",
    limit: int = 10,
    require_deals: bool = True,
) -> dict[str, Any]:
    region, subregion, region_warning = resolve_region(region_input)
    started = time.perf_counter()
    warnings = [w for w in [region_warning] if w]
    if region_warning:
        return {
            "region": region_input,
            "resolved_region": region + (f"/{subregion}" if subregion else ""),
            "category": category.get("slug") if category else None,
            "sort": sort,
            "count": 0,
            "elapsed_ms": 0,
            "warnings": warnings,
            "list_complete": True,
            "deals": [],
        }
    if category and category.get("classification") == "Dining":
        subclassifications = [category["subclassification"]] if category.get("subclassification") else DINING_SUBCLASSIFICATIONS
        all_deals: list[dict[str, Any]] = []
        complete = True
        for subclass in subclassifications:
            batch, done = fetch_deal_page(
                region,
                subregion,
                classification="Dining",
                category=None,
                sort=sort,
                limit=limit,
                require_deals=require_deals,
                subclassification=subclass,
            )
            all_deals.extend(batch)
            complete = complete and done
    else:
        classification = "Activities"
        all_deals, complete = fetch_deal_page(
            region,
            subregion,
            classification=classification,
            category=category,
            sort=sort,
            limit=limit,
            require_deals=require_deals,
        )
    deals = [d for d in all_deals if has_real_discount(d)] if require_deals else all_deals
    deals = unique_deals(deals)
    deals = sort_deals_client(deals, sort)[: max(0, limit)]
    return {
        "region": region_input or "new-zealand",
        "resolved_region": region + (f"/{subregion}" if subregion else ""),
        "category": category.get("slug") if category else None,
        "sort": sort,
        "count": len(deals),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "warnings": warnings,
        "list_complete": complete,
        "deals": deals,
    }


def unique_deals(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for deal in deals:
        key = deal.get("id") or deal.get("url")
        if key in seen:
            continue
        seen.add(key)
        out.append(deal)
    return out


def sort_deals_client(deals: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    if sort == "low":
        return sorted(deals, key=lambda d: (d.get("price") is None, d.get("price") or 10**12))
    if sort == "high":
        return sorted(deals, key=lambda d: (d.get("price") or -1), reverse=True)
    if sort == "discount":
        return sorted(deals, key=lambda d: (d.get("discount_percent") or 0, d.get("saving") or 0), reverse=True)
    return deals


def search_deals(args: argparse.Namespace) -> dict[str, Any]:
    category, warning = resolve_category(args.category)
    region, subregion, region_warning = resolve_region(args.region)
    started = time.perf_counter()
    warnings = [w for w in [warning, region_warning] if w]
    if warning or region_warning:
        return {
            "query": args.query,
            "region": args.region,
            "category": args.category,
            "count": 0,
            "elapsed_ms": 0,
            "warnings": warnings,
            "deals": [],
        }
    if category and category.get("query_hint"):
        args.query = (args.query + " " + category["query_hint"]).strip()
        category = None
    if category:
        data = fetch_deals(args.region, category=category, sort=args.sort, limit=max(args.limit * 4, 25), require_deals=True)
        needle = args.query.lower()
        deals = [d for d in data["deals"] if needle in (d.get("title") or "").lower()]
        data.update({"query": args.query, "count": len(deals[: args.limit]), "deals": deals[: args.limit]})
        return data
    path = f"{CONTEXT}/json/{urllib.parse.quote(region)}"
    if subregion:
        path += f"/{urllib.parse.quote(subregion)}"
    path += f"/activities-text-search/{urllib.parse.quote(args.query)}/hot-deals"
    payload = request_json(path)
    raw = (payload or {}).get("deals") or (payload or {}).get("results") or []
    deals = [normalize_deal(x) for x in raw if isinstance(x, dict)]
    deals = [d for d in unique_deals(deals) if has_real_discount(d)]
    deals = sort_deals_client(deals, args.sort)[: args.limit]
    return {
        "query": args.query,
        "region": args.region or "new-zealand",
        "resolved_region": region + (f"/{subregion}" if subregion else ""),
        "category": None,
        "sort": args.sort,
        "count": len(deals),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "warnings": warnings,
        "deals": deals,
    }


def extract_schema(html_text: str) -> dict[str, Any]:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html_text, flags=re.S | re.I):
        raw = html.unescape(m.group(1)).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def extract_operator(html_text: str) -> dict[str, Any] | None:
    m = re.search(r'<div class="allProducts">\s*<a href="([^"]+)">More from ([^<]+)', html_text, flags=re.S)
    if not m:
        return None
    return {"name": html.unescape(m.group(2)).strip(), "url": absolute_url(m.group(1))}


def extract_price_options(html_text: str) -> list[dict[str, Any]]:
    labels: dict[int, dict[str, Any]] = {}
    for m in re.finditer(r"window\.productPricePoints\.push\(\{(.*?)\}\)", html_text, flags=re.S):
        block = m.group(1)
        pid = int_match(block, r"'productPriceId':\s*([0-9]+)")
        if pid is None:
            continue
        labels[pid] = {
            "product_price_id": pid,
            "label": str_match(block, r"'priceLabel':\s*\"([^\"]*)\""),
            "description": str_match(block, r"'description':\s*\"([^\"]*)\""),
            "normal_price": float_match(block, r"'fullPrice':\s*([0-9.]+)"),
        }
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"window\.possiblePrices\.push\(\{(.*?)\}\)", html_text, flags=re.S):
        block = m.group(1)
        pid = int_match(block, r"'productPriceId':\s*([0-9]+)")
        if pid is None:
            continue
        base = labels.get(pid, {"product_price_id": pid})
        price = float_match(block, r"'price':\s*([0-9.]+)")
        normal = base.get("normal_price")
        allocation = int_match(block, r"'allocation':\s*([0-9]+)")
        discount = round((normal - price) / normal * 100, 1) if normal and price is not None and normal > 0 and price < normal else 0.0
        out.append(
            {
                "product_price_id": pid,
                "label": base.get("label"),
                "description": base.get("description"),
                "price": price,
                "normal_price": normal,
                "saving": round(normal - price, 2) if normal and price is not None and normal > price else None,
                "discount_percent": discount,
                "allocation": allocation,
                "price_display": str_match(block, r"'priceDisplay':\s*'([^']*)'"),
            }
        )
    deduped: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for option in out:
        key = (option.get("product_price_id"), option.get("price"))
        existing = by_key.get(key)
        if existing:
            existing["allocation"] = max(existing.get("allocation") or 0, option.get("allocation") or 0)
        else:
            by_key[key] = option
    deduped.extend(by_key.values())
    return deduped


def int_match(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def float_match(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def str_match(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, flags=re.S)
    return html.unescape(m.group(1)).strip() if m else None


def best_price_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    available = [o for o in options if (o.get("allocation") or 0) > 0 and o.get("price") is not None and o.get("price") > 0]
    discounted = [o for o in available if o.get("discount_percent") and o["discount_percent"] > 0]
    pool = discounted or available
    return min(pool, key=lambda o: o.get("price") or 10**12) if pool else None


def find_deal_reference(target: str, region: str | None = None) -> dict[str, Any] | None:
    needle = target.lower().strip()
    regions = [region] if region else ["new-zealand"] + [r["slug"] for r in REGIONS if r["slug"] != "new-zealand"]
    sorts = ["featured", "discount", "low"]
    for region_slug in regions:
        for sort in sorts:
            data = fetch_deals(region_slug, sort=sort, limit=120, require_deals=False)
            for deal in data.get("deals", []):
                url = str(deal.get("url") or "").lower()
                deal_id = str(deal.get("id") or "").lower()
                title_slug = slugish(str(deal.get("title") or ""))
                if needle == deal_id or needle in url or needle == title_slug or needle in title_slug:
                    return deal
    return None


def detail_for_target(target: str, region: str | None = None) -> dict[str, Any]:
    hint: dict[str, Any] | None = None
    if target.startswith("http") or target.startswith("/") or "/activity/" in target or "/restaurants/" in target:
        url = absolute_url(target)
    else:
        hint = find_deal_reference(target, region)
        if not hint:
            die(f"could not find deal '{target}' in current public deal lists")
        url = hint.get("url")
    html_text = request_text(str(url))
    schema = extract_schema(html_text)
    options = extract_price_options(html_text)
    best = best_price_option(options)
    operator = extract_operator(html_text)
    deal_id = schema.get("sku") or schema.get("sku ") or (hint or {}).get("id")
    if not deal_id:
        m = re.search(r"/([0-9]+)(?:/)?$", str(url))
        deal_id = m.group(1) if m else None
    price = best.get("price") if best else (hint or {}).get("price")
    normal = best.get("normal_price") if best else (hint or {}).get("normal_price")
    saving = best.get("saving") if best else (hint or {}).get("saving")
    discount = best.get("discount_percent") if best else (hint or {}).get("discount_percent")
    detail = {
        "id": deal_id,
        "title": schema.get("name") or (hint or {}).get("title"),
        "operator": operator,
        "description": schema.get("description"),
        "url": str(url),
        "image": schema.get("image") or (hint or {}).get("image"),
        "price": price,
        "normal_price": normal,
        "saving": saving,
        "discount_percent": discount,
        "availability": ((schema.get("offers") or {}).get("availability") if isinstance(schema.get("offers"), dict) else None),
        "availability_hint": availability_hint(best, hint),
        "rating": ((schema.get("aggregateRating") or {}).get("ratingValue") if isinstance(schema.get("aggregateRating"), dict) else (hint or {}).get("rating")),
        "review_count": ((schema.get("aggregateRating") or {}).get("reviewCount") if isinstance(schema.get("aggregateRating"), dict) else (hint or {}).get("review_count")),
        "price_options": sorted(
            [o for o in options if o.get("discount_percent") and o["discount_percent"] > 0],
            key=lambda o: o.get("price") or 10**12,
        )[:10],
        "source": "Bookme",
    }
    return detail


def availability_hint(best: dict[str, Any] | None, hint: dict[str, Any] | None) -> str | None:
    if best and best.get("allocation") is not None:
        return f"{best.get('allocation')} slots at selected lowest discounted price"
    if hint and (hint.get("date_from") or hint.get("date_to") or hint.get("spaces")):
        dates = " to ".join(str(x) for x in [hint.get("date_from"), hint.get("date_to")] if x)
        spaces = f"{hint.get('spaces')} spaces" if hint.get("spaces") else None
        return " | ".join(x for x in [dates, spaces] if x)
    return None


def cmd_search(args: argparse.Namespace) -> None:
    emit(search_deals(args), args.json)


def cmd_deals(args: argparse.Namespace) -> None:
    category, warning = resolve_category(args.category)
    if warning:
        data = {"region": args.region, "category": args.category, "sort": args.sort, "count": 0, "warnings": [warning], "deals": []}
    elif category and category.get("query_hint"):
        data = search_deals(argparse.Namespace(query=category["query_hint"], region=args.region, category=None, sort=args.sort, limit=args.limit))
        data["category"] = category["slug"]
    else:
        data = fetch_deals(args.region, category=category, sort=args.sort, limit=args.limit, require_deals=True)
    emit(data, args.json)


def cmd_cheapest(args: argparse.Namespace) -> None:
    category, warning = resolve_category(args.category)
    if warning:
        data = {"region": args.region, "category": args.category, "sort": "low", "count": 0, "warnings": [warning], "deals": []}
    elif category and category.get("query_hint"):
        data = search_deals(argparse.Namespace(query=category["query_hint"], region=args.region, category=None, sort="low", limit=args.limit))
        data["category"] = category["slug"]
    else:
        data = fetch_deals(args.region, category=category, sort="low", limit=args.limit, require_deals=True)
    emit(data, args.json)


def cmd_hot(args: argparse.Namespace) -> None:
    data = fetch_deals(args.region, sort="featured", limit=args.limit, require_deals=True)
    emit(data, args.json)


def cmd_deal(args: argparse.Namespace) -> None:
    emit({"deal": detail_for_target(args.target, args.region)}, args.json)


def cmd_regions(args: argparse.Namespace) -> None:
    rows = [{"slug": r["slug"], "name": r["name"]} for r in REGIONS]
    emit({"count": len(rows), "regions": rows}, args.json)


def cmd_categories(args: argparse.Namespace) -> None:
    rows = CATEGORIES
    if args.query:
        q = args.query.lower()
        rows = [c for c in rows if q in (c["slug"] + " " + c["name"] + " " + c["classification"]).lower()]
    emit({"count": len(rows), "categories": rows[: args.limit]}, args.json)


def price_line(deal: dict[str, Any]) -> str:
    bits = [money(deal.get("price"))]
    normal = deal.get("normal_price")
    if normal:
        bits.append(f"was {money(normal)}")
    if deal.get("discount_percent"):
        pct = float(deal["discount_percent"])
        bits.append(f"{pct:g}% off")
    if deal.get("saving"):
        bits.append(f"save {money(deal.get('saving'))}")
    if deal.get("coupon"):
        bits.append("coupon")
    return " (" + ", ".join(bits[1:]) + ")" if len(bits) > 1 else bits[0]


def print_deals(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("category") or data.get("sort") or "deals"
    print(f"Bookme {label}: {data.get('count', 0)} deals ({data.get('elapsed_ms', 0)} ms)")
    if data.get("resolved_region"):
        print(f"Region: {data.get('resolved_region')}")
    for warning in data.get("warnings") or []:
        print(f"Warning: {warning}")
    print()
    for deal in data.get("deals") or []:
        dates = " to ".join(str(x) for x in [deal.get("date_from"), deal.get("date_to")] if x)
        availability = " | ".join(str(x) for x in [dates, f"{deal.get('spaces')} spaces" if deal.get("spaces") else None] if x)
        print(f"{deal.get('id')}  {deal.get('title')}")
        print(f"  {price_line(deal)}" + (f" | {availability}" if availability else ""))
        if deal.get("rating"):
            print(f"  rating {deal.get('rating')} from {deal.get('review_count') or 0} reviews")
        if deal.get("url"):
            print(f"  {deal.get('url')}")
        print()


def print_detail(data: dict[str, Any]) -> None:
    deal = data.get("deal") or {}
    print(f"{deal.get('id')}  {deal.get('title')}")
    if deal.get("operator"):
        print(f"Operator: {deal['operator'].get('name')}")
    print(f"Price: {price_line(deal)}")
    if deal.get("availability_hint"):
        print(f"Availability: {deal.get('availability_hint')}")
    if deal.get("rating"):
        print(f"Rating: {deal.get('rating')} from {deal.get('review_count') or 0} reviews")
    if deal.get("url"):
        print(deal["url"])


def print_generic(data: dict[str, Any]) -> None:
    if "deal" in data:
        print_detail(data)
    elif "regions" in data:
        for r in data["regions"]:
            print(f"{r['slug']:<42} {r['name']}")
    elif "categories" in data:
        for c in data["categories"]:
            ident = c.get("id") if c.get("id") is not None else "-"
            print(f"{str(ident):>4}  {c['slug']:<42} {c['classification']:<10} {c['name']}")
    elif "deals" in data:
        print_deals(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_generic(data)


def add_common_deal_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--region", help="Bookme region slug/name, e.g. auckland, queenstown, wellington")
    sp.add_argument("--category", help="category slug/name/id, e.g. jet-boating, dinner, restaurants")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Bookme NZ public read-only deals CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search Bookme deals by keyword")
    sp.add_argument("query")
    add_common_deal_flags(sp)
    sp.add_argument("--sort", choices=["featured", "discount", "low", "high"], default="discount")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("deals", help="list current discounted deals")
    add_common_deal_flags(sp)
    sp.add_argument("--sort", choices=["featured", "discount", "low", "high"], default="discount")
    sp.set_defaults(func=cmd_deals)

    sp = sub.add_parser("cheapest", help="list cheapest current discounted deals")
    add_common_deal_flags(sp)
    sp.set_defaults(func=cmd_cheapest)

    sp = sub.add_parser("hot", help="list featured/hot discounted deals")
    sp.add_argument("--region", help="Bookme region slug/name, e.g. auckland, queenstown, wellington")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_hot)

    sp = sub.add_parser("deal", help="fetch one deal detail page")
    sp.add_argument("target", help="deal id, slug, path, or full Bookme URL")
    sp.add_argument("--region", help="optional region hint for id/slug lookup")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_deal)

    sp = sub.add_parser("regions", help="list supported Bookme NZ regions")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_regions)

    sp = sub.add_parser("categories", help="list/search supported Bookme deal categories")
    sp.add_argument("--query", help="filter category names/slugs")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
