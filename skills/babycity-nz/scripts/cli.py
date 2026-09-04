#!/usr/bin/env python3
"""Read-only storefront HTML search, product detail, and store-page CLI."""
from __future__ import annotations

import argparse
import html as html_lib
import json
import math
import re
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
    except (urllib.error.URLError, TimeoutError) as exc:
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
        if isinstance(value, str):
            value = value.replace(",", "")
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if cents:
        result /= 100
    return round(result, 2) if math.isfinite(result) and result >= 0 else None


def slugify_handle(text: str) -> str:
    text = html_lib.unescape(text).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def parse_attributes(tag: str) -> dict[str, str]:
    return {match.group(1): html_lib.unescape(match.group(2)) for match in re.finditer(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)="([^"]*)"', tag)}


def parse_search_page(html: str, limit: int) -> list[dict[str, Any]]:
    starts = list(re.finditer(r'<div class="col tp-product-item[^>]*data-product-template-id="(\d+)">', html, re.DOTALL))
    if not starts:
        raise StorefrontError("unexpected search page shape")
    products: list[dict[str, Any]] = []
    for index, match in enumerate(starts):
        if len(products) >= limit:
            break
        start = match.start()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        card = html[start:end]
        template_id = int(match.group(1))
        hidden = re.search(r'<input[^>]*name="product_id"[^>]*value="(\d+)"', card, re.DOTALL)
        title_match = re.search(r'<a[^>]*class="[^"]*tp-link-dark[^"]*"[^>]*title="([^"]+)"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', card, re.DOTALL)
        price_match = re.search(r'<span class="oe_currency_value">([0-9][0-9,]*(?:\.[0-9]{1,2})?)</span>', card)
        if not hidden or not title_match or not price_match:
            raise StorefrontError("unexpected search result shape")
        title = html_lib.unescape(title_match.group(1)).strip()
        href = html_lib.unescape(title_match.group(2)).strip()
        price = amount(price_match.group(1))
        if price is None:
            raise StorefrontError("unexpected search result price")
        image_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*>', card, re.DOTALL)
        image_url = html_lib.unescape(image_match.group(1)).strip() if image_match else ""
        products.append({
            "id": int(hidden.group(1)),
            "handle": clean_handle(href),
            "title": title,
            "url": product_lookup_url(href),
            "price_min": price,
            "price_max": price,
            "compare_at_price_min": None,
            "available": True,
            "image": image_url,
            "template_id": template_id,
        })
    if not products:
        raise StorefrontError("unexpected search page shape")
    return products


def parse_product_page(html: str, requested_handle: str | None) -> dict[str, Any]:
    title_match = re.search(r'<h1 class="h3[^"]*">([^<]+)</h1>', html, re.DOTALL)
    product_id_match = re.search(r'<input[^>]*name="product_id"[^>]*value="(\d+)"', html, re.DOTALL)
    product_type_match = re.search(r'<input[^>]*name="product_type"[^>]*value="([^"]+)"', html, re.DOTALL)
    price_match = re.search(r'<span class="product-price"[^>]*>.*?<span class="oe_currency_value">([0-9][0-9,]*(?:\.[0-9]{1,2})?)</span>', html, re.DOTALL)
    if not title_match or not product_id_match or not price_match:
        raise StorefrontError("unexpected product page shape")
    title = html_lib.unescape(title_match.group(1)).strip()
    price = amount(price_match.group(1))
    if price is None:
        raise StorefrontError("unexpected product page price")
    checked_inputs = []
    for input_match in re.finditer(r'<input\b[^>]*class="[^"]*js_variant_change[^"]*"[^>]*>', html, re.DOTALL):
        tag = input_match.group(0)
        attrs = parse_attributes(tag)
        if attrs.get("checked") != "True":
            continue
        checked_inputs.append(attrs)
    options = [attrs.get("data-value-name") or attrs.get("title") for attrs in checked_inputs if attrs.get("data-value-name") or attrs.get("title")]
    if not options:
        options = [title]
    image_urls = []
    for img_match in re.finditer(r'<img[^>]*src="([^"]+)"[^>]*>', html, re.DOTALL):
        src = html_lib.unescape(img_match.group(1)).strip()
        if "/web/image/product" in src:
            image_urls.append(src)
    if not image_urls:
        image_urls = []
    available = "Add to Cart" in html and "disabled" not in html.lower()
    canonical_match = re.search(r'rel="canonical" href="([^"]+)"', html)
    if canonical_match:
        canonical_url = html_lib.unescape(canonical_match.group(1)).strip()
        if not is_allowed_storefront_url(canonical_url):
            raise StorefrontError("unexpected product canonical URL")
        handle = clean_handle(canonical_url)
    else:
        handle = requested_handle or slugify_handle(title)
        canonical_url = absolute_product_url(handle)
    variant = {
        "id": int(product_id_match.group(1)),
        "title": title,
        "sku": "",
        "price": price,
        "compare_at_price": None,
        "available": available,
        "option1": options[0],
        "option2": options[1] if len(options) > 1 else None,
        "option3": options[2] if len(options) > 2 else None,
    }
    return {
        "id": int(product_id_match.group(1)),
        "handle": handle,
        "title": title,
        "type": product_type_match.group(1) if product_type_match else "",
        "vendor": "",
        "price": price,
        "compare_at_price": None,
        "available": available,
        "variants": [variant],
        "images": image_urls,
        "canonical_url": canonical_url,
    }


