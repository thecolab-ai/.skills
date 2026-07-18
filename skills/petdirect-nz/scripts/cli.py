#!/usr/bin/env python3
"""Read-only Petdirect NZ HTML and JSON-LD product CLI."""
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

BASE = "https://petdirect.co.nz"
UA = "TheColab-petdirect-nz/1.0 (+https://github.com/thecolab-ai/.skills)"
MAX_RESULTS = 24
MAX_SEARCH_BYTES = 2_700_000
MAX_PAGE_BYTES = 1_500_000
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
        and parsed.hostname in {"petdirect.co.nz", "www.petdirect.co.nz"}
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_url(newurl):
            raise CliError("refusing redirect outside the Petdirect HTTPS storefront")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_text(
    url: str,
    timeout: int = 10,
    max_bytes: int = MAX_PAGE_BYTES,
    *,
    allow_truncated: bool = False,
) -> tuple[str, str]:
    if not is_allowed_url(url):
        raise CliError("refusing request outside the Petdirect HTTPS storefront")
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-NZ,en;q=0.9"}, method="GET")
    try:
        with urllib.request.build_opener(StorefrontRedirectHandler()).open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not is_allowed_url(final_url):
                raise CliError("refusing response outside the Petdirect HTTPS storefront")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes and not allow_truncated:
                raise CliError(f"response from {url} exceeded the {max_bytes}-byte safety limit")
            return body[:max_bytes].decode("utf-8", "replace"), final_url
    except urllib.error.HTTPError as exc:
        raise CliError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"network error calling {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CliError(f"request timed out after {timeout}s: {url}") from exc


def cents(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        result = float(value) / 100
    except (OverflowError, TypeError, ValueError):
        return None
    return round(result, 2) if math.isfinite(result) and result >= 0 else None


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return round(result, 2) if math.isfinite(result) and result >= 0 else None


def extract_server_state(markup: str) -> dict[str, Any]:
    match = re.search(r"window\.__SERVER_STATE__\s*=\s*(\{.*?\});\s*window\.__LOCATION__", markup, re.S)
    if not match:
        raise CliError("Petdirect search state was not found; the public page may have changed")
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise CliError("Petdirect search state contained invalid JSON") from exc
    return state if isinstance(state, dict) else {}


def extract_product_state(markup: str) -> dict[str, Any]:
    match = re.search(r"window\.__PRODUCT__\s*=\s*(\{.*?\});\s*</script>", markup, re.S)
    if not match:
        raise CliError("Petdirect product state was not found; member-price semantics cannot be verified")
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise CliError("Petdirect product state contained invalid JSON") from exc
    if not isinstance(state, dict) or not isinstance(state.get("variants"), list):
        raise CliError("Petdirect product state has no variants list")
    return state


def search_result(state: dict[str, Any]) -> dict[str, Any]:
    initial = state.get("initialResults")
    if not isinstance(initial, dict):
        raise CliError("Petdirect search state has no initialResults object")
    for index in initial.values():
        if not isinstance(index, dict):
            continue
        results = index.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0]
    raise CliError("Petdirect search state has no result set")


def normalize_variant(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "sku": raw.get("sku"),
        "name": raw.get("name"),
        "price": cents(raw.get("discountedUnitPrice")),
        "rrp": cents(raw.get("rrpPrice")),
        "member_price": bool(raw.get("isMemberPrice")),
        "in_stock": raw.get("isInStock"),
        "purchasing_status": raw.get("purchasingStatus"),
        "weight_kg": raw.get("netProductWeightKilograms"),
        "image": raw.get("imageUrl"),
    }


