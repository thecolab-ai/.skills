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
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

CONSTRUCTOR_BASE = "https://ac.cnstrc.com"
COUNTRIES = {
    "nz": {
        "label": "Kmart NZ",
        "web": "https://www.kmart.co.nz",
        "constructor_key": "key_EyiTrcbGw7IFH3wR",
        "currency": "NZD",
        "store_sitemap": "https://www.kmart.co.nz/sitemap/nz/storelocation-sitemap.xml",
        "store_note": "Kmart NZ's public store sitemap currently exposes shared location slugs; verify individual store pages before treating it as canonical NZ store coverage.",
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
    headers = {
        "Accept": accept,
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = raw[:300].replace("\n", " ")
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


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
        print(f"{store.get('slug'):>24}  {store.get('name')}")
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

    sp = sub.add_parser("stores", help="list public Kmart store-detail URLs from sitemaps")
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