def clean_handle(value: str) -> str:
    text = value.strip()
    if not text:
        raise StorefrontError("product must be a valid handle or storefront /shop/<slug> URL")
    text = text.removesuffix(".js")
    if "://" in text or text.startswith("/"):
        parsed = urllib.parse.urlparse(text if "://" in text else urllib.parse.urljoin(BASE_URL, text))
        base_host = urllib.parse.urlparse(BASE_URL).hostname or ""
        bare_host = base_host.removeprefix("www.")
        if parsed.hostname not in {base_host, bare_host, "www." + bare_host}:
            raise StorefrontError("product URL must use the configured storefront")
        path = parsed.path.rstrip("/")
        if path.startswith("/shop/"):
            text = path.split("/shop/", 1)[1]
        elif path.startswith("/products/"):
            text = path.split("/products/", 1)[1]
        else:
            raise StorefrontError("product URL must use the configured storefront product paths")
    else:
        text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    text = urllib.parse.unquote(text)
    if "/" in text or not HANDLE_RE.fullmatch(text):
        raise StorefrontError("product must be a valid handle or storefront /shop/<slug> URL")
    return text


def product_lookup_url(value: str) -> str:
    text = value.strip()
    if "://" in text or text.startswith("/"):
        parsed = urllib.parse.urlparse(text if "://" in text else urllib.parse.urljoin(BASE_URL, text))
        base_host = urllib.parse.urlparse(BASE_URL).hostname or ""
        bare_host = base_host.removeprefix("www.")
        if parsed.hostname not in {base_host, bare_host, "www." + bare_host}:
            raise StorefrontError("product URL must use the configured storefront")
        path = parsed.path.rstrip("/")
        if path.startswith("/shop/"):
            return parsed._replace(path=path).geturl()
        if path.startswith("/products/"):
            return absolute_product_url(clean_handle(path))
        raise StorefrontError("product URL must use the configured storefront product paths")
    handle = clean_handle(text)
    return absolute_product_url(handle)


def absolute_product_url(handle: str) -> str:
    return f"{BASE_URL}/shop/{urllib.parse.quote(handle, safe='-')}"


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
        "url": raw.get("canonical_url") or absolute_product_url(handle),
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
    title = str(raw.get("title") or "").strip()
    price_min = amount(raw.get("price_min", raw.get("price")))
    if raw.get("id") is None or not handle or not title or price_min is None:
        raise StorefrontError("unexpected predictive-search product shape")
    compare_at = amount(raw.get("compare_at_price_min"))
    return {
        "id": raw.get("id"),
        "title": title,
        "handle": handle,
        "url": raw.get("url") or absolute_product_url(handle),
        "vendor": raw.get("vendor") or "",
        "product_type": raw.get("type") or "",
        "price_min": price_min,
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
    endpoint = BASE_URL + "/shop?search=" + urllib.parse.quote(query)
    body, source_url = fetch(endpoint, timeout, "text/html")
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorefrontError(f"invalid HTML from {source_url}") from exc
    raw_products = parse_search_page(html, limit)
    products = [normalize_search(item) for item in raw_products[:limit]]
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
    endpoint = product_lookup_url(value)
    requested_handle = None if ("://" in value or value.startswith("/")) else clean_handle(value)
    body, source_url = fetch(endpoint, timeout, "text/html")
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorefrontError(f"invalid HTML from {source_url}") from exc
    raw_product = parse_product_page(html, requested_handle)
    product = normalize_detail(raw_product)
    stamp = retrieved_at()
    return {
        "retailer": LABEL,
        "currency": "NZD",
        "price_basis": "current public storefront snapshot",
        "availability_scope": AVAILABILITY_SCOPE,
        "source_url": source_url,
        "retrieved_at": stamp,
        "product": product,
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
