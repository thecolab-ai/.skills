#!/usr/bin/env python3
"""Read-only Shopify storefront search, product detail, and store-page CLI."""
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

CONFIGS = {
    "babycity-nz": {
        "label": "babycity NZ",
        "base": "https://www.babycity.co.nz",
        "store_path": "/pages/store-locator",
    },
    "dimples-nz": {
        "label": "Dimples NZ",
        "base": "https://www.dimples.co.nz",
        "store_path": "/pages/store-locator",
    },
    "nature-baby-nz": {
        "label": "Nature Baby NZ",
        "base": "https://www.naturebaby.co.nz",
        "store_path": "/pages/store-details",
    },
    "baby-on-the-move-nz": {
        "label": "Baby On The Move NZ",
        "base": "https://babyonthemove.co.nz",
        "store_path": "/pages/store-locations",
    },
}
SKILL_NAME = Path(__file__).resolve().parents[1].name
if SKILL_NAME not in CONFIGS:
    raise RuntimeError(f"unsupported skill directory: {SKILL_NAME}")
CONFIG = CONFIGS[SKILL_NAME]
BASE_URL = str(CONFIG["base"])
LABEL = str(CONFIG["label"])
STORE_URL = BASE_URL + str(CONFIG["store_path"])
USER_AGENT = f"TheColab-{SKILL_NAME}/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 10
DEFAULT_LIMIT = 6
MAX_LIMIT = 10
MAX_RESPONSE_BYTES = 5_000_000
AVAILABILITY_SCOPE = "online storefront, not store stock"
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class StorefrontError(Exception):
    """Expected upstream or input failure."""


def is_allowed_storefront_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    base_host = urllib.parse.urlparse(BASE_URL).hostname or ""
    bare_host = base_host.removeprefix("www.")
    return parsed.scheme == "https" and parsed.hostname in {base_host, bare_host, "www." + bare_host} and parsed.username is None and parsed.password is None and port in (None, 443)


