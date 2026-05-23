#!/usr/bin/env python3
"""Mitre 10 NZ lightweight product and store CLI.

Self-contained stdlib wrapper around public mitre10.co.nz search, product, and
store endpoints. No login, cart mutation, browser automation, or dependencies.
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

BASE_WEB = "https://www.mitre10.co.nz"
BASE_OCC = "https://ccapi.mitre10.co.nz/occ/v2/mitre10"
ALGOLIA_APP_ID = "CQ00O09OXX"
ALGOLIA_SEARCH_KEY = "edc61cb5be5216c9cc02459f13e33729"
ALGOLIA_INDEX = "retail_products_relevance"
ALGOLIA_HOST = "https://cq00o09oxx-dsn.algolia.net"
UA = os.environ.get(
    "MITRE10_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)
FACETS = [
    "availableNationWide",
    "brandName",
    "categoryPath.lvl0",
    "colour",
    "essential",
    "prices.sortPrice",
    "size",
    "storesWithStock",
    "subFineline",
]


def die(message: str, code: int = 1) -> None:
    print(f"mitre10-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> Any:
    data = None
    req_headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            errors = payload.get("errors") if isinstance(payload, dict) else None
            detail = payload.get("message") or payload.get("error") or errors or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def occ_url(path: str, params: dict[str, Any] | None = None) -> str:
    query = {"lang": "en", "curr": "NZD"}
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    return BASE_OCC + path + "?" + urllib.parse.urlencode(query)


def algolia_url() -> str:
    params = {
        "x-algolia-agent": "Algolia for JavaScript (4.20.0); Browser (lite); instantsearch.js (4.56.11); JS Helper (3.14.1)",
        "x-algolia-api-key": ALGOLIA_SEARCH_KEY,
        "x-algolia-application-id": ALGOLIA_APP_ID,
    }
    return ALGOLIA_HOST + "/1/indexes/*/queries?" + urllib.parse.urlencode(params)


def algolia_params(query: str, *, limit: int, page: int, specials: bool = False) -> str:
    filters = "online:true AND availableNationWide:true"
    if specials:
        filters += " AND prices.onNationalPromo:true"
    params = {
        "analyticsTags": json.dumps(["search", "standard"], separators=(",", ":")),
        "clickAnalytics": "true",
        "facets": json.dumps(FACETS, separators=(",", ":")),
        "filters": filters,
        "highlightPostTag": "__/ais-highlight__",
        "highlightPreTag": "__ais-highlight__",
        "hitsPerPage": str(min(max(1, limit), 100)),
        "maxValuesPerFacet": "500",
        "page": str(max(0, page)),
        "query": query,
        "ruleContexts": json.dumps(["standard"], separators=(",", ":")),
        "tagFilters": "",
        "userToken": "anonymous-cli",
    }
    return urllib.parse.urlencode(params)


def algolia_search(query: str, *, limit: int, page: int = 0, specials: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    payload = {
        "requests": [
            {
                "indexName": ALGOLIA_INDEX,
                "params": algolia_params(query, limit=limit, page=page, specials=specials),
            }
        ]
    }
    data = request_json(algolia_url(), method="POST", body=payload)
    result = (data.get("results") or [{}])[0] if isinstance(data, dict) else {}
    products = [parse_algolia_product(hit) for hit in result.get("hits") or [] if isinstance(hit, dict)]
    return {
        "kind": "products",
        "source": "algolia",
        "query": query,
        "specials": specials,
        "count": len(products),
        "total": result.get("nbHits"),
        "page": result.get("page", page),
        "pages": result.get("nbPages"),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "products": products[:limit],
    }


def price_from_algolia(prices: dict[str, Any]) -> dict[str, Any]:
    rrp = prices.get("nationalRRP")
    promo = prices.get("nationalPromo")
    value = promo if promo is not None else rrp
    labels = prices.get("labels") if isinstance(prices.get("labels"), list) else []
    badges = [label.get("priceBadge") for label in labels if isinstance(label, dict) and label.get("priceBadge")]
    return {
        "value": value,
        "regular": rrp,
        "promo": promo,
        "hide_price": bool(prices.get("hidePrice")),
        "badges": badges,
    }


def image_url(path: Any) -> str | None:
    if not path:
        return None
    if isinstance(path, str):
        if path.startswith("http"):
            return path
        return BASE_WEB + path if path.startswith("/") else BASE_WEB + "/" + path
    return None


def parse_algolia_product(hit: dict[str, Any]) -> dict[str, Any]:
    prices = hit.get("prices") if isinstance(hit.get("prices"), dict) else {}
    images = hit.get("images") if isinstance(hit.get("images"), list) else []
    image = None
    if images and isinstance(images[0], dict):
        image = images[0].get("url") or images[0].get("imageUrl")
    code = str(hit.get("objectID") or hit.get("code") or "")
    return {
        "code": code,
        "name": hit.get("name") or "",
        "brand": hit.get("brandName") or "",
        "price": price_from_algolia(prices),
        "available_nationwide": bool(hit.get("availableNationWide")),
        "click_and_collect_store_count": len(hit.get("clickAndCollect") or []),
        "home_delivery_region_count": len(hit.get("homeDelivery") or []),
        "category": category_from_hit(hit),
        "url": BASE_WEB + hit["url"] if isinstance(hit.get("url"), str) and hit["url"].startswith("/") else hit.get("url"),
        "image": image_url(hit.get("img96Wx96H") or image),
    }


def category_from_hit(hit: dict[str, Any]) -> str:
    path = hit.get("categoryPath")
    if isinstance(path, dict):
        levels = [path.get(key) for key in ("lvl0", "lvl1", "lvl2")]
        levels = [x for x in levels if isinstance(x, str) and x]
        if levels:
            return levels[-1]
    names = hit.get("categoryNames")
    if isinstance(names, list):
        return " / ".join(str(x) for x in names[:3] if x)
    return ""


def parse_occ_product(item: dict[str, Any]) -> dict[str, Any]:
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    regular = item.get("regularPrice") if isinstance(item.get("regularPrice"), dict) else {}
    stock = item.get("stock") if isinstance(item.get("stock"), dict) else {}
    images = item.get("images") if isinstance(item.get("images"), list) else []
    image = None
    for entry in images:
        if isinstance(entry, dict) and entry.get("url"):
            image = entry.get("url")
            break
    categories = item.get("categories") if isinstance(item.get("categories"), list) else []
    return {
        "code": str(item.get("code") or ""),
        "name": item.get("name") or "",
        "brand": (item.get("brandName") or "").strip(),
        "summary": item.get("summary") or item.get("shortDescription") or "",
        "description": item.get("description") or "",
        "model_number": item.get("modelNumber") or "",
        "price": {
            "formatted": price.get("formattedValue"),
            "value": price.get("value"),
            "regular_formatted": regular.get("formattedValue"),
            "regular_value": regular.get("value"),
            "currency": price.get("currencyIso") or "NZD",
            "national_promo": bool(price.get("nationalPromo")),
            "regional_promo": bool(price.get("regionalPromo")),
        },
        "stock": {
            "level": stock.get("stockLevel"),
            "status": stock.get("stockLevelStatus") or item.get("stockIndicator"),
            "available_in_selected_store": bool(item.get("availableInSelectedStore")),
            "available_in_nearby_store": bool(item.get("availableInNearByStore")),
        },
        "url": BASE_WEB + item["url"] if isinstance(item.get("url"), str) and item["url"].startswith("/") else item.get("url"),
        "image": image_url(image),
        "categories": [c.get("name") for c in categories if isinstance(c, dict) and c.get("name")],
    }


def parse_store(store: dict[str, Any]) -> dict[str, Any]:
    address = store.get("address") if isinstance(store.get("address"), dict) else {}
    geo = store.get("geoPoint") if isinstance(store.get("geoPoint"), dict) else {}
    return {
        "code": str(store.get("staticStoreCode") or store.get("name") or ""),
        "name": store.get("displayName") or store.get("name") or "",
        "phone": address.get("phone") or "",
        "email": address.get("email") or "",
        "address": address.get("formattedAddress") or address.get("nzPostalAddress") or "",
        "line1": address.get("line1") or "",
        "suburb": address.get("suburb") or address.get("line2") or "",
        "town": address.get("town") or "",
        "postcode": address.get("postalCode") or "",
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "hours": week_hours(store),
    }


def week_hours(store: dict[str, Any]) -> list[dict[str, Any]]:
    opening = store.get("openingHours") if isinstance(store.get("openingHours"), dict) else {}
    days = opening.get("weekDayOpeningList") if isinstance(opening.get("weekDayOpeningList"), list) else []
    out = []
    for day in days:
        if not isinstance(day, dict):
            continue
        open_time = day.get("openingTime") if isinstance(day.get("openingTime"), dict) else {}
        close_time = day.get("closingTime") if isinstance(day.get("closingTime"), dict) else {}
        out.append(
            {
                "day": day.get("weekDay"),
                "closed": bool(day.get("closed")),
                "open": open_time.get("formattedHour"),
                "close": close_time.get("formattedHour"),
            }
        )
    return out


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"${float(value):.2f}"
    except Exception:
        return str(value)


def product_price_label(product: dict[str, Any]) -> str:
    price = product.get("price") if isinstance(product.get("price"), dict) else {}
    if price.get("hide_price"):
        return "-"
    if price.get("formatted"):
        label = str(price["formatted"])
        regular = price.get("regular_formatted")
        if regular and regular != label:
            label += f" (was {regular})"
        return label
    value = price.get("value")
    if price.get("promo") is not None:
        label = f"{money(value)} promo"
        regular = price.get("regular")
        if regular is not None and regular != value:
            label += f" (was {money(regular)})"
        return label
    return money(value if value is not None else price.get("regular"))


def cmd_search(args: argparse.Namespace) -> None:
    data = algolia_search(args.query, limit=args.limit, page=args.page, specials=False)
    emit(data, args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    data = algolia_search(args.query or "", limit=args.limit, page=args.page, specials=True)
    emit(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    code = urllib.parse.quote(str(args.code), safe="")
    payload = request_json(occ_url(f"/products/{code}", {"fields": "FULL"}))
    product = parse_occ_product(payload if isinstance(payload, dict) else {})
    data = {
        "kind": "product",
        "source": "occ",
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "product": product,
    }
    emit(data, args.json)


def cmd_stores(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    page = max(0, args.page)
    limit = min(max(1, args.limit), 100)
    if args.region:
        payload = request_json(
            occ_url(
                "/geolocation/store-locator",
                {
                    "fields": "FULL",
                    "page": page,
                    "pageSize": limit,
                    "locationQuery": args.region,
                },
            )
        )
    else:
        payload = request_json(occ_url("/stores", {"fields": "FULL", "pageSize": limit}))
    stores = [parse_store(s) for s in (payload.get("stores") or []) if isinstance(s, dict)] if isinstance(payload, dict) else []
    data = {
        "kind": "stores",
        "source": "occ",
        "region": args.region,
        "count": len(stores),
        "pagination": payload.get("pagination") if isinstance(payload, dict) else None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stores": stores[:limit],
    }
    emit(data, args.json)


def print_products(data: dict[str, Any]) -> None:
    label = "specials" if data.get("specials") else (data.get("query") or "products")
    print(f"{label}: {data.get('count', 0)} products ({data.get('elapsed_ms')} ms)")
    if data.get("total") is not None:
        print(f"Total available from source: {data.get('total')}")
    print()
    for product in data.get("products") or []:
        code = product.get("code") or ""
        brand = product.get("brand") or ""
        name = product.get("name") or ""
        print(f"{code:>8}  {brand} {name}".strip())
        bits = [product_price_label(product)]
        if product.get("available_nationwide"):
            bits.append("available nationwide")
        if product.get("click_and_collect_store_count"):
            bits.append(f"{product['click_and_collect_store_count']} click-and-collect stores")
        print("          " + " | ".join(bits))
        if product.get("category"):
            print(f"          category: {product['category']}")
        if product.get("url"):
            print(f"          {product['url']}")
        print()


def print_product(data: dict[str, Any]) -> None:
    product = data.get("product") or {}
    print(f"{product.get('code', '')}  {product.get('brand', '')} {product.get('name', '')}".strip())
    print(f"Price: {product_price_label(product)}")
    stock = product.get("stock") if isinstance(product.get("stock"), dict) else {}
    status = stock.get("status")
    if status:
        print(f"Stock: {status}")
    if product.get("model_number"):
        print(f"Model: {product['model_number']}")
    if product.get("categories"):
        print("Category: " + " / ".join(product["categories"][:4]))
    summary = product.get("summary")
    if summary:
        text = " ".join(str(summary).split())
        print("Summary: " + (text[:220] + "..." if len(text) > 220 else text))
    if product.get("url"):
        print(product["url"])


def print_stores(data: dict[str, Any]) -> None:
    label = data.get("region") or "all stores"
    print(f"{label}: {data.get('count', 0)} stores ({data.get('elapsed_ms')} ms)")
    pagination = data.get("pagination") or {}
    if pagination.get("totalResults") is not None:
        print(f"Total available from source: {pagination.get('totalResults')}")
    print()
    for store in data.get("stores") or []:
        print(f"{store.get('code'):>4}  {store.get('name')}")
        details = [store.get("address"), store.get("phone")]
        print("      " + " | ".join(str(x) for x in details if x))
        today = (store.get("hours") or [])[:1]
        if today:
            h = today[0]
            hours = "closed" if h.get("closed") else f"{h.get('open')} - {h.get('close')}"
            print(f"      {h.get('day')}: {hours}")
        print()


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    kind = data.get("kind")
    if kind == "product":
        print_product(data)
    elif kind == "stores":
        print_stores(data)
    else:
        print_products(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Mitre 10 NZ product and store lookup CLI (public endpoints, no login required).")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=0, help="zero-based Algolia page number")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch an exact product code")
    sp.add_argument("code")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("stores", help="list stores or search by city, suburb, or region")
    sp.add_argument("--region", help="city, suburb, postcode, or region text, e.g. auckland")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=0, help="zero-based store locator page number")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("specials", help="list promotional products, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=0, help="zero-based Algolia page number")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