def normalize_hit(raw: dict[str, Any]) -> dict[str, Any]:
    variants = [normalize_variant(item) for item in raw.get("variants", []) if isinstance(item, dict)]
    cheapest_raw = raw.get("cheapestVariant")
    cheapest = normalize_variant(cheapest_raw) if isinstance(cheapest_raw, dict) else None
    path = raw.get("bcCustomUrl") or ""
    source_url = urllib.parse.urljoin(BASE, str(path))
    return {
        "id": raw.get("objectID") or raw.get("id"),
        "code": raw.get("code"),
        "name": raw.get("name"),
        "brand": raw.get("brandName"),
        "price": cheapest.get("price") if cheapest else None,
        "rrp": cheapest.get("rrp") if cheapest else None,
        "member_price": cheapest.get("member_price") if cheapest else None,
        "in_stock": cheapest.get("in_stock") if cheapest else None,
        "categories": raw.get("categories") or [],
        "rating": raw.get("averageRating"),
        "image": raw.get("imageUrl"),
        "variants": variants,
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


def offer_from_variant(raw: dict[str, Any]) -> dict[str, Any]:
    offers = raw.get("offers")
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), {})
    return offers if isinstance(offers, dict) else {}


def normalize_ld_product(raw: dict[str, Any], source_url: str) -> dict[str, Any]:
    brand = raw.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    variants_value = raw.get("hasVariant")
    variants_raw: list[Any] = variants_value if isinstance(variants_value, list) else []
    variants: list[dict[str, Any]] = []
    for item in variants_raw:
        if not isinstance(item, dict):
            continue
        offer = offer_from_variant(item)
        availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
        variants.append({
            "sku": item.get("sku"),
            "name": item.get("name"),
            "price": number(offer.get("price")),
            "currency": offer.get("priceCurrency") or "NZD",
            "availability": availability,
            "in_stock": availability == "InStock" if availability else None,
        })
    offer = offer_from_variant(raw)
    if not offer and variants:
        priced = [item for item in variants if item.get("price") is not None]
        cheapest = min(priced, key=lambda item: item["price"]) if priced else {}
        price, currency, availability = cheapest.get("price"), cheapest.get("currency"), cheapest.get("availability")
    else:
        price = number(offer.get("price") or offer.get("lowPrice"))
        currency = offer.get("priceCurrency") or "NZD"
        availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
    image = raw.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    return {
        "id": raw.get("productGroupID") or raw.get("@id"),
        "sku": raw.get("sku"),
        "name": raw.get("name"),
        "brand": brand,
        "description": re.sub(r"<[^>]+>", " ", html.unescape(str(raw.get("description") or ""))).strip(),
        "image": image,
        "price": price,
        "currency": currency,
        "availability": availability,
        "variants": variants,
        "source_url": raw.get("url") or source_url,
    }


def apply_product_state(product: dict[str, Any], state: dict[str, Any]) -> None:
    state_variants = state.get("variants")
    if not isinstance(state_variants, list):
        raise CliError("Petdirect product state has no variants list")
    by_sku = {str(item.get("sku")): item for item in state_variants if isinstance(item, dict) and item.get("sku")}
    variants = product.get("variants")
    if not isinstance(variants, list):
        raise CliError("Petdirect Product JSON-LD has no variants list")
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        evidence = by_sku.get(str(variant.get("sku")))
        if evidence is None:
            raise CliError(f"Petdirect price semantics could not be verified for SKU {variant.get('sku') or 'unknown'}")
        state_price = cents(evidence.get("discountedUnitPrice"))
        if state_price is None:
            raise CliError(f"Petdirect current price could not be verified for SKU {variant.get('sku') or 'unknown'}")
        variant["price"] = state_price
        variant["rrp"] = cents(evidence.get("rrpPrice"))
        variant["member_price"] = bool(evidence.get("isMemberPrice"))
    priced = [item for item in variants if isinstance(item, dict) and item.get("price") is not None]
    if priced:
        cheapest = min(priced, key=lambda item: item["price"])
        product["price"] = cheapest["price"]
        product["rrp"] = cheapest.get("rrp")
        product["member_price"] = cheapest.get("member_price")


