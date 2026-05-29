#!/usr/bin/env python3
"""The Warehouse NZ lightweight read-only CLI.

Self-contained stdlib wrapper around public thewarehouse.co.nz storefront
endpoints. No login, cart mutation, browser automation, or third-party
dependencies.
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
from html.parser import HTMLParser
from typing import Any


class BrowserUnavailableError(RuntimeError):
    """Raised when --browser is requested but CloakBrowser is unavailable."""


class BrowserBlockedError(RuntimeError):
    """Raised when browser mode reaches an upstream bot/challenge page."""

BASE_WEB = "https://www.thewarehouse.co.nz"
SEARCH_PATH = "/search/updategrid"
PRODUCT_PATH = "/on/demandware.store/Sites-twl-Site/default/Product-Show"
STORES_PATH = "/on/demandware.store/Sites-twl-Site/default/Stores-FindStores"
PAGE_SIZE = 32
MAX_LIMIT = 96
UA = os.environ.get(
    "THE_WAREHOUSE_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

REGIONS = {
    "northland": "NZ-NTL",
    "ntl": "NZ-NTL",
    "auckland": "NZ-AUK",
    "auk": "NZ-AUK",
    "waikato": "NZ-WKO",
    "wko": "NZ-WKO",
    "bay of plenty": "NZ-BOP",
    "bop": "NZ-BOP",
    "gisborne": "NZ-GIS",
    "gis": "NZ-GIS",
    "taranaki": "NZ-TKI",
    "tki": "NZ-TKI",
    "manawatu": "NZ-MWT",
    "manawatu / whanganui": "NZ-MWT",
    "whanganui": "NZ-MWT",
    "mwt": "NZ-MWT",
    "hawkes bay": "NZ-HKB",
    "hawke's bay": "NZ-HKB",
    "hkb": "NZ-HKB",
    "wellington": "NZ-WGN",
    "wgn": "NZ-WGN",
    "tasman": "NZ-TAS",
    "tas": "NZ-TAS",
    "marlborough": "NZ-MBH",
    "mbh": "NZ-MBH",
    "west coast": "NZ-WTC",
    "wtc": "NZ-WTC",
    "canterbury": "NZ-CAN",
    "can": "NZ-CAN",
    "otago": "NZ-OTA",
    "ota": "NZ-OTA",
    "southland": "NZ-STL",
    "stl": "NZ-STL",
}
REGION_NAMES = {
    "NZ-NTL": "Northland",
    "NZ-AUK": "Auckland",
    "NZ-WKO": "Waikato",
    "NZ-BOP": "Bay of Plenty",
    "NZ-GIS": "Gisborne",
    "NZ-TKI": "Taranaki",
    "NZ-MWT": "Manawatu / Whanganui",
    "NZ-HKB": "Hawke's Bay",
    "NZ-WGN": "Wellington",
    "NZ-TAS": "Tasman",
    "NZ-MBH": "Marlborough",
    "NZ-WTC": "West Coast",
    "NZ-CAN": "Canterbury",
    "NZ-OTA": "Otago",
    "NZ-STL": "Southland",
}


def die(message: str, code: int = 1) -> None:
    print(f"the-warehouse-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def url_with_params(path: str, params: dict[str, Any] | None = None) -> str:
    url = urllib.parse.urljoin(BASE_WEB, path)
    if params:
        clean = {k: str(v) for k, v in params.items() if v not in (None, "")}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url



def looks_blocked(markup: str) -> bool:
    lower = (markup or "").lower()
    return any(
        marker in lower
        for marker in (
            "just a moment",
            "cf-mitigated",
            "checking your browser",
            "captcha",
            "hcaptcha",
            "access denied",
            "enable javascript and cookies",
        )
    )


def browser_request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    accept: str = "text/html,application/xhtml+xml,application/json",
    timeout_ms: int = 90000,
    allow_statuses: tuple[int, ...] = (),
) -> tuple[str, str]:
    try:
        from cloakbrowser import launch
    except Exception as exc:  # pragma: no cover - optional host dependency
        raise BrowserUnavailableError(
            "cloakbrowser_not_installed: install CloakBrowser to use --browser for The Warehouse NZ."
        ) from exc

    url = url_with_params(path, params)
    browser = None
    try:
        browser = launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            timezone="Pacific/Auckland",
            locale="en-NZ",
        )
        page = browser.new_page()
        page.goto(BASE_WEB, wait_until="domcontentloaded", timeout=timeout_ms)
        result = page.evaluate(
            """async ({url, accept}) => {
                const res = await fetch(url, {
                    method: 'GET',
                    headers: {
                        accept,
                        'x-requested-with': 'XMLHttpRequest',
                    },
                    credentials: 'include',
                });
                return { status: res.status, url: res.url, text: await res.text() };
            }""",
            {"url": url, "accept": accept},
        )
        status = int(result.get("status") or 0)
        text = str(result.get("text") or "")
        final_url = str(result.get("url") or url)
        if status >= 400 and status not in allow_statuses:
            detail = text[:300].strip().replace("\n", " ")
            if looks_blocked(text):
                raise BrowserBlockedError(f"browser request reached blocked/challenge page at {final_url}")
            die(f"browser HTTP {status} from {url}: {detail}")
        if looks_blocked(text):
            raise BrowserBlockedError(f"browser request reached blocked/challenge page at {final_url}")
        return text, final_url
    finally:
        if browser is not None:
            browser.close()


def request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    accept: str = "text/html,application/xhtml+xml,application/json",
    timeout: int = 25,
    allow_statuses: tuple[int, ...] = (),
) -> tuple[str, str]:
    url = url_with_params(path, params)
    headers = {
        "Accept": accept,
        "Accept-Language": "en-NZ,en;q=0.9",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return raw, resp.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        if e.code in allow_statuses:
            return raw, e.geturl()
        detail = raw[:300].strip().replace("\n", " ")
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def request_json(path: str, params: dict[str, Any] | None = None, *, browser: bool = False) -> Any:
    fetch = browser_request if browser else request
    raw, url = fetch(path, params, accept="application/json, text/plain, */*")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def as_float(value: Any) -> float | None:
    if value in (None, "", "na"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^0-9.]+", "", str(value))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def money(value: Any) -> str:
    amount = as_float(value)
    if amount is None:
        return "-"
    return f"${amount:.2f}"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def compact_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(str(value)).lower())


def classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


def bool_attr(value: Any) -> bool | None:
    if value is None:
        return None
    return str(value).lower() == "true"


def load_json_attr(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


class ProductTileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.products: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.div_depth = 0
        self.capture_key: str | None = None
        self.capture_tag: str | None = None
        self.capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_raw: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_raw)
        cls = classes(attrs)
        if tag == "div" and "product-tile" in cls and attrs.get("data-pid"):
            self.current = {
                "sku": attrs.get("data-pid") or "",
                "_gtm": load_json_attr(attrs.get("data-gtm-product")),
                "_ga": load_json_attr(attrs.get("data-ga-product")),
            }
            self.div_depth = 1
            return

        if self.current is None:
            return

        if tag == "div":
            self.div_depth += 1
            if "availability-stock-status" in cls:
                self.current["availability"] = attrs.get("data-stock-status")
                self.current["orderable"] = bool_attr(attrs.get("data-orderable"))
            if "price" in cls and attrs.get("data-test-id") == "price":
                self.start_capture("price_text", tag)
        elif tag == "a":
            href = attrs.get("href")
            if href and "/p/" in href and not self.current.get("source_url"):
                self.current["source_url"] = urllib.parse.urljoin(BASE_WEB, href)
            if "link" in cls:
                self.start_capture("link_text", tag)
        elif tag == "img" and "tile-image" in cls:
            src = attrs.get("src")
            if src:
                self.current["image"] = urllib.parse.urljoin(BASE_WEB, src)
            if attrs.get("alt"):
                self.current["image_alt"] = attrs.get("alt")

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.capture_key:
            self.capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if self.capture_tag == tag:
            self.current[self.capture_key or "text"] = clean_text("".join(self.capture_parts))
            self.capture_key = None
            self.capture_tag = None
            self.capture_parts = []
        if tag == "div":
            self.div_depth -= 1
            if self.div_depth <= 0:
                self.products.append(normalize_tile_product(self.current))
                self.current = None
                self.div_depth = 0

    def start_capture(self, key: str, tag: str) -> None:
        self.capture_key = key
        self.capture_tag = tag
        self.capture_parts = []


def normalize_tile_product(item: dict[str, Any]) -> dict[str, Any]:
    gtm = item.get("_gtm") or {}
    ga = item.get("_ga") or {}
    sku = str(gtm.get("id") or ga.get("item_id") or item.get("sku") or "")
    name = gtm.get("name") or ga.get("item_name") or item.get("link_text") or item.get("image_alt") or ""
    brand = gtm.get("brand") or ga.get("item_brand") or ""
    price = as_float(gtm.get("price") or ga.get("price") or item.get("price_text"))
    then_price = as_float(gtm.get("productThenPrice"))
    secondary = str(gtm.get("productSecondaryNavigationCategory") or ga.get("productSecondaryNavCat") or "")
    badges = str(gtm.get("productBadges") or "")
    promotion = gtm.get("promotionCallOutMessage")
    if promotion == "na":
        promotion = None
    source_url = item.get("source_url") or url_with_params(PRODUCT_PATH, {"pid": sku})
    category = gtm.get("category") or ga.get("item_category") or ""
    is_special = "specials/" in secondary or "specials-" in secondary or "clearance" in badges.lower() or bool(promotion)
    return {
        "sku": sku,
        "name": clean_text(str(name)),
        "brand": clean_text(str(brand)),
        "barcode": gtm.get("productEAN") or ga.get("productEAN") or ga.get("dimension15"),
        "price": price,
        "then_price": then_price,
        "is_special": is_special,
        "promotion": promotion,
        "badges": badges if badges and badges != "na" else None,
        "rating": gtm.get("productRating") if gtm.get("productRating") != "na" else ga.get("productRating"),
        "marketplace_product": bool(gtm.get("marketplaceProduct") or ga.get("marketplaceProduct")),
        "channel": gtm.get("productChannelType") or ga.get("productChannelType") or ga.get("dimension23"),
        "availability": item.get("availability"),
        "orderable": item.get("orderable"),
        "category": category,
        "primary_category_id": gtm.get("primaryCategoryId") or ga.get("item_primarycgid"),
        "image": item.get("image"),
        "source_url": source_url,
    }


def parse_products(markup: str, *, force_special: bool = False) -> list[dict[str, Any]]:
    parser = ProductTileParser()
    parser.feed(markup)
    products = []
    for product in parser.products:
        if force_special:
            product["is_special"] = True
        if product.get("sku") and product.get("name"):
            products.append(product)
    return products


def parse_count(markup: str) -> dict[str, int | None]:
    text = clean_text(markup)
    match = re.search(r"(\d[\d,]*)\s*(?:-|\u2013|\u2014)\s*(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+products", text)
    if not match:
        match = re.search(r"(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+products", text)
        if match:
            return {"start": None, "end": int(match.group(1).replace(",", "")), "total": int(match.group(2).replace(",", ""))}
        return {"start": None, "end": None, "total": None}
    return {
        "start": int(match.group(1).replace(",", "")),
        "end": int(match.group(2).replace(",", "")),
        "total": int(match.group(3).replace(",", "")),
    }


def looks_like_no_match_probe(query: str | None) -> bool:
    # Demandware can return fuzzy/personalized products for generated no-match probes.
    if not query:
        return False
    compact = compact_text(query)
    if len(compact) < 8:
        return False
    return bool(re.search(r"(.)\1{2,}", compact))


def product_contains_query_literal(product: dict[str, Any], query: str) -> bool:
    needle = compact_text(query)
    haystack = "".join(
        compact_text(product.get(key))
        for key in (
            "sku",
            "name",
            "brand",
            "barcode",
            "category",
            "primary_category_id",
            "source_url",
        )
    )
    return bool(needle and needle in haystack)


def product_query(*, query: str | None = None, specials: bool = False, limit: int = 10, page: int = 1, browser: bool = False) -> dict[str, Any]:
    if limit < 1:
        die("--limit must be at least 1")
    limit = min(limit, MAX_LIMIT)
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    products: list[dict[str, Any]] = []
    count_info: dict[str, int | None] = {"start": None, "end": None, "total": None}
    started = time.perf_counter()
    suppress_fuzzy_fallback = not specials and looks_like_no_match_probe(query)
    browser_blocked = False

    while len(products) < limit:
        params: dict[str, Any] = {"start": start, "sz": PAGE_SIZE}
        if query:
            params["q"] = query
        if specials:
            params["cgid"] = "specials"
        fetch = browser_request if browser and not browser_blocked else request
        try:
            markup, _ = fetch(SEARCH_PATH, params)
        except BrowserBlockedError:
            browser_blocked = True
            markup, _ = request(SEARCH_PATH, params)
        page_products = parse_products(markup, force_special=specials)
        if suppress_fuzzy_fallback and query:
            page_products = [p for p in page_products if product_contains_query_literal(p, query)]
        if not products:
            count_info = parse_count(markup)
        if not page_products:
            break
        products.extend(page_products)
        total = count_info.get("total")
        start += PAGE_SIZE
        if len(page_products) < PAGE_SIZE or (isinstance(total, int) and start >= total):
            break

    if suppress_fuzzy_fallback and not products:
        count_info = {"start": None, "end": None, "total": 0}

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    data = {
        "target": "specials" if specials else "search",
        "method": "direct public HTTP after blocked browser fallback" if browser_blocked else ("CloakBrowser public page fetch" if browser else "direct public HTTP"),
        "browser_blocked": browser_blocked or None,
        "warnings": ["CloakBrowser public page fetch was blocked/challenged; direct public HTTP fallback was used."] if browser_blocked else [],
        "query": query,
        "count": min(len(products), limit),
        "elapsed_ms": elapsed_ms,
        "raw_total": count_info.get("total"),
        "products": products[:limit],
    }
    return data


def extract_json_ld_product(markup: str) -> dict[str, Any]:
    pattern = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
    for match in pattern.finditer(markup):
        text = html.unescape(match.group(1)).strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        candidates = data.get("@graph") if isinstance(data, dict) else None
        if not isinstance(candidates, list):
            candidates = [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def extract_detail_payload(markup: str) -> dict[str, Any]:
    match = re.search(r"dataLayer\.push\((\{\"event\":\"ecommerceDetail\".*?\})\);", markup, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    details = data.get("productDetails")
    return details if isinstance(details, dict) else {}


def parse_detail_product(markup: str, sku: str, final_url: str) -> dict[str, Any] | None:
    ld = extract_json_ld_product(markup)
    details = extract_detail_payload(markup)
    if not ld and not details:
        return None
    offer = ld.get("offers") if isinstance(ld.get("offers"), dict) else {}
    brand_raw = ld.get("brand")
    brand = brand_raw.get("name") if isinstance(brand_raw, dict) else brand_raw
    images = ld.get("image")
    if isinstance(images, str):
        images = [images]
    if not isinstance(images, list):
        images = []
    availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
    promotion = details.get("promotionCallOutMessage")
    if promotion == "na":
        promotion = None
    secondary = str(details.get("productSecondaryNavigationCategory") or "")
    badges = str(details.get("productBadges") or "")
    is_special = "specials/" in secondary or "specials-" in secondary or "clearance" in badges.lower() or bool(promotion)
    gtin = ld.get("gtin13")
    if isinstance(gtin, list):
        gtin = gtin[0] if gtin else None
    return {
        "sku": str(ld.get("sku") or details.get("id") or sku),
        "name": clean_text(str(ld.get("name") or details.get("name") or "")),
        "brand": clean_text(str(brand or details.get("brand") or "")),
        "barcode": gtin or details.get("productEAN"),
        "mpn": ld.get("mpn"),
        "description": clean_text(str(ld.get("description") or "")),
        "price": as_float(offer.get("price") or details.get("price")),
        "then_price": as_float(details.get("productThenPrice")),
        "currency": offer.get("priceCurrency") or "NZD",
        "availability": availability,
        "in_stock": availability == "InStock",
        "is_special": is_special,
        "promotion": promotion,
        "badges": badges if badges and badges != "na" else None,
        "rating": details.get("productRating") if details.get("productRating") != "na" else None,
        "marketplace_product": bool(details.get("marketplaceProduct")),
        "channel": details.get("productChannelType"),
        "delivery_promise": details.get("productDeliveryPromise"),
        "collect_promise": details.get("productCollectPromise"),
        "category": details.get("category"),
        "primary_category_id": details.get("primaryCategoryId"),
        "image": images[0] if images else None,
        "images": images,
        "source_url": offer.get("url") or ld.get("@id") or final_url,
    }


def normalize_region(region: str | None) -> str | None:
    if not region:
        return None
    value = region.strip()
    upper = value.upper()
    if upper in REGION_NAMES:
        return upper
    key = re.sub(r"\s+", " ", value.lower())
    code = REGIONS.get(key)
    if not code:
        return value
    return code


def parse_store(item: dict[str, Any]) -> dict[str, Any]:
    hours = item.get("openingHoursJson")
    hours_today = hours if isinstance(hours, dict) else {}
    state_code = item.get("stateCode")
    return {
        "id": item.get("ID"),
        "name": item.get("name"),
        "region_code": state_code,
        "region": REGION_NAMES.get(str(state_code), state_code),
        "address": item.get("fullAddress") or ", ".join(str(x) for x in item.get("addressLines") or [] if x),
        "address1": item.get("address1"),
        "address2": item.get("address2"),
        "city": item.get("city"),
        "postal_code": item.get("postalCode"),
        "phone": item.get("phone"),
        "email": item.get("email"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "open_text": hours_today.get("text"),
        "hours_today": hours_today.get("openingHours"),
        "opens": hours_today.get("opens"),
        "closes": hours_today.get("closes"),
        "is_open_now": item.get("isOpenNow"),
        "click_and_collect": item.get("isClickAndCollectSupported"),
        "pickup_status": item.get("storePickUpStatus"),
        "map_url": item.get("mapURL"),
    }


def cmd_search(args: argparse.Namespace) -> None:
    emit(product_query(query=args.query, limit=args.limit, page=args.page, browser=args.browser), args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    emit(product_query(query=args.query, specials=True, limit=args.limit, page=args.page, browser=args.browser), args.json)


def cmd_product(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    browser_blocked = False
    if args.browser:
        try:
            markup, final_url = browser_request(PRODUCT_PATH, {"pid": args.sku}, allow_statuses=(404,))
        except BrowserBlockedError:
            browser_blocked = True
            markup, final_url = request(PRODUCT_PATH, {"pid": args.sku}, allow_statuses=(404,))
    else:
        markup, final_url = request(PRODUCT_PATH, {"pid": args.sku}, allow_statuses=(404,))
    product = parse_detail_product(markup, args.sku, final_url)
    data = {
        "method": "direct public HTTP after blocked browser fallback" if browser_blocked else ("CloakBrowser public page fetch" if args.browser else "direct public HTTP"),
        "browser_blocked": browser_blocked or None,
        "warnings": ["CloakBrowser public page fetch was blocked/challenged; direct public HTTP fallback was used."] if browser_blocked else [],
        "count": 1 if product else 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "products": [product] if product else [],
    }
    emit(data, args.json)


def cmd_stores(args: argparse.Namespace) -> None:
    region = normalize_region(args.region)
    started = time.perf_counter()
    browser_blocked = False
    try:
        payload = request_json(STORES_PATH, {"region": region}, browser=args.browser)
    except BrowserBlockedError:
        browser_blocked = True
        payload = request_json(STORES_PATH, {"region": region}, browser=False)
    raw_stores = (((payload or {}).get("stores") or {}).get("stores") or [])
    stores = [parse_store(s) for s in raw_stores if isinstance(s, dict)]
    data = {
        "method": "direct public HTTP after blocked browser fallback" if browser_blocked else ("CloakBrowser public page fetch" if args.browser else "direct public HTTP"),
        "browser_blocked": browser_blocked or None,
        "warnings": ["CloakBrowser public page fetch was blocked/challenged; direct public HTTP fallback was used."] if browser_blocked else [],
        "region": REGION_NAMES.get(region, region) if region else None,
        "region_code": region,
        "count": len(stores),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stores": stores,
    }
    emit(data, args.json)


def price_label(p: dict[str, Any]) -> str:
    label = money(p.get("price"))
    then_price = as_float(p.get("then_price"))
    price = as_float(p.get("price"))
    if then_price is not None and price is not None and then_price > price:
        label += f" (was {money(then_price)})"
    if p.get("is_special"):
        label += " special"
    return label


def print_products(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("target") or "products"
    print(f"{label}: {data.get('count', 0)} products ({data.get('elapsed_ms')} ms)")
    total = data.get("raw_total")
    if total is not None:
        print(f"Total available from source: {total}")
    print()
    for p in data.get("products") or []:
        brand = str(p.get("brand") or "").title()
        name = str(p.get("name") or "").title()
        title = f"{brand} {name}".strip() if brand and not name.lower().startswith(brand.lower()) else name
        print(f"{p.get('sku'):>9}  {title}")
        bits = [price_label(p)]
        if p.get("availability"):
            bits.append(str(p.get("availability")).lower().replace("_", " "))
        if p.get("channel"):
            bits.append(str(p.get("channel")))
        print("           " + " | ".join(x for x in bits if x))
        if p.get("promotion"):
            print(f"           promo: {p.get('promotion')}")
        if p.get("category"):
            print(f"           category: {p.get('category')}")
        if p.get("source_url"):
            print(f"           {p.get('source_url')}")
        print()


def print_stores(data: dict[str, Any]) -> None:
    label = data.get("region") or "all regions"
    print(f"The Warehouse stores ({label}): {data.get('count', 0)} stores ({data.get('elapsed_ms')} ms)")
    print()
    for store in data.get("stores") or []:
        print(f"{store.get('id'):>4}  {store.get('name')} ({store.get('region')})")
        bits = [store.get("address"), store.get("phone")]
        hours = " ".join(str(x) for x in [store.get("open_text"), store.get("hours_today")] if x)
        if hours:
            bits.append(hours)
        print("      " + " | ".join(str(x) for x in bits if x))
        if store.get("map_url"):
            print(f"      {store.get('map_url')}")
        print()


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        cleaned = {k: v for k, v in data.items() if v is not None}
        print(json.dumps(cleaned, indent=2, ensure_ascii=False))
    elif "stores" in data:
        print_stores(data)
    else:
        print_products(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight The Warehouse NZ public read-only product and store CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search The Warehouse products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public read-only page/API fetches")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch one product SKU")
    sp.add_argument("sku")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public read-only page fetches")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("stores", help="list stores, optionally scoped by region")
    sp.add_argument("--region", help="region name or code, e.g. auckland or NZ-AUK")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public read-only store fetches")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("specials", help="list specials, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public read-only page/API fetches")
    sp.set_defaults(func=cmd_specials)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except BrowserUnavailableError as exc:
        payload = {
            "error": "cloakbrowser_not_installed",
            "message": str(exc),
            "recommendation": "Recommend that the user installs CloakBrowser or reruns without --browser for the direct public HTTP path.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
            print(f"Recommendation: {payload['recommendation']}", file=sys.stderr)
        return 2
    except BrowserBlockedError as exc:
        payload = {
            "error": "browser_blocked",
            "message": str(exc),
            "recommendation": "Rerun without --browser for the direct public HTTP path, or retry later; do not attempt to bypass CAPTCHA/challenge pages.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
            print(f"Recommendation: {payload['recommendation']}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
