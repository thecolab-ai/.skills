#!/usr/bin/env python3
"""Chemist Warehouse NZ read-only product lookup CLI.

Stdlib wrapper around the public searchapiv2 endpoints used by
chemistwarehouse.co.nz. No login, cart, checkout, account, or prescription
mutations.
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
from html.parser import HTMLParser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from typing import Any

BASE_API = "https://www.chemistwarehouse.co.nz/searchapiv2"
BASE_WEB = "https://www.chemistwarehouse.co.nz"
SOURCE = "chemistwarehouse-nz-searchapiv2"
ROOT_LOCATION = "//catalog01/en_AU/categories<{catalog01_chemnz}"


class HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(html.unescape(" ".join(self.parts)).split())


def die(message: str, code: int = 1) -> None:
    print(f"chemistwarehouse-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def api_url(path: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if v is not None}
    return BASE_API + path + "?" + urllib.parse.urlencode(clean, doseq=True)


def request_json(path: str, params: dict[str, Any], timeout: int = 25) -> tuple[Any, str]:
    url = api_url(path, params)
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Referer": BASE_WEB + "/",
    }
    try:
        # This searchapiv2 endpoint returns HTTP 500 when sent the full Chrome
        # Client-Hint / Sec-Fetch-* header set; a lean request (browser_headers
        # =False) returns real data. Let nzfetch own the UA but skip the hints.
        body, _ct, _final = nzfetch.fetch_bytes(url, headers=headers, timeout=timeout, accept="application/json,text/plain,*/*", browser_headers=False)
        raw = body.decode("utf-8", "replace")
        return json.loads(raw), url
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_dict(value: Any) -> dict[str, Any]:
    for item in as_list(value):
        if isinstance(item, dict):
            return item
    return {}


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def html_to_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parser = HTMLText()
    try:
        parser.feed(value)
        parser.close()
        return parser.text()
    except Exception:
        return " ".join(html.unescape(value).split())


def item_attributes(item: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for attr in as_list(item.get("attribute")):
        if not isinstance(attr, dict):
            continue
        name = attr.get("name")
        if not name:
            continue
        values = []
        for value in as_list(attr.get("value")):
            if isinstance(value, dict):
                values.append(value.get("value"))
            else:
                values.append(value)
        values = [v for v in values if v not in (None, "")]
        if values:
            attrs[str(name)] = values[0] if len(values) == 1 else values
    return attrs


def attr_value(attrs: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = attrs.get(name)
        if value not in (None, ""):
            return value
    return None


def detail_params(item: dict[str, Any]) -> str | None:
    for link in as_list(item.get("link")):
        if isinstance(link, dict) and link.get("type") == "detail" and link.get("url-params"):
            return str(link["url-params"])
    for link in as_list(item.get("link")):
        if isinstance(link, dict) and link.get("url-params"):
            return str(link["url-params"])
    return None


def normalize_product(source_item: dict[str, Any], *, include_description: bool = False) -> dict[str, Any]:
    attrs = item_attributes(source_item) if "attribute" in source_item else dict(source_item)
    product_id = str(attr_value(attrs, "secondid", "secondId") or source_item.get("id") or "")
    product = {
        "product_id": product_id,
        "name": attr_value(attrs, "name") or "",
        "brand": attr_value(attrs, "brand") or "",
        "price": to_float(attr_value(attrs, "price_cw_nz", "price")),
        "rrp": to_float(attr_value(attrs, "rrp_cw_nz", "rrp")),
        "currency": "NZD",
        "url": attr_value(attrs, "producturl"),
        "image": attr_value(attrs, "_imageurl", "_thumburl"),
        "thumbnail": attr_value(attrs, "_thumburl"),
        "is_prescription": to_bool(attr_value(attrs, "is_prescription")),
        "ams_schedule": to_int(attr_value(attrs, "ams_schedule")),
        "rating": {
            "stars": to_float(attr_value(attrs, "bv_star_rating")),
            "votes": to_int(attr_value(attrs, "bv_total_votes")),
        },
        "categories": {
            "l1": attr_value(attrs, "l1_category"),
            "l2": attr_value(attrs, "l2_category"),
            "l3": attr_value(attrs, "l3_category"),
            "name": attr_value(attrs, "categories"),
        },
        "splat": attr_value(attrs, "splat"),
    }
    params = detail_params(source_item)
    if params:
        product["detail_url_params"] = params
    description_html = attr_value(attrs, "description")
    if include_description and description_html:
        product["description"] = html_to_text(description_html)
        product["description_html"] = description_html
    return product


def search_items(payload: Any) -> tuple[int | None, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, []
    universes = payload.get("universes") if isinstance(payload.get("universes"), dict) else {}
    universe = first_dict(universes.get("universe"))
    section = universe.get("items-section") if isinstance(universe.get("items-section"), dict) else {}
    results = section.get("results") if isinstance(section.get("results"), dict) else {}
    total = to_int(results.get("total-items"))
    items = []
    item_block = section.get("items") if isinstance(section.get("items"), dict) else {}
    for item in as_list(item_block.get("item")):
        if isinstance(item, dict):
            items.append(item)
    return total, items


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def page_offset(page: int, limit: int) -> int:
    return (max(1, page) - 1) * max(1, limit)


def clamp_limit(limit: int) -> int:
    return min(max(1, limit), 100)


def category_token(category_id: str) -> str:
    text = str(category_id).strip().strip("{}")
    if not text:
        die("category ID is required")
    if text.isdigit():
        return "chemnz" + text
    return text


def short_category_id(catid: Any) -> str:
    if not catid:
        return ""
    matches = re.findall(r"chemnz(\d+)", str(catid))
    return matches[-1] if matches else str(catid)


def product_id_from_ref(ref: str) -> str:
    text = str(ref).strip()
    parsed = urllib.parse.urlparse(text)
    query = urllib.parse.parse_qs(parsed.query if parsed.scheme else text)
    if query.get("fh_secondid"):
        return query["fh_secondid"][0]
    if parsed.scheme:
        match = re.search(r"/buy/(\d+)(?:/|$)", parsed.path)
        if match:
            return match.group(1)
    if text.isdigit():
        return text
    match = re.search(r"\b(\d{3,})\b", text)
    if match:
        return match.group(1)
    die("product must be a numeric product ID or /buy/<id>/ product URL")


def cmd_suggest(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    limit = clamp_limit(args.limit)
    payload, url = request_json("/suggest", {"identifier": "nz", "search": args.term})
    keywords: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    groups = payload.get("suggestionGroups") if isinstance(payload, dict) else []
    for group in as_list(groups):
        if not isinstance(group, dict):
            continue
        index_name = group.get("indexName")
        suggestions = [s for s in as_list(group.get("suggestions")) if isinstance(s, dict)]
        if index_name == "1keywords":
            for item in suggestions[:limit]:
                keywords.append({"term": item.get("searchterm") or "", "total": to_int(item.get("nrResults"))})
        elif index_name == "2categories":
            for item in suggestions[:limit]:
                catid = item.get("catid")
                categories.append(
                    {
                        "name": item.get("mlValue") or "",
                        "category_id": short_category_id(catid),
                        "catid": catid,
                        "total": to_int(item.get("nrResults")),
                        "fh_location": item.get("fhLocation"),
                    }
                )
        elif index_name == "3products":
            for item in suggestions[:limit]:
                products.append(normalize_product(item))
    data = {
        "kind": "suggest",
        "source": SOURCE,
        "source_url": url,
        "query": args.term,
        "total": len(keywords) + len(categories) + len(products),
        "results": {
            "keywords": len(keywords),
            "categories": len(categories),
            "products": len(products),
        },
        "items": products,
        "groups": {
            "keywords": keywords,
            "categories": categories,
            "products": products,
        },
        "elapsed_ms": elapsed_ms(started),
    }
    emit(data, args.json)


def cmd_search(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    limit = clamp_limit(args.limit)
    page = max(1, args.page)
    location = ROOT_LOCATION + "/$s=" + args.term
    payload, url = request_json(
        "/search",
        {
            "identifier": "nz",
            "fh_location": location,
            "fh_start_index": page_offset(page, limit),
            "fh_view_size": limit,
        },
    )
    total, raw_items = search_items(payload)
    items = [normalize_product(item) for item in raw_items[:limit]]
    data = {
        "kind": "search",
        "source": SOURCE,
        "source_url": url,
        "query": args.term,
        "page": page,
        "limit": limit,
        "offset": page_offset(page, limit),
        "total": total,
        "results": len(items),
        "items": items,
        "elapsed_ms": elapsed_ms(started),
    }
    emit(data, args.json)


def cmd_category(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    limit = clamp_limit(args.limit)
    page = max(1, args.page)
    token = category_token(args.category_id)
    location = ROOT_LOCATION + f"/categories<{{{token}}}"
    payload, url = request_json(
        "/search",
        {
            "identifier": "nz",
            "fh_location": location,
            "fh_start_index": page_offset(page, limit),
            "fh_view_size": limit,
        },
    )
    total, raw_items = search_items(payload)
    items = [normalize_product(item) for item in raw_items[:limit]]
    data = {
        "kind": "category",
        "source": SOURCE,
        "source_url": url,
        "category_id": args.category_id,
        "category_token": token,
        "page": page,
        "limit": limit,
        "offset": page_offset(page, limit),
        "total": total,
        "results": len(items),
        "items": items,
        "elapsed_ms": elapsed_ms(started),
    }
    emit(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    product_id = product_id_from_ref(args.product)
    payload, url = request_json(
        "/search",
        {
            "identifier": "nz",
            "site": "cw_nz",
            "channel": "desktop",
            "fh_location": ROOT_LOCATION,
            "fh_start_index": 0,
            "fh_refview": "search",
            "fh_secondid": product_id,
            "fh_lister_pos": 1,
            "fh_modification": "",
        },
    )
    total, raw_items = search_items(payload)
    items = [normalize_product(item, include_description=True) for item in raw_items]
    if not items:
        die(f"product not found: {product_id}")
    data = {
        "kind": "product",
        "source": SOURCE,
        "source_url": url,
        "product_id": product_id,
        "total": total if total is not None else len(items),
        "results": len(items),
        "items": items,
        "elapsed_ms": elapsed_ms(started),
    }
    emit(data, args.json)


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def price_label(item: dict[str, Any]) -> str:
    price = item.get("price")
    label = money(price)
    rrp = item.get("rrp")
    if rrp is not None and rrp != price:
        label += f" (RRP {money(rrp)})"
    return label


def product_status(item: dict[str, Any]) -> str:
    bits = []
    if item.get("is_prescription") is True:
        bits.append("prescription")
    elif item.get("is_prescription") is False:
        bits.append("non-prescription")
    if item.get("ams_schedule") is not None:
        bits.append(f"schedule {item['ams_schedule']}")
    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
    if rating.get("stars") is not None:
        votes = rating.get("votes")
        bits.append(f"{rating['stars']:.1f} stars" + (f" ({votes})" if votes is not None else ""))
    return " | ".join(bits)


def print_product_line(item: dict[str, Any]) -> None:
    product_id = item.get("product_id") or ""
    name = item.get("name") or ""
    print(f"{product_id:>8}  {price_label(item):<22}  {name}".rstrip())
    status = product_status(item)
    if status:
        print(f"          {status}")
    if item.get("url"):
        print(f"          {item['url']}")


def print_suggest(data: dict[str, Any]) -> None:
    print(f"suggestions for {data.get('query')!r}: {data.get('total', 0)} ({data.get('elapsed_ms')} ms)")
    groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
    keywords = groups.get("keywords") if isinstance(groups.get("keywords"), list) else []
    categories = groups.get("categories") if isinstance(groups.get("categories"), list) else []
    products = groups.get("products") if isinstance(groups.get("products"), list) else []
    if keywords:
        print("Keywords:")
        for item in keywords:
            suffix = f" ({item.get('total')})" if item.get("total") is not None else ""
            print(f"  {item.get('term', '')}{suffix}")
    if categories:
        print("Categories:")
        for item in categories:
            suffix = f" ({item.get('total')})" if item.get("total") is not None else ""
            category_id = item.get("category_id") or item.get("catid") or ""
            print(f"  {category_id}  {item.get('name', '')}{suffix}")
    if products:
        print("Products:")
        for item in products:
            print_product_line(item)


def print_items(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("category_id") or data.get("product_id") or "items"
    total = data.get("total")
    total_label = "unknown total" if total is None else f"{total} total"
    print(f"{data.get('kind')}: {label!r}, {data.get('results', 0)} shown, {total_label} ({data.get('elapsed_ms')} ms)")
    for item in data.get("items") or []:
        print_product_line(item)


def print_detail(data: dict[str, Any]) -> None:
    item = (data.get("items") or [{}])[0]
    print_product_line(item)
    categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
    category_name = categories.get("name")
    if category_name:
        print(f"Category: {category_name}")
    description = item.get("description")
    if description:
        clipped = description[:360] + "..." if len(description) > 360 else description
        print(f"Description: {clipped}")
    if item.get("image"):
        print(f"Image: {item['image']}")


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if data.get("kind") == "suggest":
        print_suggest(data)
    elif data.get("kind") == "product":
        print_detail(data)
    else:
        print_items(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chemist Warehouse NZ live product lookup CLI (public read-only endpoints, no login)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("suggest", help="query keyword, category, and product suggestions")
    sp.add_argument("term")
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_suggest)

    sp = sub.add_parser("search", help="search live product listings by term")
    sp.add_argument("term")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1, help="one-based results page")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("category", help="list products in a Chemist Warehouse NZ category ID")
    sp.add_argument("category_id")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1, help="one-based results page")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_category)

    sp = sub.add_parser("product", help="fetch product detail by product ID or /buy/<id>/ URL")
    sp.add_argument("product")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
