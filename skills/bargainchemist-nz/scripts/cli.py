#!/usr/bin/env python3
"""Bargain Chemist NZ lightweight read-only product CLI.

Self-contained stdlib wrapper around public Boost Commerce search/suggest
endpoints and Shopify product JSON. No login, cart mutation, browser
automation, prescription flow, or third-party dependencies.
"""
from __future__ import annotations

import argparse
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

BASE_WEB = "https://www.bargainchemist.co.nz"
BOOST_SEARCH_BASE = "https://services.mybcapps.com/bc-sf-filter/search"
BOOST_SUGGEST_BASE = "https://services.mybcapps.com/bc-sf-filter/search/suggest"
SHOP = "bargain-chemist.myshopify.com"
DEFAULT_LIMIT = 12
MAX_LIMIT = 50


class ApiError(Exception):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"bargainchemist-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def bounded_limit(value: str) -> int:
    parsed = positive_int(value)
    if parsed > MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"must be <= {MAX_LIMIT}")
    return parsed


def request_json(url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> tuple[Any, str]:
    if params:
        clean = {k: str(v) for k, v in params.items() if v not in (None, "")}
        url = url + "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-NZ,en;q=0.9",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
    }
    try:
        body, _ct, final_url = nzfetch.fetch_bytes(url, headers=headers, timeout=timeout, accept="application/json, text/plain, */*")
        raw = body.decode("utf-8", "replace")
        return json.loads(raw), final_url
    except nzfetch.Blocked as e:
        raise ApiError(f"network error calling {url}: {e}") from e
    except nzfetch.FetchError as e:
        raise ApiError(str(e)) from e
    except json.JSONDecodeError as e:
        raise ApiError(f"invalid JSON from {url}: {e}") from e


def to_number(value: Any, *, cents: bool = False) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = re.sub(r"[^0-9.]+", "", str(value))
        if not text:
            return None
        try:
            amount = float(text)
        except ValueError:
            return None
    if cents:
        amount = amount / 100.0
    return round(amount, 2)


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def money(value: Any) -> str:
    amount = to_number(value)
    if amount is None:
        return "-"
    return f"${amount:.2f}"


def stock_label(value: Any) -> str:
    available = bool_or_none(value)
    if available is True:
        return "in stock"
    if available is False:
        return "unavailable"
    return "unknown"


def product_url(handle: str) -> str:
    return f"{BASE_WEB}/products/{urllib.parse.quote(handle, safe='')}"


