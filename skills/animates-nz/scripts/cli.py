#!/usr/bin/env python3
"""Read-only Animates NZ product search and JSON-LD detail CLI."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://www.animates.co.nz"
SEARCH_API = BASE + "/rest/default/V1/search"
UA = "TheColab-animates-nz/1.0 (+https://github.com/thecolab-ai/.skills)"
MAX_RESULTS = 10
MAX_SEARCH_BYTES = 1_000_000
MAX_PAGE_BYTES = 1_000_000
MAX_TIMEOUT = 60


class CliError(RuntimeError):
    pass


def is_allowed_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"animates.co.nz", "www.animates.co.nz"}
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_url(newurl):
            raise CliError("refusing redirect outside the Animates HTTPS storefront")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_text(url: str, timeout: int = 10, max_bytes: int = MAX_PAGE_BYTES) -> tuple[str, str]:
    if not is_allowed_url(url):
        raise CliError("refusing request outside the Animates HTTPS storefront")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/json", "Accept-Language": "en-NZ,en;q=0.9"},
        method="GET",
    )
    try:
        with urllib.request.build_opener(StorefrontRedirectHandler()).open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not is_allowed_url(final_url):
                raise CliError("refusing response outside the Animates HTTPS storefront")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise CliError(f"response from {url} exceeded the {max_bytes}-byte safety limit")
            return body.decode("utf-8", "replace"), final_url
    except urllib.error.HTTPError as exc:
        raise CliError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"network error calling {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CliError(f"request timed out after {timeout}s: {url}") from exc


def as_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return round(number, 2) if math.isfinite(number) and number >= 0 else None


def json_ld_objects(markup: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    pattern = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
    for match in pattern.finditer(markup):
        try:
            value = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = value.get("@graph", []) if isinstance(value, dict) and isinstance(value.get("@graph"), list) else [value]
        objects.extend(item for item in candidates if isinstance(item, dict))
    return objects


def parse_product(markup: str, source_url: str) -> dict[str, Any] | None:
    product = next((item for item in json_ld_objects(markup) if item.get("@type") == "Product"), None)
    if not product:
        return None
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), {})
    if not isinstance(offers, dict):
        offers = {}
    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    availability = str(offers.get("availability") or "").rsplit("/", 1)[-1] or None
    return {
        "id": product.get("@id") or source_url,
        "sku": product.get("sku"),
        "mpn": product.get("mpn"),
        "name": product.get("name"),
        "brand": brand,
        "category": product.get("category"),
        "description": re.sub(r"\s+", " ", html.unescape(str(product.get("description") or ""))).strip(),
        "image": image,
        "price": as_number(offers.get("price")),
        "currency": offers.get("priceCurrency") or "NZD",
        "availability": availability,
        "in_stock": availability == "InStock" if availability else None,
        "source_url": offers.get("url") or product.get("@id") or source_url,
    }


def search_ids(query: str, limit: int, timeout: int) -> tuple[list[str], int | None, str]:
    if not query.strip():
        raise CliError("search query must not be empty")
    params = {
        "searchCriteria[requestName]": "quick_search_container",
        "searchCriteria[filterGroups][0][filters][0][field]": "search_term",
        "searchCriteria[filterGroups][0][filters][0][value]": query,
        "searchCriteria[pageSize]": limit,
        "searchCriteria[currentPage]": 1,
    }
    url = SEARCH_API + "?" + urllib.parse.urlencode(params)
    text, final_url = fetch_text(url, timeout, MAX_SEARCH_BYTES)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON from {final_url}") from exc
    ids = [str(item["id"]) for item in data.get("items", []) if isinstance(item, dict) and item.get("id") is not None]
    total = data.get("total_count")
    return ids[:limit], int(total) if isinstance(total, int) else None, final_url


def product_url(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        if not is_allowed_url(value):
            raise CliError("product URL must be on animates.co.nz")
        return value
    if value.isdigit():
        return f"{BASE}/catalog/product/view/id/{value}"
    if value.startswith("/") or value.endswith(".html"):
        return urllib.parse.urljoin(BASE, value)
    raise CliError("product must be an Animates URL, .html path, or numeric product ID")


def get_product(value: str, timeout: int) -> tuple[dict[str, Any], str]:
    url = product_url(value)
    markup, final_url = fetch_text(url, timeout)
    product = parse_product(markup, final_url)
    if not product or not product.get("name") or product.get("price") is None:
        raise CliError(f"no complete Product JSON-LD found at {final_url}; the page may have changed")
    product["source_url"] = final_url
    return product, final_url


def search(query: str, limit: int, timeout: int) -> dict[str, Any]:
    ids, total, search_url = search_ids(query, limit, timeout)
    products: list[dict[str, Any]] = []
    warnings: list[str] = []
    for product_id in ids:
        try:
            product, _ = get_product(product_id, timeout)
            product["product_id"] = product_id
            products.append(product)
        except CliError as exc:
            warnings.append(f"product {product_id}: {exc}")
    if ids and not products:
        raise CliError("search returned IDs but no product detail pages could be parsed")
    return {
        "retailer": "Animates NZ",
        "command": "search",
        "query": query,
        "count": len(products),
        "total": total,
        "results": products,
        "warnings": warnings,
        "source_url": search_url,
        "retrieved_at": timestamp(),
    }


def detail(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {"retailer": "Animates NZ", "command": "product", "product": product, "source_url": source_url, "retrieved_at": timestamp()}


def snapshot(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {
        "retailer": "Animates NZ",
        "command": "price-snapshot",
        "sku": product.get("sku"),
        "name": product.get("name"),
        "price": product.get("price"),
        "currency": product.get("currency"),
        "availability": product.get("availability"),
        "source_url": source_url,
        "retrieved_at": timestamp(),
    }


def emit(data: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if data["command"] == "search":
        print(f"{data['count']} Animates result(s) for {data['query']!r}")
        for item in data["results"]:
            print(f"{item.get('sku') or '-':>10}  ${item.get('price', 0):.2f}  {item.get('name')}")
            print(f"            {item.get('source_url')}")
    elif data["command"] == "product":
        item = data["product"]
        print(f"{item.get('name')}\n${item.get('price', 0):.2f} {item.get('currency')} | {item.get('availability')}\n{data['source_url']}")
    else:
        print(f"{data.get('name')}: ${data.get('price', 0):.2f} {data.get('currency')} | {data.get('availability')}\n{data['source_url']}")


def positive_limit(value: str) -> int:
    number = int(value)
    if not 1 <= number <= MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_RESULTS}")
    return number


def timeout_arg(value: str) -> int:
    number = int(value)
    if not 1 <= number <= MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_TIMEOUT}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="animates-nz", description="Read-only Animates NZ product search and price snapshots.")
    parser.add_argument("--timeout", type=timeout_arg, default=10, help=f"network timeout in seconds (1-{MAX_TIMEOUT}; default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)
    search_parser = sub.add_parser("search", help="search products using public Magento search and detail pages")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=positive_limit, default=5)
    search_parser.add_argument("--json", action="store_true")
    for command, help_text in (("product", "fetch a product URL or numeric ID"), ("price-snapshot", "capture current public price and availability")):
        item_parser = sub.add_parser(command, help=help_text)
        item_parser.add_argument("product")
        item_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "search":
            data = search(args.query, args.limit, args.timeout)
        elif args.command == "product":
            data = detail(args.product, args.timeout)
        else:
            data = snapshot(args.product, args.timeout)
        emit(data, args.json)
        return 0
    except (CliError, ValueError) as exc:
        print(f"animates-nz: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
