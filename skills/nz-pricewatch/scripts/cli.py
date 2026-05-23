#!/usr/bin/env python3
"""NZ electronics/appliance price comparison CLI.

Self-contained stdlib wrapper around PriceSpy NZ public read-only pages.
No login, browser session, cart, checkout, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

BASE_WEB = "https://pricespy.co.nz"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

CATEGORY_ALIASES = {
    "tv": 107,
    "tvs": 107,
    "television": 107,
    "televisions": 107,
    "oled": 107,
    "qled": 107,
    "mobile": 103,
    "mobile phone": 103,
    "mobile phones": 103,
    "phone": 103,
    "phones": 103,
    "smartphone": 103,
    "smartphones": 103,
    "iphone": 103,
    "laptop": 353,
    "laptops": 353,
    "headphone": 148,
    "headphones": 148,
    "monitor": 393,
    "monitors": 393,
    "tablet": 1594,
    "tablets": 1594,
    "dishwasher": 523,
    "dishwashers": 523,
    "washing machine": 513,
    "washing machines": 513,
    "vacuum": 515,
    "vacuum cleaner": 515,
    "vacuum cleaners": 515,
    "microwave": 534,
    "microwaves": 534,
    "soundbar": 2,
    "soundbars": 2,
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-pricewatch: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_value(value: Any) -> Any:
    if value == "$undefined":
        return None
    if isinstance(value, dict):
        return {k: clean_value(v) for k, v in value.items() if clean_value(v) is not None}
    if isinstance(value, list):
        return [clean_value(v) for v in value if clean_value(v) is not None]
    return value


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


def product_url(product_id: Any) -> str:
    return f"{BASE_WEB}/product.php?p={urllib.parse.quote(str(product_id))}"


def offer_url(shop_id: Any, offer_id: Any) -> str | None:
    if shop_id in (None, "") or offer_id in (None, ""):
        return None
    return f"{BASE_WEB}/go-to-shop/{urllib.parse.quote(str(shop_id))}/offer/{urllib.parse.quote(str(offer_id))}?client_id=1551"


def request_text(path_or_url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> str:
    url = absolute_url(path_or_url) or path_or_url
    if params:
        clean = {k: str(v) for k, v in params.items() if v not in (None, "")}
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-NZ,en;q=0.9",
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:240]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def parse_product_id(value: str) -> str:
    raw = str(value).strip()
    if raw.isdigit():
        return raw
    m = re.search(r"[?&]p=([0-9]+)", raw)
    if m:
        return m.group(1)
    die(f"expected numeric PriceSpy product id or product.php?p= URL, got {value!r}")


def money(value: Any, currency: str = "NZD") -> str:
    if value is None:
        return "-"
    try:
        amount = float(value)
    except Exception:
        return str(value)
    prefix = "$" if currency == "NZD" else f"{currency} "
    return f"{prefix}{amount:,.0f}" if amount.is_integer() else f"{prefix}{amount:,.2f}"


def change_money(summary: dict[str, Any]) -> str:
    value = summary.get("change_amount")
    if value is None:
        return "-"
    try:
        amount = abs(float(value))
    except Exception:
        return str(value)
    return money(amount)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def decode_next_f_chunks(html_text: str) -> str:
    chunks: list[str] = []
    for m in re.finditer(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)</script>", html_text, flags=re.S):
        try:
            chunks.append(json.loads('"' + m.group(1) + '"'))
        except json.JSONDecodeError:
            continue
    return "\n".join(chunks)


def extract_balanced(text: str, start: int) -> str | None:
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def json_values_after_key(text: str, key: str, opener: str) -> list[Any]:
    values: list[Any] = []
    idx = 0
    while True:
        pos = text.find(key, idx)
        if pos < 0:
            break
        start = text.find(opener, pos + len(key))
        if start < 0:
            break
        raw = extract_balanced(text, start)
        if not raw:
            idx = pos + len(key)
            continue
        idx = start + len(raw)
        try:
            values.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return values


def json_ld_items(html_text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html_text, flags=re.S | re.I):
        raw = html.unescape(m.group(1)).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def category_id(value: str | None, query: str | None = None) -> int | None:
    if value:
        raw = value.strip().lower()
        if raw.isdigit():
            return int(raw)
        resolved = CATEGORY_ALIASES.get(raw)
        if resolved:
            return resolved
        die(f"unknown category {value!r}; use a numeric PriceSpy category id or run categories")
    q = (query or "").lower()
    if re.search(r"\b(oled|qled|tv|television|inch|inches)\b", q):
        return 107
    if re.search(r"\b(iphone|galaxy|pixel|smartphone|mobile phone|phone)\b", q):
        return 103
    return None


def normalize_card(card: dict[str, Any]) -> dict[str, Any] | None:
    data = card.get("data") if isinstance(card.get("data"), dict) else {}
    product = data.get("product") if isinstance(data.get("product"), dict) else None
    if not product or not product.get("id"):
        return None
    offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
    category = product.get("category") if isinstance(product.get("category"), dict) else {}
    price = offer.get("price") if isinstance(offer, dict) else None
    try:
        price = float(price) if price not in (None, "$undefined") else None
    except Exception:
        price = None
    return clean_value(
        {
            "product_id": product.get("id"),
            "title": product.get("name"),
            "brand": product.get("brandName"),
            "category": category.get("categoryName"),
            "category_id": category.get("categoryId"),
            "core_properties": product.get("coreProperties") or [],
            "current_price": price,
            "current_price_display": money(price) if price is not None else None,
            "merchant": offer.get("storeName") if isinstance(offer, dict) else None,
            "merchant_id": offer.get("storeId") if isinstance(offer, dict) else None,
            "stock_status": offer.get("stockStatus") if isinstance(offer, dict) else None,
            "store_count": product.get("storeCount"),
            "price_drop_percent": product.get("priceDrop"),
            "product_url": absolute_url(product.get("productLink")) or product_url(product.get("id")),
            "offer_url": offer.get("offerLink") if isinstance(offer, dict) else None,
            "image": absolute_url(product.get("logo")),
            "source": "PriceSpy NZ",
        }
    )


def extract_product_cards(html_text: str) -> list[dict[str, Any]]:
    joined = decode_next_f_chunks(html_text)
    cards = []
    for raw in json_values_after_key(joined, '"productCardData":', "{"):
        item = normalize_card(raw)
        if item:
            cards.append(item)
    seen: dict[Any, dict[str, Any]] = {}
    order: list[Any] = []
    for item in cards:
        pid = item.get("product_id")
        old = seen.get(pid)
        if old is None:
            seen[pid] = item
            order.append(pid)
            continue
        old_price = old.get("current_price")
        new_price = item.get("current_price")
        if old_price is None or (new_price is not None and new_price < old_price):
            seen[pid] = item
    return [seen[pid] for pid in order]


def product_schema(html_text: str) -> dict[str, Any]:
    for item in json_ld_items(html_text):
        if item.get("@type") == "Product":
            return item
    return {}


def breadcrumb_schema(html_text: str) -> list[dict[str, Any]]:
    for item in json_ld_items(html_text):
        if item.get("@type") == "BreadcrumbList":
            rows = []
            for el in item.get("itemListElement") or []:
                node = el.get("item") if isinstance(el, dict) else None
                if isinstance(node, dict):
                    rows.append({"position": el.get("position"), "name": node.get("name"), "url": node.get("@id")})
            return rows
    return []


def normalize_offer(row: dict[str, Any]) -> dict[str, Any]:
    price_obj = row.get("price") if isinstance(row.get("price"), dict) else {}
    original_obj = row.get("originalPrice") if isinstance(row.get("originalPrice"), dict) else {}
    price = price_obj.get("amount")
    currency = price_obj.get("currency") or "NZD"
    shop = row.get("shop") if isinstance(row.get("shop"), dict) else {}
    deal = row.get("deal") if isinstance(row.get("deal"), dict) else {}
    return clean_value(
        {
            "merchant": shop.get("name"),
            "merchant_id": row.get("shopId"),
            "offer_id": row.get("shopOfferId"),
            "offer_name": row.get("name"),
            "price": price,
            "price_display": money(price, currency),
            "currency": currency,
            "original_price": original_obj.get("amount"),
            "stock_status": row.get("stockStatus"),
            "condition": row.get("condition"),
            "featured": row.get("isFeatured"),
            "deal_percent": deal.get("percentage"),
            "reviews": row.get("shopUserReviews"),
            "logo": row.get("shopLogoUrl"),
            "url": offer_url(row.get("shopId"), row.get("shopOfferId")),
        }
    )


def extract_offer_rows(html_text: str) -> list[dict[str, Any]]:
    joined = decode_next_f_chunks(html_text)
    arrays = json_values_after_key(joined, '"offerRows":', "[")
    rows = arrays[0] if arrays and isinstance(arrays[0], list) else []
    offers = [normalize_offer(x) for x in rows if isinstance(x, dict)]
    return sorted(offers, key=lambda o: (o.get("price") is None, o.get("price") or math.inf))


def normalize_history_item(row: dict[str, Any]) -> dict[str, Any]:
    raw_price = row.get("price")
    price = None
    if raw_price is not None:
        try:
            price = round(float(raw_price) / 100, 2)
        except Exception:
            price = None
    return clean_value(
        {
            "date": row.get("date"),
            "merchant": row.get("shopName"),
            "merchant_id": row.get("shopId"),
            "offer_id": row.get("shopOfferId"),
            "offer_name": row.get("name"),
            "price": price,
            "price_display": money(price),
            "active": row.get("active"),
            "membership_price": row.get("isMembershipPrice"),
            "paid_membership": row.get("isPaidMembership"),
        }
    )


def extract_history_items(html_text: str) -> list[dict[str, Any]]:
    joined = decode_next_f_chunks(html_text)
    arrays = json_values_after_key(joined, '"historyItems":', "[")
    rows: list[dict[str, Any]] = []
    for arr in arrays:
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "shopName" in arr[0]:
            rows = arr
            break
    history = [normalize_history_item(x) for x in rows if isinstance(x, dict)]
    return sorted(history, key=lambda h: (h.get("date") or "", h.get("merchant") or ""))


def filter_history(history: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return history
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for item in history:
        dt = parse_dt(item.get("date"))
        if dt is not None and dt >= cutoff:
            out.append(item)
    return out


def history_summary(history: list[dict[str, Any]], days: int, current_price: float | None = None) -> dict[str, Any]:
    window = filter_history(history, days)
    lows: dict[str, float] = {}
    for item in window:
        if item.get("price") is None:
            continue
        day = str(item.get("date") or "")[:10]
        price = float(item["price"])
        lows[day] = min(lows.get(day, price), price)
    days_sorted = sorted(lows)
    first_price = lows[days_sorted[0]] if days_sorted else None
    first_date = days_sorted[0] if days_sorted else None
    latest_price = current_price if current_price is not None else (lows[days_sorted[-1]] if days_sorted else None)
    latest_date = "current_snapshot" if current_price is not None else (days_sorted[-1] if days_sorted else None)
    delta = round(latest_price - first_price, 2) if latest_price is not None and first_price is not None else None
    pct = round(delta / first_price * 100, 2) if delta is not None and first_price else None
    if delta is None:
        direction = "unknown"
    elif abs(delta) < 1:
        direction = "stable"
    elif delta < 0:
        direction = "down"
    else:
        direction = "up"
    return {
        "days": days,
        "history_points": len(window),
        "merchant_count": len({x.get("merchant") for x in window if x.get("merchant")}),
        "first_lowest_date": first_date,
        "first_lowest_price": first_price,
        "latest_lowest_date": latest_date,
        "latest_lowest_price": latest_price,
        "change_amount": delta,
        "change_percent": pct,
        "direction": direction,
    }


def product_detail(product_id: str, days: int = 30) -> dict[str, Any]:
    started = time.perf_counter()
    html_text = request_text(f"/product.php?p={urllib.parse.quote(product_id)}")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    schema = product_schema(html_text)
    if not schema:
        die(f"could not find public Product schema for product id {product_id}")
    aggregate = schema.get("offers") if isinstance(schema.get("offers"), dict) else {}
    offers = extract_offer_rows(html_text)
    history = extract_history_items(html_text)
    current = offers[0].get("price") if offers else aggregate.get("lowPrice")
    try:
        current = float(current) if current is not None else None
    except Exception:
        current = None
    high = offers[-1].get("price") if offers else aggregate.get("highPrice")
    try:
        high = float(high) if high is not None else None
    except Exception:
        high = None
    props = []
    for prop in schema.get("additionalProperty") or []:
        if isinstance(prop, dict):
            props.append({"name": prop.get("name"), "value": prop.get("value")})
    return clean_value(
        {
            "product_id": int(product_id),
            "title": schema.get("name"),
            "brand": (schema.get("brand") or {}).get("name") if isinstance(schema.get("brand"), dict) else None,
            "description": schema.get("description"),
            "image": schema.get("image"),
            "url": schema.get("url") or product_url(product_id),
            "category_path": breadcrumb_schema(html_text),
            "properties": props,
            "current_lowest_price": current,
            "current_lowest_price_display": money(current),
            "current_highest_price": high,
            "price_spread": round(high - current, 2) if high is not None and current is not None else None,
            "offer_count": len(offers) or aggregate.get("offerCount"),
            "offers": offers,
            "history_summary": history_summary(history, days, current),
            "history_points_total": len(history),
            "elapsed_ms": elapsed_ms,
            "fetched_at": now_iso(),
            "source": "PriceSpy NZ",
        }
    )


def search_products(args: argparse.Namespace, *, effective_limit: int | None = None) -> dict[str, Any]:
    cid = category_id(args.category, args.query)
    limit = effective_limit or args.limit
    params: dict[str, Any] = {}
    if args.query:
        params["query"] = args.query
    if cid:
        params["category"] = cid
    started = time.perf_counter()
    html_text = request_text("/search", params)
    products = extract_product_cards(html_text)
    warnings: list[str] = []
    if not products:
        warnings.append("no structured PriceSpy product cards found in the public page")
    min_price = getattr(args, "min_price", None)
    max_price = getattr(args, "max_price", None)
    if min_price is not None:
        products = [p for p in products if p.get("current_price") is not None and float(p["current_price"]) >= min_price]
    if max_price is not None:
        products = [p for p in products if p.get("current_price") is not None and float(p["current_price"]) <= max_price]
    products = products[: max(1, limit)]
    return {
        "query": args.query,
        "category_id": cid,
        "category": args.category,
        "count": len(products),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "fetched_at": now_iso(),
        "warnings": warnings,
        "products": products,
        "source": "PriceSpy NZ",
    }


def cmd_search(args: argparse.Namespace) -> None:
    emit(search_products(args), args.json)


def cmd_product(args: argparse.Namespace) -> None:
    data = product_detail(parse_product_id(args.product_id), days=30)
    emit(data, args.json)


def cmd_cheapest(args: argparse.Namespace) -> None:
    search_args = argparse.Namespace(
        query=args.query,
        category=args.category,
        limit=args.limit,
        min_price=None,
        max_price=None,
    )
    data = search_products(search_args, effective_limit=max(args.limit, 30))
    priced = [p for p in data["products"] if p.get("current_price") is not None]
    if not priced:
        die(f"no priced PriceSpy results found for {args.query!r}")
    winner = min(priced, key=lambda p: float(p["current_price"]))
    detail = product_detail(str(winner["product_id"]), days=30)
    out = {
        "query": args.query,
        "category_id": data.get("category_id"),
        "fetched_at": now_iso(),
        "cheapest": winner,
        "product_detail": {
            "offer_count": detail.get("offer_count"),
            "price_spread": detail.get("price_spread"),
            "offers": detail.get("offers"),
            "history_summary": detail.get("history_summary"),
            "history_points_total": detail.get("history_points_total"),
        },
        "source": "PriceSpy NZ",
    }
    emit(out, args.json)


def cmd_history(args: argparse.Namespace) -> None:
    data = product_detail(parse_product_id(args.product_id), days=args.days)
    html_text = request_text(f"/product.php?p={urllib.parse.quote(str(data['product_id']))}")
    history = filter_history(extract_history_items(html_text), args.days)
    out = {
        "product_id": data.get("product_id"),
        "title": data.get("title"),
        "current_lowest_price": data.get("current_lowest_price"),
        "current_lowest_price_display": data.get("current_lowest_price_display"),
        "summary": data.get("history_summary"),
        "count": len(history),
        "history": history,
        "source": "PriceSpy NZ",
        "fetched_at": now_iso(),
    }
    emit(out, args.json)


def cmd_categories(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    html_text = request_text("/categories")
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for m in re.finditer(r'href="/category\.php\?k=([0-9]+)">([^<]+)', html_text):
        cid = int(m.group(1))
        if cid in seen:
            continue
        seen.add(cid)
        name = html.unescape(m.group(2)).strip()
        rows.append({"id": cid, "name": name})
    if args.query:
        needle = args.query.lower()
        rows = [r for r in rows if needle in r["name"].lower()]
    rows = sorted(rows, key=lambda r: r["name"].lower())
    out = {
        "count": len(rows[: args.limit]),
        "total_count": len(rows),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "categories": rows[: args.limit],
        "source": "PriceSpy NZ",
    }
    emit(out, args.json)


def cmd_trending(args: argparse.Namespace) -> None:
    cid = category_id(args.category or "tvs")
    seed_args = argparse.Namespace(query="", category=str(cid), limit=max(args.limit * 3, args.limit), min_price=None, max_price=None)
    seed = search_products(seed_args, effective_limit=max(args.limit * 3, args.limit))
    moves: list[dict[str, Any]] = []
    for product in seed.get("products", [])[: max(args.limit * 3, args.limit)]:
        if not product.get("product_id"):
            continue
        try:
            detail = product_detail(str(product["product_id"]), days=args.days)
        except SystemExit:
            continue
        summary = detail.get("history_summary") or {}
        if summary.get("change_amount") is None:
            continue
        direction = summary.get("direction")
        if args.direction in {"down", "up"} and direction != args.direction:
            continue
        if args.direction == "down":
            score = -(summary.get("change_amount") or 0)
        elif args.direction == "up":
            score = summary.get("change_amount") or 0
        else:
            score = abs(summary.get("change_amount") or 0)
        row = {
            "product_id": product.get("product_id"),
            "title": product.get("title"),
            "brand": product.get("brand"),
            "category": product.get("category"),
            "current_lowest_price": detail.get("current_lowest_price"),
            "current_lowest_price_display": detail.get("current_lowest_price_display"),
            "history_summary": summary,
            "product_url": product.get("product_url"),
            "source": "PriceSpy NZ",
            "_score": score,
        }
        moves.append(row)
    moves = sorted(moves, key=lambda r: r["_score"], reverse=True)[: args.limit]
    for row in moves:
        row.pop("_score", None)
    out = {
        "category_id": cid,
        "direction": args.direction,
        "days": args.days,
        "count": len(moves),
        "fetched_at": now_iso(),
        "trending": moves,
        "warnings": ["sampled from the first PriceSpy category/search results, not a full category crawl"],
        "source": "PriceSpy NZ",
    }
    emit(out, args.json)


def print_products(data: dict[str, Any]) -> None:
    print(f"PriceSpy NZ search: {data.get('count')} result(s) in {data.get('elapsed_ms')} ms")
    if data.get("category_id"):
        print(f"Category id: {data.get('category_id')}")
    for warning in data.get("warnings") or []:
        print(f"Warning: {warning}")
    print()
    for item in data.get("products") or []:
        print(f"{item.get('product_id')}  {item.get('title')}")
        bits = [
            item.get("current_price_display"),
            f"at {item.get('merchant')}" if item.get("merchant") else None,
            f"{item.get('store_count')} stores" if item.get("store_count") else None,
            f"{item.get('price_drop_percent')}% drop" if item.get("price_drop_percent") else None,
        ]
        print("  " + " | ".join(str(x) for x in bits if x))
        props = ", ".join(item.get("core_properties") or [])
        if props:
            print(f"  {props}")
        print(f"  {item.get('product_url')}")
        print()


def print_product(data: dict[str, Any]) -> None:
    print(f"{data.get('product_id')}  {data.get('title')}")
    print(f"PriceSpy NZ: {data.get('current_lowest_price_display')} low, {data.get('offer_count')} offer(s)")
    if data.get("price_spread") is not None:
        print(f"Spread: {money(data.get('price_spread'))}")
    summary = data.get("history_summary") or {}
    if summary.get("direction") and summary.get("direction") != "unknown":
        change = change_money(summary)
        pct = f"{summary.get('change_percent')}%" if summary.get("change_percent") is not None else "-"
        print(f"Last {summary.get('days')} days: {summary.get('direction')} {change} ({pct}), {summary.get('history_points')} history point(s)")
    print(data.get("url"))
    print()
    for offer in data.get("offers") or []:
        print(f"{offer.get('price_display')}  {offer.get('merchant')}  {offer.get('stock_status') or ''}")
        if offer.get("offer_name"):
            print(f"  {offer.get('offer_name')}")
        if offer.get("url"):
            print(f"  {offer.get('url')}")


def print_cheapest(data: dict[str, Any]) -> None:
    item = data.get("cheapest") or {}
    detail = data.get("product_detail") or {}
    print(f"Cheapest PriceSpy NZ match for {data.get('query')!r}:")
    print(f"{item.get('product_id')}  {item.get('title')}")
    print(f"{item.get('current_price_display')} at {item.get('merchant')} ({detail.get('offer_count')} offer(s))")
    if detail.get("price_spread") is not None:
        print(f"Store spread: {money(detail.get('price_spread'))}")
    summary = detail.get("history_summary") or {}
    if summary.get("direction") != "unknown":
        change = change_money(summary)
        pct = f"{summary.get('change_percent')}%" if summary.get("change_percent") is not None else "-"
        print(f"Last {summary.get('days')} days: {summary.get('direction')} {change} ({pct})")
    print(item.get("product_url"))


def print_history(data: dict[str, Any]) -> None:
    print(f"{data.get('product_id')}  {data.get('title')}")
    summary = data.get("summary") or {}
    print(f"Current lowest: {data.get('current_lowest_price_display')}")
    if summary.get("direction") != "unknown":
        change = change_money(summary)
        pct = f"{summary.get('change_percent')}%" if summary.get("change_percent") is not None else "-"
        print(f"Last {summary.get('days')} days: {summary.get('direction')} {change} ({pct}); {summary.get('history_points')} point(s)")
    print()
    for item in (data.get("history") or [])[-20:]:
        print(f"{str(item.get('date') or '')[:10]}  {item.get('price_display')}  {item.get('merchant')}  {item.get('offer_name') or ''}")


def print_categories(data: dict[str, Any]) -> None:
    print(f"PriceSpy NZ categories: showing {data.get('count')} of {data.get('total_count')}")
    for row in data.get("categories") or []:
        print(f"{row.get('id'):>5}  {row.get('name')}")


def print_trending(data: dict[str, Any]) -> None:
    print(f"PriceSpy NZ category {data.get('category_id')} trending {data.get('direction')} over {data.get('days')} days")
    for warning in data.get("warnings") or []:
        print(f"Warning: {warning}")
    print()
    for item in data.get("trending") or []:
        summary = item.get("history_summary") or {}
        change = change_money(summary)
        pct = f"{summary.get('change_percent')}%" if summary.get("change_percent") is not None else "-"
        print(f"{item.get('product_id')}  {item.get('title')}")
        print(f"  {item.get('current_lowest_price_display')} | {summary.get('direction')} {change} ({pct})")
        print(f"  {item.get('product_url')}")


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(clean_value(data), indent=2, ensure_ascii=False))
    elif "products" in data:
        print_products(data)
    elif "cheapest" in data:
        print_cheapest(data)
    elif "history" in data:
        print_history(data)
    elif "trending" in data:
        print_trending(data)
    elif "categories" in data:
        print_categories(data)
    elif "offers" in data:
        print_product(data)
    else:
        print(json.dumps(clean_value(data), indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight read-only NZ electronics/appliance price comparison CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search PriceSpy NZ product cards")
    sp.add_argument("query")
    sp.add_argument("--category", help="numeric PriceSpy category id or alias such as tvs, phones, laptops")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--max-price", type=float)
    sp.add_argument("--min-price", type=float)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("product", help="fetch one PriceSpy NZ product with merchant offers")
    sp.add_argument("product_id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser("cheapest", help="find the cheapest current PriceSpy NZ match for a query")
    sp.add_argument("query")
    sp.add_argument("--category", help="numeric PriceSpy category id or alias such as tvs, phones, laptops")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cheapest)

    sp = sub.add_parser("history", help="fetch PriceSpy NZ price-history points for a product")
    sp.add_argument("product_id")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("trending", help="sample products with notable PriceSpy NZ price moves")
    sp.add_argument("--category", default="tvs", help="numeric PriceSpy category id or alias; default: tvs")
    sp.add_argument("--direction", choices=["down", "up", "any"], default="down")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_trending)

    sp = sub.add_parser("categories", help="list/search PriceSpy NZ product categories")
    sp.add_argument("--query", help="filter category names")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "limit", 1) is not None and getattr(args, "limit", 1) < 1:
        die("--limit must be at least 1")
    if getattr(args, "days", 1) is not None and getattr(args, "days", 1) < 1:
        die("--days must be at least 1")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