def absolute_url(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if text.startswith("//"):
        return "https:" + text
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return BASE_WEB + text
    return text


def normalize_image(entry: Any) -> str | None:
    if isinstance(entry, str):
        return absolute_url(entry)
    if isinstance(entry, dict):
        for key in ("src", "url", "image", "original_src"):
            url = absolute_url(entry.get(key))
            if url:
                return url
        preview = entry.get("preview_image")
        if isinstance(preview, dict):
            return normalize_image(preview)
    return None


def normalize_images(raw: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in ("images", "images_info", "media"):
        value = raw.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    for key in ("featured_image", "image"):
        value = raw.get(key)
        if value:
            candidates.append(value)
    seen: set[str] = set()
    images: list[str] = []
    for entry in candidates:
        url = normalize_image(entry)
        if url and url not in seen:
            seen.add(url)
            images.append(url)
    return images


def normalize_variant(raw: dict[str, Any], *, cents: bool) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or raw.get("name") or "",
        "sku": raw.get("sku") or "",
        "barcode": raw.get("barcode") or "",
        "available": bool_or_none(raw.get("available")),
        "price": to_number(raw.get("price"), cents=cents),
        "compare_at_price": to_number(raw.get("compare_at_price"), cents=cents),
        "inventory_quantity": to_int(raw.get("inventory_quantity")),
        "option1": raw.get("option1"),
        "option2": raw.get("option2"),
        "option3": raw.get("option3"),
    }


def min_max_variant_prices(variants: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    prices = [v.get("price") for v in variants if isinstance(v.get("price"), (int, float))]
    if not prices:
        return None, None
    return min(prices), max(prices)


def normalize_product(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    cents = source == "shopify-product-json"
    handle = str(raw.get("handle") or "").strip()
    variants_raw = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    variants = [normalize_variant(v, cents=cents) for v in variants_raw if isinstance(v, dict)]
    variant_min, variant_max = min_max_variant_prices(variants)
    price_min = to_number(raw.get("price_min"), cents=cents)
    price_max = to_number(raw.get("price_max"), cents=cents)
    if price_min is None:
        price_min = variant_min if variant_min is not None else to_number(raw.get("price"), cents=cents)
    if price_max is None:
        price_max = variant_max if variant_max is not None else price_min
    url = product_url(handle) if handle else absolute_url(raw.get("url")) or ""
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or raw.get("name") or "",
        "handle": handle,
        "url": url,
        "source_url": url,
        "price_min": price_min,
        "price_max": price_max,
        "available": bool_or_none(raw.get("available")),
        "vendor": raw.get("vendor") or "",
        "product_type": raw.get("product_type") or raw.get("type") or "",
        "body_html": raw.get("body_html") or raw.get("description"),
        "variants": variants,
        "images": normalize_images(raw),
    }


def search_params(term: str, *, limit: int, page: int) -> dict[str, Any]:
    return {
        "_": "pf",
        "shop": SHOP,
        "page": page,
        "limit": limit,
        "sort": "relevance",
        "locale": "en",
        "event_type": "init",
        "pg": "search_page",
        "build_filter_tree": "true",
        "q": term,
        "product_available": "true",
        "variant_available": "true",
        "return_all_currency_fields": "false",
        "currency": "NZD",
        "country": "NZ",
    }


def suggest_params(term: str) -> dict[str, Any]:
    return {
        "shop": SHOP,
        "locale": "en",
        "q": term,
        "re_run_if_typo": "true",
        "event_type": "suggest",
        "pg": "search_page",
        "return_all_currency_fields": "false",
        "recent_search": term,
        "enable_default_result": "false",
    }


def normalize_suggestions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    output: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            output.append({"text": item})
        elif isinstance(item, dict):
            text = item.get("q") or item.get("query") or item.get("term") or item.get("title") or item.get("text")
            output.append({"text": text or "", "raw": item})
    return output


def search_products(term: str, *, limit: int, page: int, raw: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    data, source_url = request_json(BOOST_SEARCH_BASE, search_params(term, limit=limit, page=page))
    products = data.get("products") if isinstance(data, dict) else []
    results = [normalize_product(p, source="boost-commerce-search") for p in products or [] if isinstance(p, dict)]
    output = {
        "source": "boost-commerce-search",
        "source_url": source_url,
        "query": term,
        "page": page,
        "limit": limit,
        "total_product": data.get("total_product") if isinstance(data, dict) else None,
        "total_page": data.get("total_page") if isinstance(data, dict) else None,
        "results": results,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    if raw:
        output["raw"] = data
    return output


def suggest_products(term: str, *, limit: int, raw: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    data, source_url = request_json(BOOST_SUGGEST_BASE, suggest_params(term))
    products = data.get("products") if isinstance(data, dict) else []
    results = [normalize_product(p, source="boost-commerce-suggest") for p in products or [] if isinstance(p, dict)]
    output = {
        "source": "boost-commerce-suggest",
        "source_url": source_url,
        "query": term,
        "limit": limit,
        "total_product": data.get("total_product") if isinstance(data, dict) else None,
        "suggestions": normalize_suggestions(data.get("suggestions") if isinstance(data, dict) else None),
        "results": results[:limit],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    if raw:
        output["raw"] = data
    return output


def extract_handle(value: str) -> str:
    text = value.strip()
    if not text:
        die("product handle or URL is required")
    if "://" in text or text.startswith("www.") or "/products/" in text:
        parse_target = text if "://" in text else "https://" + text.lstrip("/")
        parsed = urllib.parse.urlparse(parse_target)
        path = parsed.path
        if "/products/" in path:
            text = path.split("/products/", 1)[1]
        else:
            text = path.rsplit("/", 1)[-1]
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    if text.endswith(".js"):
        text = text[:-3]
    handle = urllib.parse.unquote(text).strip()
    if not handle or "/" in handle:
        die(f"could not parse product handle from {value!r}")
    return handle


def product_from_boost(handle: str, *, raw: bool = False) -> dict[str, Any] | None:
    data = search_products(handle, limit=12, page=1, raw=raw)
    match = None
    for product in data.get("results") or []:
        if product.get("handle") == handle:
            match = product
            break
    if not match:
        return None
    output = {
        "source": "boost-commerce-search",
        "source_url": data.get("source_url"),
        "handle": handle,
        "total_product": 1,
        "results": [match],
        "product": match,
        "fallback": "Shopify product JSON was unavailable; matched exact handle in Boost search.",
    }
    if raw and data.get("raw") is not None:
        output["raw"] = data["raw"]
    return output


def product_detail(value: str, *, raw: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    handle = extract_handle(value)
    endpoint = product_url(handle) + ".js"
    try:
        data, source_url = request_json(endpoint)
    except ApiError as e:
        fallback = product_from_boost(handle, raw=raw)
        if fallback is not None:
            fallback["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            return fallback
        raise ApiError(f"{e}; Boost fallback did not find handle {handle!r}") from e
    product = normalize_product(data, source="shopify-product-json") if isinstance(data, dict) else {}
    output = {
        "source": "shopify-product-json",
        "source_url": source_url,
        "handle": handle,
        "total_product": 1 if product else 0,
        "results": [product] if product else [],
        "product": product,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    if raw:
        output["raw"] = data
    return output


def print_product_rows(result: dict[str, Any]) -> None:
    total = result.get("total_product")
    query = result.get("query")
    shown = len(result.get("results") or [])
    if query:
        print(f"{total if total is not None else '?'} product matches for {query!r} (showing {shown})")
    else:
        print(f"{shown} product result(s)")
    for product in result.get("results") or []:
        title = product.get("title") or "(untitled)"
        price = money(product.get("price_min"))
        available = stock_label(product.get("available"))
        vendor = product.get("vendor") or ""
        url = product.get("url") or ""
        extra = f" | {vendor}" if vendor else ""
        print(f"{price:>8}  {available:<11}  {title}{extra}")
        if url:
            print(f"          {url}")


def print_suggest(result: dict[str, Any]) -> None:
    suggestions = [s.get("text") for s in result.get("suggestions") or [] if s.get("text")]
    if suggestions:
        print("Suggestions: " + ", ".join(suggestions[:8]))
    print_product_rows(result)


def print_product_detail(result: dict[str, Any]) -> None:
    product = result.get("product") or {}
    if not product:
        print("No product found.")
        return
    title = product.get("title") or "(untitled)"
    price_min = product.get("price_min")
    price_max = product.get("price_max")
    price_text = money(price_min) if price_min == price_max else f"{money(price_min)}-{money(price_max)}"
    bits = [price_text, stock_label(product.get("available"))]
    if product.get("vendor"):
        bits.append(str(product["vendor"]))
    if product.get("product_type"):
        bits.append(str(product["product_type"]))
    print(title)
    print(" | ".join(bits))
    if product.get("url"):
        print(product["url"])
    print(f"Variants: {len(product.get('variants') or [])} | Images: {len(product.get('images') or [])}")


def emit(result: dict[str, Any], *, json_output: bool, mode: str) -> None:
    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if mode == "suggest":
        print_suggest(result)
    elif mode == "product":
        print_product_detail(result)
    else:
        print_product_rows(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bargainchemist-nz",
        description="Read-only Bargain Chemist NZ product search and product detail CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="search Bargain Chemist products")
    search.add_argument("term", help="search term")
    search.add_argument("--limit", type=bounded_limit, default=DEFAULT_LIMIT, help=f"results per page, 1-{MAX_LIMIT}")
    search.add_argument("--page", type=positive_int, default=1, help="1-based search page")
    search.add_argument("--json", dest="json_output", action="store_true", help="print normalized JSON")
    search.add_argument("--raw", action="store_true", help="include raw API response in JSON output")

    suggest = sub.add_parser("suggest", help="fetch suggestions and suggested products")
    suggest.add_argument("term", help="suggestion term")
    suggest.add_argument("--limit", type=bounded_limit, default=8, help=f"maximum suggested products, 1-{MAX_LIMIT}")
    suggest.add_argument("--json", dest="json_output", action="store_true", help="print normalized JSON")
    suggest.add_argument("--raw", action="store_true", help="include raw API response in JSON output")

    product = sub.add_parser("product", help="fetch one product by handle or product URL")
    product.add_argument("handle_or_url", help="product handle or https://www.bargainchemist.co.nz/products/<handle> URL")
    product.add_argument("--json", dest="json_output", action="store_true", help="print normalized JSON")
    product.add_argument("--raw", action="store_true", help="include raw API response in JSON output")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            result = search_products(args.term, limit=args.limit, page=args.page, raw=args.raw)
            emit(result, json_output=args.json_output, mode="search")
        elif args.command == "suggest":
            result = suggest_products(args.term, limit=args.limit, raw=args.raw)
            emit(result, json_output=args.json_output, mode="suggest")
        elif args.command == "product":
            result = product_detail(args.handle_or_url, raw=args.raw)
            emit(result, json_output=args.json_output, mode="product")
        else:
            parser.error("unknown command")
    except ApiError as e:
        die(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
