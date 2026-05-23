#!/usr/bin/env python3
"""Woolworths NZ lightweight product CLI.

Self-contained stdlib wrapper around public woolworths.co.nz product endpoints.
No login, cart mutation, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_WEB = "https://www.woolworths.co.nz"
BASE_API = BASE_WEB + "/api/v1"
UA = os.environ.get(
    "WOOLWORTHS_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)
UI_VER = os.environ.get("WOOLWORTHS_NZ_UI_VER", "7.70.51")


def die(message: str, code: int = 1) -> None:
    print(f"woolworths-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    url = BASE_API + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "OnlineShopping.WebApp",
        "X-UI-Ver": UI_VER,
        "Referer": BASE_WEB + "/",
        "Origin": BASE_WEB,
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("Message") or payload.get("message") or payload.get("Error") or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"${float(value):.2f}"
    except Exception:
        return str(value)


def nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def category_from(item: dict[str, Any]) -> str:
    breadcrumb = item.get("breadcrumb") or {}
    parts: list[str] = []
    for key in ("department", "aisle", "shelf"):
        name = nested(breadcrumb, key, "name")
        if name:
            parts.append(str(name))
    if parts:
        return " / ".join(parts)
    departments = item.get("departments") or []
    if departments and isinstance(departments[0], dict):
        return departments[0].get("name") or ""
    return ""


def parse_product(item: dict[str, Any]) -> dict[str, Any]:
    price = item.get("price") or {}
    size = item.get("size") or {}
    quantity = item.get("quantity") or {}
    images_raw = item.get("images") or {}
    if isinstance(images_raw, dict):
        image = images_raw.get("big") or images_raw.get("small")
    elif isinstance(images_raw, list) and images_raw:
        first_image = images_raw[0]
        image = first_image.get("url") if isinstance(first_image, dict) else str(first_image)
    else:
        image = None
    sale_price = price.get("salePrice")
    original_price = price.get("originalPrice")
    is_special = bool(price.get("isSpecial") or price.get("isClubPrice"))
    return {
        "sku": str(item.get("sku") or ""),
        "name": item.get("name") or "",
        "brand": item.get("brand") or "",
        "barcode": item.get("barcode") or "",
        "slug": item.get("slug") or "",
        "price": original_price,
        "sale_price": sale_price,
        "save_price": price.get("savePrice"),
        "save_percentage": price.get("savePercentage"),
        "is_special": is_special,
        "is_club_price": bool(price.get("isClubPrice")),
        "unit": item.get("unit") or "Each",
        "selected_purchasing_unit": item.get("selectedPurchasingUnit"),
        "size": size.get("volumeSize") or "",
        "package_type": size.get("packageType"),
        "cup_price": size.get("cupPrice"),
        "cup_measure": size.get("cupMeasure"),
        "availability": item.get("availabilityStatus") or "Unknown",
        "in_stock": item.get("availabilityStatus") == "In Stock",
        "category": category_from(item),
        "supports_dual_pricing": bool(item.get("supportsBothEachAndKgPricing")),
        "average_weight_per_unit": item.get("averageWeightPerUnit"),
        "average_price_per_each": price.get("averagePricePerSingleUnit"),
        "purchasing_unit_price": price.get("purchasingUnitPrice"),
        "minimum_quantity": quantity.get("min"),
        "maximum_quantity": quantity.get("max"),
        "quantity_increment": quantity.get("increment"),
        "image": image or item.get("imageUrl") or item.get("bigImageUrl"),
        "source_url": BASE_WEB + "/shop/productdetails/" + str(item.get("sku") or "") + "/" + str(item.get("slug") or ""),
    }


def product_items(payload: Any) -> list[dict[str, Any]]:
    items = nested(payload or {}, "products", "items", default=[])
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("type", "Product") == "Product":
            p = parse_product(item)
            if p["sku"] and p["name"]:
                out.append(p)
    return out


def products_query(target: str, *, search: str | None = None, category_id: str | None = None, limit: int = 10, page: int = 1, in_stock_only: bool = False) -> dict[str, Any]:
    size = min(max(1, limit), 48)
    params: dict[str, Any] = {
        "target": target,
        "size": size,
        "page": max(1, page),
        "inStockProductsOnly": str(bool(in_stock_only)).lower(),
    }
    if search:
        params["search"] = search
    if category_id:
        params["categoryId"] = category_id
    started = time.perf_counter()
    payload = request_json("/products", params=params)
    products = product_items(payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "target": target,
        "query": search,
        "category_id": category_id,
        "count": len(products),
        "elapsed_ms": elapsed_ms,
        "products": products[:limit],
        "raw_total": nested(payload or {}, "products", "totalRecordCount"),
    }


def cmd_search(args: argparse.Namespace) -> None:
    data = products_query("search", search=args.query, limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    if args.size:
        needle = args.size.lower()
        data["products"] = [p for p in data["products"] if needle in (p.get("size") or "").lower()]
        data["count"] = len(data["products"])
    emit(data, args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    if args.query:
        # The upstream specials endpoint ignores the search parameter, so when the
        # user supplies a query we use the search target and filter to specials
        # client-side. Fetch up to the API max so the filter has enough to work with.
        fetch_size = max(args.limit * 4, 24)
        data = products_query("search", search=args.query, limit=fetch_size, page=args.page, in_stock_only=args.in_stock_only)
        specials_only = [p for p in data["products"] if p.get("is_special")]
        data["products"] = specials_only[:args.limit]
        data["count"] = len(data["products"])
        data["target"] = "specials"
    else:
        data = products_query("specials", limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    emit(data, args.json)


def cmd_browse(args: argparse.Namespace) -> None:
    data = products_query("browse", category_id=args.category_id, limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    emit(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    products = []
    started = time.perf_counter()
    for sku in args.skus:
        payload = request_json(f"/products/{urllib.parse.quote(str(sku))}")
        if isinstance(payload, dict):
            products.append(parse_product(payload))
    data = {"count": len(products), "elapsed_ms": round((time.perf_counter() - started) * 1000), "products": products}
    emit(data, args.json)


def price_label(p: dict[str, Any]) -> str:
    original = p.get("price")
    sale = p.get("sale_price")
    if p.get("is_special") and sale is not None and sale != original:
        label = f"{money(sale)} special"
        if original is not None:
            label += f" (was {money(original)})"
        if p.get("is_club_price"):
            label += " club"
        return label
    return money(sale if sale is not None else original)


def print_products(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("target") or "products"
    print(f"{label}: {data.get('count', 0)} products ({data.get('elapsed_ms')} ms)")
    total = data.get("raw_total")
    if total is not None:
        print(f"Total available from source: {total}")
    print()
    for p in data.get("products") or []:
        bits = []
        size = p.get("size") or ""
        if size:
            bits.append(str(size))
        if p.get("package_type"):
            bits.append(str(p["package_type"]))
        bits.append(price_label(p))
        stock = "in stock" if p.get("in_stock") else p.get("availability", "unknown")
        bits.append(str(stock).lower())
        print(f"{p.get('sku'):>8}  {p.get('brand', '').title()} {p.get('name', '').title()}".strip())
        print("          " + " | ".join(x for x in bits if x))
        if p.get("cup_price") and p.get("cup_measure"):
            print(f"          unit: {money(p.get('cup_price'))} per {p.get('cup_measure')}")
        if p.get("category"):
            print(f"          category: {p.get('category')}")
        if p.get("supports_dual_pricing"):
            avg = p.get("average_weight_per_unit")
            print(f"          purchase options: Each or Kg" + (f"; avg wt {avg}kg" if avg else ""))
        print()


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_products(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Woolworths NZ product lookup CLI (public product endpoints, no login required).")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--size", help="filter returned products by size text, e.g. 2L")
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("specials", help="list specials, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)

    sp = sub.add_parser("browse", help="browse a numeric Woolworths category id")
    sp.add_argument("category_id", help="numeric category id from Woolworths breadcrumb/category data")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_browse)

    sp = sub.add_parser("product", help="fetch one or more product SKUs")
    sp.add_argument("skus", nargs="+")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
