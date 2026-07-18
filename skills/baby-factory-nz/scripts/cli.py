#!/usr/bin/env python3
"""Read-only Baby Factory NZ HTML and JSON-LD product CLI."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://www.babyfactory.co.nz"
UA = "TheColab-baby-factory-nz/1.0 (+https://github.com/thecolab-ai/.skills)"
MAX_RESULTS = 20
MAX_PAGE_BYTES = 1_200_000
MAX_PAGE = 50
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
        and parsed.hostname in {"babyfactory.co.nz", "www.babyfactory.co.nz"}
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_url(newurl):
            raise CliError("refusing redirect outside the Baby Factory HTTPS storefront")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_text(url: str, timeout: int = 10) -> tuple[str, str]:
    if not is_allowed_url(url):
        raise CliError("refusing request outside the Baby Factory HTTPS storefront")
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-NZ,en;q=0.9"}, method="GET")
    try:
        with urllib.request.build_opener(StorefrontRedirectHandler()).open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not is_allowed_url(final_url):
                raise CliError("refusing response outside the Baby Factory HTTPS storefront")
            body = response.read(MAX_PAGE_BYTES + 1)
            if len(body) > MAX_PAGE_BYTES:
                raise CliError(f"response from {url} exceeded the {MAX_PAGE_BYTES}-byte safety limit")
            return body.decode("utf-8", "replace"), final_url
    except urllib.error.HTTPError as exc:
        raise CliError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"network error calling {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CliError(f"request timed out after {timeout}s: {url}") from exc


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def extract_category_state(markup: str) -> dict[str, Any]:
    match = re.search(r"window\.category\s*=\s*(\{.*?\});\s*</script>", markup, re.S)
    if not match:
        raise CliError("Baby Factory search state was not found; the public page may have changed")
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise CliError("Baby Factory search state contained invalid JSON") from exc
    return state if isinstance(state, dict) else {}


def image_url(raw: dict[str, Any]) -> str | None:
    images = raw.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict):
                for key in ("src", "url", "path"):
                    if image.get(key):
                        return urllib.parse.urljoin(BASE, str(image[key]))
            elif isinstance(image, str):
                return urllib.parse.urljoin(BASE, image)
    return None


def normalize_variant(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "barcode": raw.get("barcode"),
        "size": raw.get("size"),
        "price": number(raw.get("unitprice")),
        "regular_price": number(raw.get("baseunitprice")),
        "currency": raw.get("currency") or "NZD",
        "on_sale": bool(raw.get("saleprice")),
        "status": raw.get("status"),
    }


def normalize_search_item(raw: dict[str, Any]) -> dict[str, Any]:
    stylecolour_value = raw.get("stylecolour")
    stylecolour: dict[str, Any] = stylecolour_value if isinstance(stylecolour_value, dict) else {}
    variants_value = stylecolour.get("variants")
    variants = [normalize_variant(item) for item in variants_value if isinstance(item, dict)] if isinstance(variants_value, list) else []
    prices = [item["price"] for item in variants if item.get("price") is not None]
    regular = [item["regular_price"] for item in variants if item.get("regular_price") is not None]
    url_key = stylecolour.get("urlkey") or ""
    source_url = urllib.parse.urljoin(BASE, "/" + str(url_key).lstrip("/"))
    return {
        "id": raw.get("productid"),
        "style": raw.get("style"),
        "name": raw.get("description"),
        "brand": raw.get("label"),
        "colour": stylecolour.get("colour"),
        "price": min(prices) if prices else None,
        "regular_price": min(regular) if regular else None,
        "currency": variants[0].get("currency") if variants else "NZD",
        "on_sale": any(item.get("on_sale") for item in variants),
        "variants": variants,
        "image": image_url(stylecolour),
        "source_url": source_url if is_allowed_url(source_url) else None,
    }


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


def normalize_ld_product(raw: dict[str, Any], source_url: str) -> dict[str, Any]:
    brand = raw.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    offers_value = raw.get("offers")
    offers = offers_value if isinstance(offers_value, list) else [offers_value] if isinstance(offers_value, dict) else []
    normalized_offers = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
        normalized_offers.append({
            "sku": offer.get("sku"), "price": number(offer.get("price") or offer.get("lowPrice")),
            "high_price": number(offer.get("highPrice")), "currency": offer.get("priceCurrency") or "NZD",
            "availability": availability, "in_stock": availability == "InStock" if availability else None,
        })
    priced = [offer for offer in normalized_offers if offer.get("price") is not None]
    cheapest = min(priced, key=lambda offer: offer["price"]) if priced else {}
    image = raw.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    return {
        "sku": raw.get("sku"), "name": str(raw.get("name") or "").strip(), "brand": brand,
        "description": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(raw.get("description") or "")))).strip(),
        "image": image, "price": cheapest.get("price"), "currency": cheapest.get("currency") or "NZD",
        "availability": cheapest.get("availability"), "offers": normalized_offers,
        "source_url": raw.get("url") or source_url,
    }


def product_url(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        if not is_allowed_url(value):
            raise CliError("product URL must be on babyfactory.co.nz")
        return value
    slug = value.strip("/")
    if not slug:
        raise CliError("product URL or slug is required")
    return f"{BASE}/{urllib.parse.quote(slug, safe='-')}"


def get_product(value: str, timeout: int) -> tuple[dict[str, Any], str]:
    url = product_url(value)
    markup, final_url = fetch_text(url, timeout)
    raw = next((item for item in json_ld_objects(markup) if item.get("@type") == "Product"), None)
    if not raw:
        raise CliError(f"no Product JSON-LD found at {final_url}; the page may have changed")
    product = normalize_ld_product(raw, final_url)
    if not product.get("name") or product.get("price") is None:
        raise CliError(f"incomplete Product JSON-LD at {final_url}")
    product["source_url"] = final_url
    return product, final_url


def search(query: str, limit: int, page: int, timeout: int) -> dict[str, Any]:
    if not query.strip():
        raise CliError("search query must not be empty")
    url = BASE + "/search?" + urllib.parse.urlencode({"q": query, "p": page})
    markup, final_url = fetch_text(url, timeout)
    decoded_markup = html.unescape(markup)
    if re.search(r"Sorry,\s+we (?:could not|couldn't) find any products to match your search", decoded_markup, re.I):
        state: dict[str, Any] = {"items": [], "totalitems": 0, "totalpages": 0, "currentpage": page}
    else:
        state = extract_category_state(markup)
    items_value = state.get("items")
    items = [normalize_search_item(item) for item in items_value if isinstance(item, dict)][:limit] if isinstance(items_value, list) else []
    total = state.get("totalitems")
    if isinstance(total, int) and total > 0 and not items:
        raise CliError("search reported matches but no products could be normalized")
    return {
        "retailer": "Baby Factory NZ", "command": "search", "query": query, "page": state.get("currentpage", page),
        "count": len(items), "total": total, "total_pages": state.get("totalpages"), "results": items,
        "source_url": final_url, "retrieved_at": timestamp(),
    }


def detail(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {"retailer": "Baby Factory NZ", "command": "product", "product": product, "source_url": source_url, "retrieved_at": timestamp()}


def snapshot(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {
        "retailer": "Baby Factory NZ", "command": "price-snapshot", "sku": product.get("sku"), "name": product.get("name"),
        "price": product.get("price"), "currency": product.get("currency"), "availability": product.get("availability"),
        "offers": product.get("offers"), "source_url": source_url, "retrieved_at": timestamp(),
    }


def emit(data: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif data["command"] == "search":
        print(f"{data['count']} Baby Factory result(s) for {data['query']!r}")
        for item in data["results"]:
            print(f"${item.get('price', 0):.2f}  {item.get('name')}\n          {item.get('source_url')}")
    elif data["command"] == "product":
        item = data["product"]
        print(f"{item.get('name')}\n${item.get('price', 0):.2f} {item.get('currency')} | {item.get('availability') or 'availability not stated'}\n{data['source_url']}")
    else:
        print(f"{data.get('name')}: ${data.get('price', 0):.2f} {data.get('currency')}\n{data['source_url']}")


def bounded_limit(value: str) -> int:
    number_value = int(value)
    if not 1 <= number_value <= MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_RESULTS}")
    return number_value


def positive_int(value: str) -> int:
    number_value = int(value)
    if number_value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number_value


def bounded_page(value: str) -> int:
    number_value = positive_int(value)
    if number_value > MAX_PAGE:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_PAGE}")
    return number_value


def bounded_timeout(value: str) -> int:
    number_value = positive_int(value)
    if number_value > MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_TIMEOUT}")
    return number_value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="baby-factory-nz", description="Read-only Baby Factory NZ product search and price snapshots.")
    parser.add_argument("--timeout", type=bounded_timeout, default=10, help=f"network timeout in seconds (1-{MAX_TIMEOUT}; default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)
    search_parser = sub.add_parser("search", help="search public Baby Factory product HTML state")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=bounded_limit, default=10)
    search_parser.add_argument("--page", type=bounded_page, default=1)
    search_parser.add_argument("--json", action="store_true")
    for command, help_text in (("product", "fetch a product URL or slug"), ("price-snapshot", "capture current public price")):
        item_parser = sub.add_parser(command, help=help_text)
        item_parser.add_argument("product")
        item_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = search(args.query, args.limit, args.page, args.timeout) if args.command == "search" else detail(args.product, args.timeout) if args.command == "product" else snapshot(args.product, args.timeout)
        emit(data, args.json)
        return 0
    except (CliError, ValueError) as exc:
        print(f"baby-factory-nz: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
