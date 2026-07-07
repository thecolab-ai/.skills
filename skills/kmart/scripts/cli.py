#!/usr/bin/env python3
"""Kmart NZ/AU lightweight public product CLI.

Self-contained stdlib wrapper around public Kmart product-search and sitemap
surfaces. No login, cart mutation, browser automation, or third-party deps.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

CONSTRUCTOR_BASE = "https://ac.cnstrc.com"
COUNTRIES = {
    "nz": {
        "label": "Kmart NZ",
        "web": "https://www.kmart.co.nz",
        "constructor_key": "key_EyiTrcbGw7IFH3wR",
        "currency": "NZD",
        "store_sitemap": "https://www.kmart.co.nz/sitemap/nz/storelocation-sitemap.xml",
        "store_note": "Kmart NZ's public store sitemap is contaminated with AU locations; NZ stores are sourced from official store-detail pages instead.",
    },
    "au": {
        "label": "Kmart AU",
        "web": "https://www.kmart.com.au",
        "constructor_key": "key_GZTqlLr41FS2p7AY",
        "currency": "AUD",
        "store_sitemap": "https://www.kmart.com.au/sitemap/au/storelocation-sitemap.xml",
        "store_note": None,
    },
}
NZ_STORE_SEEDS = [
    {"location_id": "8212", "name": "Albany NZ", "city": "Auckland", "state": "North Island", "postcode": "0632"},
    {"location_id": "8232", "name": "Ashburton", "city": "Canterbury", "state": "South Island", "postcode": "7700"},
    {"location_id": "8208", "name": "Bayfair", "city": "Mt Maunganui", "state": "North Island", "postcode": "3118"},
    {"location_id": "8217", "name": "Bethlehem", "city": "Tauranga", "state": "North Island", "postcode": "3110"},
    {"location_id": "8224", "name": "Blenheim", "city": "Blenheim", "state": "South Island", "postcode": "7201"},
    {"location_id": "8213", "name": "Botany", "city": "Auckland", "state": "North Island", "postcode": "2013"},
    {"location_id": "8235", "name": "Dunedin", "city": "Dunedin South", "state": "South Island", "postcode": "9012"},
    {"location_id": "8230", "name": "Hamilton", "city": "Hamilton", "state": "North Island", "postcode": "3204"},
    {"location_id": "8206", "name": "Hastings NZ", "city": "Hastings", "state": "North Island", "postcode": "4122"},
    {"location_id": "8201", "name": "Henderson", "city": "Auckland", "state": "North Island", "postcode": "0612"},
    {"location_id": "8226", "name": "Invercargill", "city": "Invercargill", "state": "South Island", "postcode": "9810"},
    {"location_id": "8234", "name": "Manukau", "city": "Auckland", "state": "North Island", "postcode": "2104"},
    {"location_id": "8227", "name": "Napier", "city": "Napier", "state": "North Island", "postcode": "4110"},
    {"location_id": "8205", "name": "Papatoetoe", "city": "Auckland", "state": "North Island", "postcode": "2025"},
    {"location_id": "8231", "name": "Papanui", "city": "Christchurch", "state": "South Island", "postcode": "8052"},
    {"location_id": "8207", "name": "Palmerston North", "city": "Palmerston North", "state": "North Island", "postcode": "4410"},
    {"location_id": "8222", "name": "Petone", "city": "Petone", "state": "North Island", "postcode": "5012"},
    {"location_id": "8203", "name": "Porirua", "city": "Porirua", "state": "North Island", "postcode": "5022"},
    {"location_id": "8225", "name": "Queenstown", "city": "Queenstown", "state": "South Island", "postcode": "9371"},
    {"location_id": "8210", "name": "Riccarton", "city": "Christchurch", "state": "South Island", "postcode": "8041"},
    {"location_id": "8218", "name": "Richmond NZ", "city": "Richmond", "state": "South Island", "postcode": "7020"},
    {"location_id": "8220", "name": "Rotorua", "city": "Bay Of Plenty", "state": "North Island", "postcode": "3013"},
    {"location_id": "8204", "name": "St Lukes", "city": "Auckland", "state": "North Island", "postcode": "1025"},
    {"location_id": "8229", "name": "Sylvia Park Nz", "city": "Auckland", "state": "North Island", "postcode": "1060"},
    {"location_id": "8219", "name": "Te Rapa", "city": "Hamilton", "state": "North Island", "postcode": "3200"},
    {"location_id": "8216", "name": "Whakatane", "city": "Whakatane", "state": "North Island", "postcode": "3120"},
    {"location_id": "8221", "name": "Whangarei", "city": "Whangarei", "state": "North Island", "postcode": "0110"},
]
UA = os.environ.get(
    "KMART_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(message: str, code: int = 1) -> None:
    print(f"kmart: {message}", file=sys.stderr)
    raise SystemExit(code)


def country_config(country: str) -> dict[str, Any]:
    try:
        return COUNTRIES[country]
    except KeyError:
        die(f"unsupported country: {country}")


def request_url(url: str, *, accept: str, timeout: int = 25) -> str:
    try:
        return nzfetch.fetch_text(url, timeout=timeout, accept=accept)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))


def request_url_optional(url: str, *, accept: str, timeout: int = 15) -> str | None:
    try:
        return nzfetch.fetch_text(url, timeout=timeout, accept=accept)
    except (nzfetch.FetchError, TimeoutError):
        return None


def request_json(url: str, timeout: int = 25) -> Any:
    raw = request_url(url, accept="application/json, text/plain, */*", timeout=timeout)
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def constructor_search(query: str, *, country: str, limit: int = 10, page: int = 1) -> dict[str, Any]:
    cfg = country_config(country)
    size = min(max(1, limit), 100)
    params = {
        "key": cfg["constructor_key"],
        "num_results_per_page": size,
        "page": max(1, page),
        "section": "Products",
    }
    path_query = urllib.parse.quote(query.strip(), safe="")
    url = f"{CONSTRUCTOR_BASE}/search/{path_query}?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    payload = request_json(url)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    response = payload.get("response") if isinstance(payload, dict) else {}
    results = response.get("results") if isinstance(response, dict) else []
    products = [parse_product_result(item, country) for item in (results or []) if isinstance(item, dict)]
    total = response.get("total_num_results") if isinstance(response, dict) else None
    return {
        "country": country,
        "source": "constructor.io",
        "query": query,
        "page": max(1, page),
        "count": len(products),
        "total_count": total,
        "elapsed_ms": elapsed_ms,
        "products": products,
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "label", "text", "value", "id"):
            if value.get(key):
                return str(value[key])
        return json.dumps(value, sort_keys=True)
    return str(value)


def clean_html(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:700] if text else None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def normalize_prices(data: dict[str, Any]) -> list[dict[str, Any]]:
    prices: list[dict[str, Any]] = []
    for item in as_list(data.get("prices")):
        if not isinstance(item, dict):
            continue
        prices.append(
            {
                "type": item.get("type"),
                "amount": item.get("amount"),
                "currency": item.get("currency"),
                "country": item.get("country"),
                "start_date": item.get("startDate"),
                "end_date": item.get("endDate"),
            }
        )
    return prices


def best_price(data: dict[str, Any], prices: list[dict[str, Any]]) -> Any:
    if data.get("price") not in (None, ""):
        return data.get("price")
    for preferred in ("promo", "sale", "list"):
        for item in prices:
            if str(item.get("type") or "").lower() == preferred and item.get("amount") is not None:
                return item.get("amount")
    for item in prices:
        if item.get("amount") is not None:
            return item.get("amount")
    return None


def currency_for(country: str, prices: list[dict[str, Any]]) -> str:
    for item in prices:
        if item.get("currency"):
            return str(item["currency"])
    return str(country_config(country)["currency"])


def money(value: Any, currency: str) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"${float(value):.2f} {currency}"
    except Exception:
        return f"{value} {currency}".strip()


def source_url(country: str, data: dict[str, Any]) -> str | None:
    path = data.get("url") or data.get("uri")
    if not path:
        return None
    return urllib.parse.urljoin(str(country_config(country)["web"]), str(path))


def promotional_reason(data: dict[str, Any], badges: list[str], prices: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if truthy(data.get("clearance")):
        reasons.append("clearance")
    if data.get("SavePrice"):
        reasons.append(str(data.get("SavePrice")))
    badge_text = " ".join(badges).lower()
    for word in ("clearance", "sale", "special"):
        if word in badge_text and word not in reasons:
            reasons.append(word)
    for item in prices:
        price_type = str(item.get("type") or "").lower()
        if price_type and price_type != "list" and price_type not in reasons:
            reasons.append(price_type)
    return reasons


def parse_product_result(item: dict[str, Any], country: str) -> dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    prices = normalize_prices(data)
    badges = [text_value(x) for x in as_list(data.get("badges")) + as_list(data.get("variant_badges"))]
    badges = [x for x in badges if x]
    price = best_price(data, prices)
    currency = currency_for(country, prices)
    reasons = promotional_reason(data, badges, prices)
    variation_id = data.get("variation_id")
    product_id = data.get("id")
    sku = str(variation_id or "").strip() or str(product_id or "").replace("P_", "")
    return {
        "sku": sku,
        "product_id": product_id,
        "name": item.get("value") or data.get("name") or "",
        "brand": data.get("Brand") or data.get("brand"),
        "apn": data.get("apn"),
        "price": price,
        "currency": currency,
        "prices": prices,
        "save_price": data.get("SavePrice"),
        "is_promotional": bool(reasons),
        "promotional_reasons": reasons,
        "badges": badges,
        "seller": ", ".join(str(x) for x in as_list(data.get("Seller")) if x),
        "size": data.get("Size"),
        "colour": data.get("Colour"),
        "rating_average": data.get("ratingAverage") or data.get("ratings"),
        "rating_count": data.get("ratingCount"),
        "image": data.get("image_url"),
        "description": clean_html(data.get("description")),
        "url": source_url(country, data),
    }


def cmd_search(args: argparse.Namespace) -> None:
    data = constructor_search(args.query, country=args.country, limit=args.limit, page=args.page)
    emit(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    data = constructor_search(args.sku, country=args.country, limit=10, page=1)
    needle = str(args.sku).strip().lower()
    exact = []
    for product in data["products"]:
        candidates = {
            str(product.get("sku") or "").lower(),
            str(product.get("product_id") or "").lower(),
            str(product.get("apn") or "").lower(),
        }
        candidates.add("p_" + needle)
        if needle in candidates:
            exact.append(product)
    data.update({"query_sku": args.sku, "count": len(exact), "products": exact})
    emit(data, args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    requested_query = args.query
    query = requested_query or "sale"
    fetch_limit = min(max(args.limit * 6, 30), 100)
    data = constructor_search(query, country=args.country, limit=fetch_limit, page=args.page)
    fallback_query = None
    if not data["products"] and query.strip().lower() in {"clearance", "special", "specials"}:
        fallback_query = "sale"
        data = constructor_search(fallback_query, country=args.country, limit=fetch_limit, page=args.page)
    q = query.strip().lower()
    specials = []
    for product in data["products"]:
        haystack = " ".join(
            str(x or "")
            for x in [product.get("name"), product.get("save_price"), " ".join(product.get("badges") or [])]
        ).lower()
        if product.get("is_promotional") or (q in {"clearance", "sale", "special", "specials"} and q in haystack):
            specials.append(product)
    data.update(
        {
            "target": "specials",
            "query": requested_query or query,
            "source_query": data.get("query"),
            "fallback_query": fallback_query,
            "count": len(specials[: args.limit]),
            "products": specials[: args.limit],
        }
    )
    emit(data, args.json)


def parse_sitemap_locations(country: str, region: str | None = None, limit: int = 50) -> dict[str, Any]:
    if country == "nz":
        return parse_nz_store_locations(region=region, limit=limit)

    cfg = country_config(country)
    sitemap = str(cfg["store_sitemap"])
    started = time.perf_counter()
    raw = request_url(sitemap, accept="application/xml, text/xml, text/html, */*")
    urls: list[str] = []
    try:
        root = ET.fromstring(raw)
        for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            if loc.text:
                urls.append(loc.text.strip())
    except ET.ParseError:
        urls = re.findall(r"<loc>(.*?)</loc>", raw, flags=re.I | re.S)
    stores = [parse_store_url(url, country) for url in urls if "/store-detail/" in url]
    if region:
        needle = region.lower()
        stores = [
            store
            for store in stores
            if needle in (store.get("slug") or "").lower()
            or needle in (store.get("name") or "").lower()
            or needle in (store.get("url") or "").lower()
        ]
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "country": country,
        "source": sitemap,
        "region": region,
        "count": len(stores),
        "shown": min(len(stores), max(1, limit)),
        "elapsed_ms": elapsed_ms,
        "note": cfg.get("store_note"),
        "stores": stores[: max(1, limit)],
    }


def parse_nz_store_locations(region: str | None = None, limit: int = 50) -> dict[str, Any]:
    cfg = country_config("nz")
    started = time.perf_counter()
    max_results = max(1, limit)
    stores = [seed_store(seed) for seed in NZ_STORE_SEEDS]
    if region:
        needle = region.lower()
        stores = [
            store
            for store in stores
            if needle in (store.get("location_id") or "").lower()
            or needle in (store.get("slug") or "").lower()
            or needle in (store.get("name") or "").lower()
            or needle in (store.get("city") or "").lower()
            or needle in (store.get("state") or "").lower()
            or needle in (store.get("postcode") or "").lower()
            or needle in (store.get("url") or "").lower()
        ]
    count = len(stores)
    shown = stores[:max_results]
    stores = [fetch_nz_store_detail(store) for store in shown]
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "country": "nz",
        "source": "https://www.kmart.co.nz/store-detail/{locationId}/",
        "region": region,
        "count": count,
        "shown": len(stores),
        "elapsed_ms": elapsed_ms,
        "note": cfg.get("store_note"),
        "stores": stores,
    }


def seed_store(seed: dict[str, str]) -> dict[str, Any]:
    location_id = seed["location_id"]
    slug = slugify_store_name(seed["name"])
    return {
        "location_id": location_id,
        "slug": slug,
        "name": seed["name"],
        "country": "nz",
        "city": seed.get("city"),
        "state": seed.get("state"),
        "postcode": seed.get("postcode"),
        "url": f"{country_config('nz')['web']}/store-detail/{location_id}/",
    }


def slugify_store_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or name.lower()


def fetch_nz_store_detail(store: dict[str, Any]) -> dict[str, Any]:
    raw = request_url_optional(str(store["url"]), accept="text/html, application/xhtml+xml, */*")
    if not raw:
        return store
    location = parse_next_location(raw)
    if not location:
        return store
    address = ", ".join(
        str(x)
        for x in [
            location.get("address1"),
            location.get("address2"),
            location.get("address3"),
            location.get("city"),
            location.get("state"),
            location.get("postcode"),
        ]
        if x
    )
    name = str(location.get("publicName") or store.get("name") or "")
    store.update(
        {
            "location_id": str(location.get("locationId") or store.get("location_id") or ""),
            "slug": slugify_store_name(name),
            "name": name,
            "phone": location.get("phoneNumber"),
            "address": address or None,
            "city": location.get("city"),
            "state": location.get("state"),
            "postcode": location.get("postcode"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "trading_hours": [
                {"day": item.get("weekDay"), "hours": item.get("hours")}
                for item in as_list(location.get("tradingHours"))
                if isinstance(item, dict)
            ],
        }
    )
    return store


def parse_next_location(raw: str) -> dict[str, Any] | None:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', raw, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    props = data.get("props") if isinstance(data.get("props"), dict) else {}
    page_props = props.get("pageProps") if isinstance(props.get("pageProps"), dict) else data.get("pageProps", {})
    location = page_props.get("location") if isinstance(page_props, dict) else None
    return location if isinstance(location, dict) and location.get("locationId") else None


def parse_store_url(url: str, country: str) -> dict[str, Any]:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    name = slug.replace("-", " ").title()
    name = name.replace(" Cbd", " CBD").replace(" Dc", " DC").replace("Nsw", "NSW")
    return {"slug": slug, "name": name, "country": country, "url": url}


def cmd_stores(args: argparse.Namespace) -> None:
    data = parse_sitemap_locations(args.country, region=args.region, limit=args.limit)
    emit(data, args.json)


def print_products(data: dict[str, Any]) -> None:
    cfg = country_config(str(data.get("country") or "nz"))
    label = data.get("target") or "search"
    query = data.get("query_sku") or data.get("query") or ""
    total = data.get("total_count")
    total_label = f" of {total}" if total is not None else ""
    print(f"{cfg['label']} {label} {query!r}: {data.get('count', 0)}{total_label} products ({data.get('elapsed_ms')} ms)")
    print()
    for product in data.get("products") or []:
        price = money(product.get("price"), str(product.get("currency") or cfg["currency"]))
        print(f"{product.get('sku') or '-':>10}  {product.get('name')}")
        bits = [price, product.get("brand"), product.get("size"), product.get("colour"), product.get("seller")]
        print("            " + " | ".join(str(x) for x in bits if x))
        if product.get("promotional_reasons"):
            print("            promo: " + ", ".join(str(x) for x in product["promotional_reasons"]))
        if product.get("url"):
            print(f"            {product.get('url')}")
        print()


def print_stores(data: dict[str, Any]) -> None:
    cfg = country_config(str(data.get("country") or "nz"))
    region = f" matching {data.get('region')!r}" if data.get("region") else ""
    print(f"{cfg['label']} stores{region}: showing {data.get('shown')} of {data.get('count')} ({data.get('elapsed_ms')} ms)")
    print(f"Source: {data.get('source')}")
    if data.get("note"):
        print(f"Note: {data.get('note')}")
    print()
    for store in data.get("stores") or []:
        key = store.get("location_id") or store.get("slug")
        print(f"{str(key or '-'):>24}  {store.get('name')}")
        details = store.get("address")
        if not details:
            details = ", ".join(str(x) for x in [store.get("city"), store.get("state"), store.get("postcode")] if x)
        if details:
            print(f"                          {details}")
        if store.get("phone"):
            print(f"                          {store.get('phone')}")
        print(f"                          {store.get('url')}")
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
    ap = argparse.ArgumentParser(description="Lightweight Kmart NZ/AU public read-only product and store lookup CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search Kmart products")
    sp.add_argument("query")
    sp.add_argument("--country", choices=sorted(COUNTRIES), default="nz")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch an exact Kmart SKU")
    sp.add_argument("sku")
    sp.add_argument("--country", choices=sorted(COUNTRIES), default="nz")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("stores", help="list public Kmart store-detail URLs and metadata")
    sp.add_argument("--region", help="filter sitemap store slugs/names by text")
    sp.add_argument("--country", choices=sorted(COUNTRIES), default="nz")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("specials", help="list clearance/promotional products, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--country", choices=sorted(COUNTRIES), default="nz")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
