#!/usr/bin/env python3
"""Briscoes NZ lightweight public product/store CLI.

Self-contained stdlib wrapper around public Briscoes NZ Klevu search and
Magento GraphQL read-only endpoints. No login, cart mutation, browser
automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_WEB = "https://www.briscoes.co.nz"
GRAPHQL_URL = BASE_WEB + "/graphql"
DEFAULT_KLEVU_HOST = "aucs34.ksearchnet.com"
DEFAULT_KLEVU_API_KEY = "klevu-173190000117617559"
UA = os.environ.get(
    "BRISCOES_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

KLEVU_FIELDS = [
    "isDiscountPrice",
    "second_main_image",
    "discount",
    "displayTitle",
    "priceRuleBadgeData",
    "price",
    "inStock",
    "id",
    "imageHover",
    "sku",
    "brand",
    "basePrice",
    "image",
    "priceBadgeData",
    "brand_url",
    "relative_url",
    "name",
    "color",
    "sap_category",
    "colorSwatch",
    "productplu",
    "currency",
    "isHidePriceRange",
    "salePrice",
    "type_id",
    "url",
    "breadcrumb",
    "category",
    "manualBadge",
]

PROMO_CATEGORY_PREFIXES = (
    "buying-guides-inspiration",
    "clearance",
    "gift-guides",
    "hot-home-deals",
    "new-in",
    "online-only",
    "sale",
    "sale-backup",
    "shop-by-brand",
)

KLEVU_CONFIG_QUERY = """
query KlevuData {
  storeConfig {
    store_code
    klevu_search_url
    klevu_search_js_api_key
    quick_search_placeholder
  }
}
"""

PRODUCT_QUERY = """
query ProductBySku($sku: String!) {
  products(filter: { sku: { eq: $sku } }, pageSize: 1) {
    total_count
    items {
      __typename
      uid
      id
      sku
      name
      brand
      stock_status
      url_key
      url_suffix
      special_price
      image { url }
      small_image { url }
      price_range {
        minimum_price {
          regular_price { value currency }
          final_price { value currency }
          discount { amount_off percent_off }
        }
        maximum_price {
          regular_price { value currency }
          final_price { value currency }
          discount { amount_off percent_off }
        }
      }
      categories {
        uid
        name
        url_path
      }
      product_salesrule_badges {
        badge_name
        badge_description
        badge_browse_text
      }
    }
  }
}
"""

STORES_QUERY = """
query FindAllStores {
  findStore {
    store_id
    scope_id
    store_enable
    store_locator_name
    is_display_store_finder
    latitude
    longitude
    working_time
    cut_off_time
    oms_store_id
    store_number
    fulfilment_number
    dispatch_point_name
    enable_next_day_delivery
    same_day_delivery
    organization
    line1
    line2
    city
    region
    postcode
    country_code
    state
    email
    phone
  }
}
"""

_KLEVU_CONFIG: dict[str, str] | None = None


def die(message: str, code: int = 1) -> None:
    print(f"briscoes-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(url: str, payload: dict[str, Any], timeout: int = 25) -> Any:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
            detail = body.get("message") or body.get("Message") or body.get("errors") or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = request_json(GRAPHQL_URL, payload)
    if not isinstance(data, dict):
        die("unexpected GraphQL response")
    if data.get("errors"):
        messages = "; ".join(str(e.get("message", e)) for e in data["errors"] if isinstance(e, dict))
        die(f"GraphQL error: {messages or data['errors']}")
    return data.get("data") or {}


def klevu_config() -> dict[str, str]:
    global _KLEVU_CONFIG
    if _KLEVU_CONFIG is not None:
        return _KLEVU_CONFIG
    store = (graphql(KLEVU_CONFIG_QUERY).get("storeConfig") or {})
    host = str(store.get("klevu_search_url") or DEFAULT_KLEVU_HOST)
    api_key = str(store.get("klevu_search_js_api_key") or DEFAULT_KLEVU_API_KEY)
    if not host.startswith("http://") and not host.startswith("https://"):
        url = "https://" + host.strip("/") + "/cs/v2/search"
    else:
        url = host.rstrip("/") + "/cs/v2/search"
    _KLEVU_CONFIG = {"url": url, "api_key": api_key, "store_code": str(store.get("store_code") or "briscoes")}
    return _KLEVU_CONFIG


def to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def money(value: Any) -> str:
    number = to_number(value)
    if number is None:
        return "-"
    return f"${number:.2f}"


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def category_label(raw: Any) -> str:
    text = first_non_empty(raw)
    if not text:
        return ""
    if ">" in text:
        parts = [p.strip() for p in text.split(">") if p.strip()]
        return " > ".join(parts)
    if ";;" in text:
        parts = [p.strip() for p in text.split(";;") if p.strip()]
        return " > ".join(parts[:3])
    return text


def has_price_discount(product: dict[str, Any]) -> bool:
    regular = to_number(product.get("price"))
    sale = to_number(product.get("sale_price"))
    save = to_number(product.get("save_price"))
    return (regular is not None and sale is not None and sale < regular) or bool(save and save > 0)


def placeholder_image(url: Any) -> bool:
    text = str(url or "").lower()
    return not text or "placeholder" in text


def sale_tagged(category: str) -> bool:
    text = category.lower()
    tokens = {p.strip().lower() for p in text.replace(">", ";;").split(";;")}
    return (
        "sale" in tokens
        or "sale backup" in tokens
        or any("clearance" in p or "deals" in p or "deal" == p for p in tokens)
    )


def parse_klevu_product(item: dict[str, Any]) -> dict[str, Any]:
    current = to_number(item.get("salePrice")) or to_number(item.get("price"))
    base = to_number(item.get("basePrice"))
    discount_text = first_non_empty(item.get("discount"))
    category = category_label(item.get("breadcrumb") or item.get("category"))
    is_discount = str(item.get("isDiscountPrice") or "").lower() in {"yes", "true", "1"}
    is_special = is_discount or (base is not None and current is not None and current < base) or sale_tagged(str(item.get("category") or category))
    return {
        "sku": first_non_empty(item.get("sku"), item.get("productplu")),
        "product_id": first_non_empty(item.get("id")),
        "name": first_non_empty(item.get("name"), item.get("displayTitle")),
        "brand": first_non_empty(item.get("brand")),
        "price": base if base is not None else current,
        "sale_price": current,
        "save_price": round(base - current, 2) if base is not None and current is not None and current < base else None,
        "discount": discount_text or None,
        "is_special": is_special,
        "is_discount_price": is_discount,
        "currency": first_non_empty(item.get("currency"), item.get("storeBaseCurrency"), "NZD"),
        "in_stock": str(item.get("inStock") or "").lower() in {"yes", "true", "1"},
        "category": category,
        "image": first_non_empty(item.get("image"), item.get("imageUrl")),
        "source_url": first_non_empty(item.get("url"), BASE_WEB + "/" + str(item.get("relative_url") or "").lstrip("/")),
    }


def klevu_search(query: str, *, limit: int = 10, page: int = 1) -> dict[str, Any]:
    cfg = klevu_config()
    size = min(max(1, limit), 100)
    current_page = max(1, page)
    payload = {
        "context": {"apiKeys": [cfg["api_key"]]},
        "recordQueries": [
            {
                "id": "productList",
                "typeOfRequest": "SEARCH",
                "settings": {
                    "query": {"term": query},
                    "typeOfRecords": ["KLEVU_PRODUCT"],
                    "limit": size,
                    "offset": (current_page - 1) * size,
                    "sort": "RELEVANCE",
                    "searchPrefs": ["searchCompoundsAsAndQuery", "hideOutOfStockProducts"],
                    "fields": KLEVU_FIELDS,
                },
            }
        ],
    }
    started = time.perf_counter()
    payload_out = request_json(cfg["url"], payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    results = (payload_out or {}).get("queryResults") or []
    result = next((r for r in results if isinstance(r, dict) and r.get("id") == "productList"), {})
    meta = result.get("meta") or {}
    records = result.get("records") or []
    products = [parse_klevu_product(r) for r in records if isinstance(r, dict)]
    return {
        "source": "klevu",
        "query": query,
        "count": len(products),
        "total_count": meta.get("totalResultsFound"),
        "page": current_page,
        "page_size": size,
        "elapsed_ms": elapsed_ms,
        "products": products,
    }


def price_node(item: dict[str, Any], bound: str = "minimum_price") -> dict[str, Any]:
    return (((item.get("price_range") or {}).get(bound) or {}))


def parse_category(cat: dict[str, Any]) -> dict[str, Any]:
    return {"uid": cat.get("uid"), "name": cat.get("name"), "url_path": cat.get("url_path")}


def category_depth(cat: dict[str, Any]) -> int:
    path = str(cat.get("url_path") or "").strip("/")
    return len([p for p in path.split("/") if p])


def preferred_category(categories: list[dict[str, Any]]) -> str:
    if not categories:
        return ""

    def is_promo(cat: dict[str, Any]) -> bool:
        path = str(cat.get("url_path") or "").strip("/").lower()
        return any(path == prefix or path.startswith(prefix + "/") for prefix in PROMO_CATEGORY_PREFIXES)

    candidates = [c for c in categories if not is_promo(c)] or categories
    best = max(candidates, key=lambda c: (category_depth(c), len(str(c.get("url_path") or ""))))
    return str(best.get("name") or "")


def parse_graphql_product(item: dict[str, Any]) -> dict[str, Any]:
    minimum = price_node(item)
    regular = ((minimum.get("regular_price") or {}).get("value"))
    final = ((minimum.get("final_price") or {}).get("value"))
    discount = minimum.get("discount") or {}
    categories = [parse_category(c) for c in item.get("categories") or [] if isinstance(c, dict)]
    category = preferred_category(categories)
    url_key = str(item.get("url_key") or "").lstrip("/")
    url_suffix = str(item.get("url_suffix") or "")
    return {
        "sku": first_non_empty(item.get("sku")),
        "product_id": item.get("id"),
        "uid": item.get("uid"),
        "type": item.get("__typename"),
        "name": first_non_empty(item.get("name")),
        "brand": first_non_empty(item.get("brand")),
        "price": regular,
        "sale_price": final,
        "save_price": discount.get("amount_off"),
        "save_percentage": discount.get("percent_off"),
        "special_price": item.get("special_price"),
        "is_special": bool((discount.get("amount_off") or 0) or item.get("special_price")),
        "currency": ((minimum.get("final_price") or {}).get("currency")) or "NZD",
        "stock_status": item.get("stock_status"),
        "in_stock": item.get("stock_status") == "IN_STOCK",
        "category": category,
        "categories": categories,
        "badges": [b for b in item.get("product_salesrule_badges") or [] if isinstance(b, dict)],
        "image": first_non_empty((item.get("small_image") or {}).get("url"), (item.get("image") or {}).get("url")),
        "source_url": BASE_WEB + "/" + url_key + url_suffix,
    }


def product_details(sku: str) -> list[dict[str, Any]]:
    payload = graphql(PRODUCT_QUERY, {"sku": sku})
    products_raw = ((payload.get("products") or {}).get("items") or [])
    return [parse_graphql_product(p) for p in products_raw if isinstance(p, dict)]


def exact_klevu_match(sku: str) -> dict[str, Any] | None:
    data = klevu_search(sku, limit=5)
    for product in data.get("products") or []:
        if str(product.get("sku") or "").strip() == str(sku).strip():
            return product
    return None


def enrich_from_klevu(product: dict[str, Any], klevu_product: dict[str, Any] | None) -> dict[str, Any]:
    if not klevu_product:
        return product
    if placeholder_image(product.get("image")) and not placeholder_image(klevu_product.get("image")):
        product["image"] = klevu_product.get("image")
    if not product.get("category") and klevu_product.get("category"):
        product["category"] = klevu_product.get("category")
    if not product.get("source_url") and klevu_product.get("source_url"):
        product["source_url"] = klevu_product.get("source_url")
    return product


def parse_hours(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        raw = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return []
    out = []
    for row in raw if isinstance(raw, list) else []:
        if isinstance(row, dict):
            out.append(
                {
                    "day": row.get("day_of_week"),
                    "open": row.get("open_time"),
                    "close": row.get("close_time"),
                }
            )
    return out


def parse_store(item: dict[str, Any]) -> dict[str, Any]:
    parts = [item.get("line1"), item.get("line2"), item.get("city"), item.get("postcode")]
    address = ", ".join(str(p).strip() for p in parts if str(p or "").strip())
    return {
        "store_id": item.get("store_id"),
        "store_number": item.get("store_number"),
        "name": item.get("store_locator_name"),
        "organization": item.get("organization"),
        "address": address,
        "line1": item.get("line1"),
        "line2": item.get("line2"),
        "city": item.get("city"),
        "region": item.get("region") or item.get("state"),
        "postcode": item.get("postcode"),
        "country_code": item.get("country_code"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "phone": str(item.get("phone") or "").strip(),
        "email": item.get("email"),
        "hours": parse_hours(item.get("working_time")),
        "cut_off_time": item.get("cut_off_time"),
        "same_day_delivery": item.get("same_day_delivery"),
        "enable_next_day_delivery": bool(item.get("enable_next_day_delivery")),
        "source_url": BASE_WEB + "/store-finder",
    }


def store_matches(store: dict[str, Any], region: str) -> bool:
    needle = re.sub(r"\s+", " ", region.strip().lower())
    if not needle:
        return True

    def clean(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    primary = [clean(store.get(k)) for k in ("name", "city", "region", "postcode")]
    if any(needle in value for value in primary):
        return True

    # Suburb lives in line2 for most stores. Keep this exact so a broad region
    # query like "wellington" does not match Auckland's "Mt Wellington" address.
    suburb = clean(store.get("line2"))
    if suburb and needle == suburb:
        return True

    # Address matching is useful for postcode or street-number lookups, but not
    # for broad city/region filters because road names can contain other cities.
    if any(ch.isdigit() for ch in needle):
        return needle in clean(store.get("address"))
    return False


def cmd_search(args: argparse.Namespace) -> None:
    emit_products(klevu_search(args.query, limit=args.limit, page=args.page), args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    term = args.query or "*"
    limit = min(max(1, args.limit), 100)
    fetch_size = min(max(limit * 6, 30), 100)
    data = klevu_search(term, limit=fetch_size, page=args.page)
    specials = []
    for candidate in data["products"]:
        if not candidate.get("is_special") or not candidate.get("sku"):
            continue
        detail_products = product_details(str(candidate["sku"]))
        if not detail_products:
            continue
        detail = enrich_from_klevu(detail_products[0], candidate)
        if not has_price_discount(detail):
            continue
        specials.append(detail)
        if len(specials) >= limit:
            break

    data["source"] = "klevu-sale-filter+magento-price-verify"
    data["query"] = args.query
    data["framing"] = "Klevu sale/deal discovery verified against Magento price_range; Briscoes does not expose a dedicated public specials endpoint"
    data["verification"] = "Each returned product has Magento final_price below regular_price."
    data["products"] = specials
    data["count"] = len(data["products"])
    data["page_size"] = limit
    emit_products(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    products = product_details(args.sku)
    if products and any(placeholder_image(p.get("image")) for p in products):
        match = exact_klevu_match(args.sku)
        products = [enrich_from_klevu(p, match) for p in products]
    data = {
        "source": "magento-graphql",
        "sku": args.sku,
        "count": len(products),
        "total_count": len(products),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "products": products,
    }
    emit_products(data, args.json)


def cmd_stores(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = graphql(STORES_QUERY)
    stores = []
    for item in payload.get("findStore") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("store_enable") or not item.get("is_display_store_finder"):
            continue
        store = parse_store(item)
        if args.region and not store_matches(store, args.region):
            continue
        stores.append(store)
    stores.sort(key=lambda s: (str(s.get("city") or ""), str(s.get("name") or "")))
    data = {
        "source": "magento-graphql",
        "region": args.region,
        "count": len(stores),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stores": stores,
    }
    emit_stores(data, args.json)


def price_label(p: dict[str, Any]) -> str:
    original = p.get("price")
    sale = p.get("sale_price")
    if p.get("is_special") and sale is not None:
        label = f"{money(sale)} sale"
        if original is not None and to_number(original) and to_number(sale) and to_number(original) > to_number(sale):
            label += f" (was {money(original)})"
        return label
    return money(sale if sale is not None else original)


def print_products(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("sku") or data.get("source") or "products"
    print(f"{label}: {data.get('count', 0)} products ({data.get('elapsed_ms')} ms)")
    total = data.get("total_count")
    if total is not None:
        print(f"Total available from source: {total}")
    if data.get("framing"):
        print(str(data["framing"]))
    print()
    for p in data.get("products") or []:
        brand = (p.get("brand") or "").strip()
        name = (p.get("name") or "").strip()
        title = f"{brand} {name}".strip()
        stock = "in stock" if p.get("in_stock") else (p.get("stock_status") or "stock unknown")
        print(f"{p.get('sku'):>8}  {title}")
        bits = [price_label(p), str(stock).lower()]
        if p.get("category"):
            bits.append(str(p["category"]))
        print("          " + " | ".join(x for x in bits if x))
        if p.get("source_url"):
            print(f"          {p.get('source_url')}")
        if p.get("image"):
            print(f"          image: {p.get('image')}")
        print()


def print_stores(data: dict[str, Any]) -> None:
    label = f"stores matching {data['region']}" if data.get("region") else "stores"
    print(f"{label}: {data.get('count', 0)} stores ({data.get('elapsed_ms')} ms)")
    print()
    for s in data.get("stores") or []:
        print(f"{s.get('store_id'):>4}  {s.get('name')}")
        bits = [s.get("address"), s.get("phone"), s.get("email")]
        print("      " + " | ".join(str(x) for x in bits if x))
        hours = s.get("hours") or []
        if hours:
            sample = "; ".join(f"{h.get('day')}: {h.get('open')}-{h.get('close')}" for h in hours[:7])
            print(f"      hours: {sample}")
        print()


def emit_products(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_products(data)


def emit_stores(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_stores(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Briscoes NZ public read-only product and store CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search Briscoes products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch exact Briscoes product SKU detail")
    sp.add_argument("sku")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("stores", help="list Briscoes store-finder locations")
    sp.add_argument("--region", help="filter by city, region, suburb, postcode, or store name")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("specials", help="list sale/deal-flagged products, optionally filtered by query")
    sp.add_argument("query", nargs="?")
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