def product_url(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        if not is_allowed_url(value):
            raise CliError("product URL must be on petdirect.co.nz")
        return value
    if value.startswith("/p/"):
        return urllib.parse.urljoin(BASE, value)
    slug = value.strip("/")
    if not slug or "/" in slug:
        raise CliError("product must be a Petdirect product URL, /p/ path, or slug")
    return f"{BASE}/p/{urllib.parse.quote(slug)}/"


def get_product(value: str, timeout: int) -> tuple[dict[str, Any], str]:
    url = product_url(value)
    markup, final_url = fetch_text(url, timeout)
    raw = next((item for item in json_ld_objects(markup) if item.get("@type") in {"Product", "ProductGroup"}), None)
    if not raw:
        raise CliError(f"no Product JSON-LD found at {final_url}; the page may have changed")
    product = normalize_ld_product(raw, final_url)
    if not product.get("name") or product.get("price") is None:
        raise CliError(f"incomplete Product JSON-LD at {final_url}")
    apply_product_state(product, extract_product_state(markup))
    product["source_url"] = final_url
    return product, final_url


def search(query: str, limit: int, page: int, timeout: int) -> dict[str, Any]:
    if not query.strip():
        raise CliError("search query must not be empty")
    url = BASE + "/search?" + urllib.parse.urlencode({"q": query, "page": page})
    # Current search HTML repeats its server state later in the document. The
    # complete first state object is inside this bounded prefix, so deliberately
    # stop reading rather than downloading the duplicate multi-megabyte tail.
    markup, final_url = fetch_text(url, timeout, MAX_SEARCH_BYTES, allow_truncated=True)
    result = search_result(extract_server_state(markup))
    hits = [normalize_hit(item) for item in result.get("hits", []) if isinstance(item, dict)][:limit]
    if result.get("nbHits", 0) and not hits:
        raise CliError("search reported matches but no products could be normalized")
    return {
        "retailer": "Petdirect NZ", "command": "search", "query": query, "page": page,
        "count": len(hits), "total": result.get("nbHits"), "total_pages": result.get("nbPages"),
        "results": hits, "source_url": final_url, "retrieved_at": timestamp(),
    }


def detail(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {"retailer": "Petdirect NZ", "command": "product", "product": product, "source_url": source_url, "retrieved_at": timestamp()}


def snapshot(value: str, timeout: int) -> dict[str, Any]:
    product, source_url = get_product(value, timeout)
    return {
        "retailer": "Petdirect NZ", "command": "price-snapshot", "sku": product.get("sku"), "name": product.get("name"),
        "price": product.get("price"), "rrp": product.get("rrp"), "member_price": product.get("member_price"),
        "currency": product.get("currency"), "availability": product.get("availability"),
        "variants": product.get("variants"), "source_url": source_url, "retrieved_at": timestamp(),
    }


def display_price(item: dict[str, Any]) -> str:
    price = item.get("price")
    rendered = f"${price:.2f}" if isinstance(price, (int, float)) else "price unavailable"
    if item.get("member_price") is True:
        rendered += " Pet Perks member price"
    rrp = item.get("rrp")
    if isinstance(rrp, (int, float)) and rrp > 0:
        rendered += f" (RRP ${rrp:.2f})"
    return rendered


def emit(data: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif data["command"] == "search":
        print(f"{data['count']} Petdirect result(s) for {data['query']!r}")
        for item in data["results"]:
            print(f"{display_price(item)}  {item.get('name')}\n          {item.get('source_url')}")
    elif data["command"] == "product":
        item = data["product"]
        print(f"{item.get('name')}\nFrom {display_price(item)} {item.get('currency')}\n{data['source_url']}")
    else:
        print(f"{data.get('name')}: from {display_price(data)} {data.get('currency')}\n{data['source_url']}")


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
    parser = argparse.ArgumentParser(prog="petdirect-nz", description="Read-only Petdirect NZ product search and price snapshots.")
    parser.add_argument("--timeout", type=bounded_timeout, default=10, help=f"network timeout in seconds (1-{MAX_TIMEOUT}; default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)
    search_parser = sub.add_parser("search", help="search public Petdirect product HTML state")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=bounded_limit, default=10)
    search_parser.add_argument("--page", type=bounded_page, default=1)
    search_parser.add_argument("--json", action="store_true")
    for command, help_text in (("product", "fetch a product URL or slug"), ("price-snapshot", "capture current public prices")):
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
        print(f"petdirect-nz: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