class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_storefront_url(newurl):
            raise StorefrontError("refusing redirect outside the configured HTTPS storefront")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def positive_bounded(value: str, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= number <= maximum:
        raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
    return number


def limit_arg(value: str) -> int:
    return positive_bounded(value, MAX_LIMIT)


def timeout_arg(value: str) -> int:
    return positive_bounded(value, 30)


def fetch(url: str, timeout: int, accept: str) -> tuple[bytes, str]:
    if not is_allowed_storefront_url(url):
        raise StorefrontError("refusing request outside the configured HTTPS storefront")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": accept,
            "Accept-Language": "en-NZ,en;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.build_opener(StorefrontRedirectHandler()).open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not is_allowed_storefront_url(final_url):
                raise StorefrontError("refusing redirect outside the configured storefront")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise StorefrontError("upstream response exceeded the 5 MB safety limit")
            return body, final_url
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise StorefrontError(f"not found (HTTP 404): {url}") from exc
        raise StorefrontError(f"upstream HTTP {exc.code}: {url}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        reason = getattr(exc, "reason", exc)
        raise StorefrontError(f"network error calling {url}: {reason}") from exc


def fetch_json(url: str, timeout: int) -> tuple[Any, str]:
    body, final_url = fetch(url, timeout, "application/json")
    try:
        return json.loads(body.decode("utf-8")), final_url
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorefrontError(f"invalid JSON from {final_url}") from exc


def amount(value: Any, *, cents: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if cents:
        result /= 100
    return round(result, 2)


def clean_handle(value: str) -> str:
    text = value.strip()
    if "/products/" in text:
        parsed = urllib.parse.urlparse(text if "://" in text else "https://" + text.lstrip("/"))
        base_host = urllib.parse.urlparse(BASE_URL).hostname or ""
        bare_host = base_host.removeprefix("www.")
        if parsed.hostname not in {base_host, bare_host, "www." + bare_host}:
            raise StorefrontError("product URL must use the configured storefront")
        text = parsed.path.split("/products/", 1)[1]
    text = urllib.parse.unquote(text.split("?", 1)[0].split("#", 1)[0].strip("/"))
    if text.endswith(".js"):
        text = text[:-3]
    if not HANDLE_RE.fullmatch(text):
        raise StorefrontError("product must be a valid handle or storefront /products/<handle> URL")
    return text


def absolute_product_url(handle: str) -> str:
    return f"{BASE_URL}/products/{urllib.parse.quote(handle, safe='-')}"


def normalize_variant(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or "",
        "sku": raw.get("sku") or "",
        "price": amount(raw.get("price"), cents=True),
        "compare_at_price": amount(raw.get("compare_at_price"), cents=True),
        "available_online": bool(raw.get("available")),
        "availability_scope": AVAILABILITY_SCOPE,
        "options": [raw.get(key) for key in ("option1", "option2", "option3") if raw.get(key) is not None],
    }


def normalize_detail(raw: dict[str, Any]) -> dict[str, Any]:
    handle = str(raw.get("handle") or "")
    title = str(raw.get("title") or "").strip()
    variants_value = raw.get("variants")
    product_price = amount(raw.get("price"), cents=True)
    if not handle or not title or raw.get("id") is None or product_price is None or not isinstance(variants_value, list) or not variants_value or not all(isinstance(item, dict) and item.get("id") is not None and amount(item.get("price"), cents=True) is not None for item in variants_value):
        raise StorefrontError("unexpected product response shape")
    variants = [normalize_variant(item) for item in variants_value if isinstance(item, dict)]
    images_value = raw.get("images")
    images = [str(item) for item in images_value if isinstance(item, str)] if isinstance(images_value, list) else []
    return {
        "id": raw.get("id"),
        "title": title,
        "handle": handle,
        "url": absolute_product_url(handle),
        "vendor": raw.get("vendor") or "",
        "product_type": raw.get("type") or "",
        "price": product_price,
        "compare_at_price": amount(raw.get("compare_at_price"), cents=True),
        "available_online": bool(raw.get("available")),
        "availability_scope": AVAILABILITY_SCOPE,
        "variants": variants,
        "images": images,
    }


def normalize_search(raw: dict[str, Any]) -> dict[str, Any]:
    handle = str(raw.get("handle") or "")
    compare_at = amount(raw.get("compare_at_price_min"))
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or "",
        "handle": handle,
        "url": absolute_product_url(handle),
        "vendor": raw.get("vendor") or "",
        "product_type": raw.get("type") or "",
        "price_min": amount(raw.get("price_min", raw.get("price"))),
        "price_max": amount(raw.get("price_max", raw.get("price"))),
        "compare_at_price_min": compare_at if compare_at and compare_at > 0 else None,
        "available_online": bool(raw.get("available")),
        "availability_scope": AVAILABILITY_SCOPE,
        "image_url": raw.get("image"),
    }


def search_products(query: str, limit: int, timeout: int) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise StorefrontError("search query must not be empty")
    params = {
        "q": query,
        "resources[type]": "product",
        "resources[limit]": limit,
        "resources[options][unavailable_products]": "last",
    }
    endpoint = BASE_URL + "/search/suggest.json?" + urllib.parse.urlencode(params)
    payload, source_url = fetch_json(endpoint, timeout)
    try:
        raw_products = payload["resources"]["results"]["products"]
    except (KeyError, TypeError) as exc:
        raise StorefrontError("unexpected predictive-search response shape") from exc
    if not isinstance(raw_products, list):
        raise StorefrontError("unexpected predictive-search products shape")
    products = [normalize_search(item) for item in raw_products[:limit] if isinstance(item, dict)]
    stamp = retrieved_at()
    return {
        "retailer": LABEL,
        "query": query,
        "count": len(products),
        "limit": limit,
        "currency": "NZD",
        "price_basis": "current public storefront snapshot",
        "availability_scope": AVAILABILITY_SCOPE,
        "source_url": source_url,
        "retrieved_at": stamp,
        "products": products,
    }


def product_detail(value: str, timeout: int) -> dict[str, Any]:
    handle = clean_handle(value)
    endpoint = absolute_product_url(handle) + ".js"
    payload, source_url = fetch_json(endpoint, timeout)
    if not isinstance(payload, dict):
        raise StorefrontError("unexpected product response shape")
    stamp = retrieved_at()
    return {
        "retailer": LABEL,
        "currency": "NZD",
        "price_basis": "current public storefront snapshot",
        "availability_scope": AVAILABILITY_SCOPE,
        "source_url": source_url,
        "retrieved_at": stamp,
        "product": normalize_detail(payload),
    }


class PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.in_title = False
        self.title = ""
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title" and not self.title and not self.title_parts:
            self.in_title = True
        if tag == "meta" and (attributes.get("name") or "").lower() == "description":
            self.description = attributes.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            if not self.title:
                self.title = " ".join(part for part in self.title_parts if part)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data.strip())


def store_page(timeout: int) -> dict[str, Any]:
    body, source_url = fetch(STORE_URL, timeout, "text/html")
    parser = PageMetadataParser()
    try:
        parser.feed(body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise StorefrontError(f"invalid HTML from {source_url}") from exc
    return {
        "retailer": LABEL,
        "store_page_url": source_url,
        "title": parser.title,
        "description": parser.description,
        "inventory_note": "This page identifies physical locations; online variant availability is not store stock.",
        "source_url": source_url,
        "retrieved_at": retrieved_at(),
    }


def emit(payload: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if "products" in payload:
        print(f"{payload['count']} {LABEL} product result(s) for {payload['query']!r}")
        for item in payload["products"]:
            low, high = item["price_min"], item["price_max"]
            price = "price unavailable" if low is None else f"NZ${low:.2f}" if low == high else f"NZ${low:.2f}–{high:.2f}"
            status = "available online" if item["available_online"] else "unavailable online"
            print(f"- {item['title']} — {price}; {status}\n  {item['url']}")
    elif "product" in payload:
        item = payload["product"]
        price = "price unavailable" if item["price"] is None else f"NZ${item['price']:.2f}"
        print(f"{item['title']} — {price}\n{item['url']}\nAvailability: {AVAILABILITY_SCOPE}")
        print(f"Variants: {len(item['variants'])}")
    else:
        print(f"{payload['title']}\n{payload['store_page_url']}\n{payload['description']}")
        print(payload["inventory_note"])
    print(f"Retrieved: {payload['retrieved_at']}\nSource: {payload['source_url']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SKILL_NAME, description=f"Read-only public product data from {LABEL}.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search public products")
    search.add_argument("query", help="product search terms")
    search.add_argument("--limit", type=limit_arg, default=DEFAULT_LIMIT, help=f"maximum results (1-{MAX_LIMIT})")
    search.add_argument("--timeout", type=timeout_arg, default=DEFAULT_TIMEOUT, help="network timeout seconds (1-30; default 10)")
    search.add_argument("--json", action="store_true", help="print machine-readable JSON")

    product = subparsers.add_parser("product", help="fetch a product by handle or product URL")
    product.add_argument("handle_or_url", help="product handle or storefront product URL")
    product.add_argument("--timeout", type=timeout_arg, default=DEFAULT_TIMEOUT, help="network timeout seconds (1-30; default 10)")
    product.add_argument("--json", action="store_true", help="print machine-readable JSON")

    stores = subparsers.add_parser("stores", help="fetch the retailer's verified public store page")
    stores.add_argument("--timeout", type=timeout_arg, default=DEFAULT_TIMEOUT, help="network timeout seconds (1-30; default 10)")
    stores.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "search":
            payload = search_products(args.query, args.limit, args.timeout)
        elif args.command == "product":
            payload = product_detail(args.handle_or_url, args.timeout)
        else:
            payload = store_page(args.timeout)
        emit(payload, args.json)
        return 0
    except StorefrontError as exc:
        print(f"{SKILL_NAME}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
