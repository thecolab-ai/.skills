#!/usr/bin/env python3
"""Read-only Petstock NZ catalogue, product, price, and availability CLI."""
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

BASE = "https://www.petstock.co.nz"
ALGOLIA_APP_ID = "HX85NPQ0XP"
# Public read-only Algolia search key delivered to every Petstock browser.
ALGOLIA_API_KEY = "c545abd23934d9a1a200961d8d189708"
PRODUCT_INDEX = "product_prod"
VARIANT_INDEX = "product_prod_all_variants"
ALGOLIA_HOST = f"{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
ALGOLIA_URL = f"https://{ALGOLIA_HOST}/1/indexes/*/queries"
UA = "TheColab-petstock-nz/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"
MAX_RESULTS = 24
MAX_PAGE = 50
MAX_TIMEOUT = 60
MAX_RESPONSE_BYTES = 2_000_000


class CliError(RuntimeError):
    pass


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def allowed_storefront_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"petstock.co.nz", "www.petstock.co.nz"}
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


def allowed_algolia_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == ALGOLIA_HOST
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed, label: str):
        super().__init__()
        self.allowed = allowed
        self.label = label

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allowed(newurl):
            raise CliError(f"refusing redirect outside the {self.label}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_capped(response, url: str) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise CliError(f"response from {url} exceeded the {MAX_RESPONSE_BYTES}-byte safety limit")
    return body


def request_bytes(
    url: str,
    timeout: int,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    allowed=allowed_storefront_url,
    label: str = "Petstock HTTPS storefront",
) -> tuple[bytes, str]:
    if not allowed(url):
        raise CliError(f"refusing request outside the {label}")
    request_headers = {"User-Agent": UA, "Accept": "text/html, application/json;q=0.9"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers, method="POST" if data is not None else "GET")
    try:
        opener = urllib.request.build_opener(SafeRedirectHandler(allowed, label))
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not allowed(final_url):
                raise CliError(f"refusing response outside the {label}")
            return read_capped(response, url), final_url
    except urllib.error.HTTPError as exc:
        raise CliError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"network error calling {url}: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise CliError(f"network error calling {url}: {exc}") from exc


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 2) if math.isfinite(number) and number >= 0 else None


def algolia_queries(requests: list[dict[str, str]], timeout: int) -> tuple[list[dict[str, Any]], str]:
    if not 1 <= len(requests) <= MAX_RESULTS:
        raise CliError(f"Algolia request count must be between 1 and {MAX_RESULTS}")
    if any(request.get("indexName") not in {PRODUCT_INDEX, VARIANT_INDEX} for request in requests):
        raise CliError("refusing unapproved Algolia index")
    body = json.dumps({"requests": requests}).encode()
    raw, final_url = request_bytes(
        ALGOLIA_URL,
        timeout,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
        },
        allowed=allowed_algolia_url,
        label="shipped Petstock Algolia search origin",
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError("Algolia returned invalid JSON") from exc
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or len(results) != len(requests) or not all(isinstance(result, dict) for result in results):
        raise CliError("Algolia returned an unexpected result shape")
    if any(not isinstance(result.get("hits"), list) for result in results):
        raise CliError("Algolia result has no hits array")
    return results, final_url


def algolia_query(
    index: str,
    query: str,
    hits_per_page: int,
    page: int,
    timeout: int,
    *,
    exact_sku: str | None = None,
) -> tuple[dict[str, Any], str]:
    if exact_sku is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", exact_sku):
        raise CliError("refusing invalid exact SKU filter")
    query_params: dict[str, Any] = {"query": query, "hitsPerPage": hits_per_page, "page": page}
    if exact_sku is not None:
        query_params["facetFilters"] = json.dumps([f"sku:{exact_sku}"])
    params = urllib.parse.urlencode(query_params)
    results, final_url = algolia_queries([{"indexName": index, "params": params}], timeout)
    return results[0], final_url


def product_url(handle: str) -> str:
    return f"{BASE}/products/{urllib.parse.quote(handle)}"


def normalise_rewards(raw: dict[str, Any]) -> dict[str, Any]:
    loyalties_value = raw.get("loyalties")
    loyalties: list[Any] = loyalties_value if isinstance(loyalties_value, list) else []
    programmes = []
    for item in loyalties:
        if isinstance(item, dict) and item.get("loyaltyPromoCode"):
            programmes.append({
                "code": item.get("loyaltyPromoCode"),
                "earning": item.get("isEarning"),
                "redeeming": item.get("isRedeeming"),
                "rate": as_number(item.get("rate")),
                "starts_at": item.get("startsAt"),
                "ends_at": item.get("endsAt"),
            })
    edr_value = raw.get("edr")
    edr: dict[str, Any] = edr_value if isinstance(edr_value, dict) else {}
    return {
        "programmes": programmes,
        "everyday_rewards_points": edr.get("edrPoints"),
        "autoship_everyday_rewards_points": edr.get("sellingPlanEdrPoints"),
        "note": "Rewards eligibility/points are not a member price and may require programme membership.",
    }


def normalise_variant(raw: dict[str, Any]) -> dict[str, Any]:
    handle = raw.get("handle") if isinstance(raw.get("handle"), str) else ""
    sku = str(raw.get("sku") or raw.get("objectID") or "") or None
    return {
        "sku": sku,
        "gtin": None,
        "barcode": None,
        "title": raw.get("title"),
        "brand": raw.get("vendor"),
        "size": raw.get("size"),
        "colour": raw.get("colour"),
        "price_nzd": as_number(raw.get("price")),
        "original_price_nzd": as_number(raw.get("originalPrice")),
        "on_sale": bool(raw.get("discountApplied")),
        "online_available": raw.get("stockAvailableOnline"),
        "stock_available": raw.get("stockAvailable"),
        "home_delivery_allowed": raw.get("allowHomeDelivery"),
        "click_and_collect_allowed": raw.get("allowClickAndCollect"),
        "autoship": {
            "available": raw.get("subscriptionAvailable"),
            "price_nzd": as_number(raw.get("subscriptionPrice")),
            "note": "Autoship is a conditional recurring-order offer, not the standard or member price.",
        },
        "member_price": {
            "available": False,
            "price_nzd": None,
            "note": "No distinct public member-price field was verified in this catalogue record.",
        },
        "rewards": normalise_rewards(raw),
        "source_url": product_url(handle) if handle and re.fullmatch(r"[a-z0-9][a-z0-9-]*", handle) else None,
    }


def normalise_hit(raw: dict[str, Any]) -> dict[str, Any]:
    item = normalise_variant(raw)
    item.update({
        "description": re.sub(r"<[^>]+>", " ", html.unescape(str(raw.get("description") or ""))).strip(),
        "categories": raw.get("categories") if isinstance(raw.get("categories"), list) else [],
        "image": raw.get("image"),
        "review_average": raw.get("reviewAverage"),
        "review_count": raw.get("reviewCount"),
    })
    return item


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


def parse_product_input(value: str) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value:
        raise CliError("product must not be empty")
    if value.startswith("https://"):
        if not allowed_storefront_url(value):
            raise CliError("product URL must be on the Petstock NZ HTTPS storefront")
        path = urllib.parse.unquote(urllib.parse.urlparse(value).path).rstrip("/")
        match = re.fullmatch(r"/products/([a-z0-9][a-z0-9-]*?)(?:-variant-([A-Za-z0-9_-]+))?", path)
        if not match:
            raise CliError("product URL must use /products/<handle> or /products/<handle>-variant-<sku>")
        return match.group(1), match.group(2)
    if re.fullmatch(r"[0-9]{5,32}", value):
        return None, value
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise CliError("product must be a Petstock handle, product URL, or numeric SKU")
    return value, None


def resolve_handle_from_sku(sku: str, timeout: int) -> str:
    result, _ = algolia_query(VARIANT_INDEX, "", 1, 0, timeout, exact_sku=sku)
    exact = next((hit for hit in result["hits"] if isinstance(hit, dict) and str(hit.get("sku") or hit.get("objectID")) == sku), None)
    handle = exact.get("handle") if isinstance(exact, dict) else None
    if not isinstance(handle, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", handle):
        raise CliError(f"no exact Petstock SKU match found for {sku}")
    return handle


def fetch_product(handle: str, timeout: int) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    raw, final_url = request_bytes(product_url(handle), timeout)
    markup = raw.decode("utf-8", "replace")
    product = next((item for item in json_ld_objects(markup) if item.get("@type") == "Product"), None)
    if not isinstance(product, dict) or not product.get("name"):
        raise CliError(f"no complete Product JSON-LD found at {final_url}")
    offers_value = product.get("offers")
    offers_raw = offers_value if isinstance(offers_value, list) else [offers_value] if isinstance(offers_value, dict) else []
    offers = []
    for offer in offers_raw:
        if not isinstance(offer, dict):
            continue
        offer_url = offer.get("url") if isinstance(offer.get("url"), str) else None
        if not offer_url or not allowed_storefront_url(offer_url):
            raise CliError(f"product offer at {final_url} had no canonical Petstock NZ URL")
        availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
        sku_match = re.search(r"-variant-([A-Za-z0-9_-]{1,64})$", urllib.parse.urlparse(offer_url).path) if offer_url else None
        price = as_number(offer.get("price"))
        if not sku_match or price is None or offer.get("priceCurrency") != "NZD":
            raise CliError(f"product offer at {final_url} was missing an exact SKU, price, or NZD currency")
        offers.append({
            "sku": sku_match.group(1) if sku_match else None,
            "price_nzd": price,
            "currency": offer.get("priceCurrency"),
            "availability": availability,
            "in_stock": availability == "InStock" if availability else None,
            "source_url": offer_url,
        })
    if not offers or any(offer.get("currency") != "NZD" for offer in offers):
        raise CliError(f"product offers at {final_url} were missing or not NZD")
    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    detail = {
        "name": product.get("name"),
        "brand": brand,
        "description": re.sub(r"\s+", " ", html.unescape(str(product.get("description") or ""))).strip(),
        "images": product.get("image") if isinstance(product.get("image"), list) else [product.get("image")] if product.get("image") else [],
        "offers": offers,
        "aggregate_rating": product.get("aggregateRating"),
        "source_url": final_url,
    }
    if len(offers) > MAX_RESULTS:
        raise CliError(f"product has more than the {MAX_RESULTS}-variant safety limit")
    offer_skus = [offer.get("sku") for offer in offers]
    if any(not isinstance(sku, str) for sku in offer_skus) or len(set(offer_skus)) != len(offer_skus):
        raise CliError(f"product offers at {final_url} have missing or duplicate SKU evidence")
    requests = []
    for sku in offer_skus:
        params = urllib.parse.urlencode({
            "query": "",
            "hitsPerPage": 1,
            "page": 0,
            "facetFilters": json.dumps([f"sku:{sku}"]),
        })
        requests.append({"indexName": VARIANT_INDEX, "params": params})
    results, _ = algolia_queries(requests, timeout)
    variants = []
    for sku, result in zip(offer_skus, results):
        exact = next((hit for hit in result["hits"] if isinstance(hit, dict) and str(hit.get("sku") or hit.get("objectID")) == sku), None)
        if not isinstance(exact, dict) or exact.get("handle") != handle:
            raise CliError(f"no exact catalogue variant matched SKU {sku} for product handle {handle}")
        variants.append(normalise_variant(exact))
    return detail, variants, final_url


def search(query: str, limit: int, page: int, timeout: int) -> dict[str, Any]:
    if not query.strip():
        raise CliError("search query must not be empty")
    result, source_url = algolia_query(PRODUCT_INDEX, query, limit, page - 1, timeout)
    hits = [normalise_hit(hit) for hit in result["hits"] if isinstance(hit, dict)][:limit]
    if result.get("nbHits", 0) and not hits:
        raise CliError("search reported matches but no products could be normalised")
    if any(not hit.get("sku") or not hit.get("title") or not hit.get("source_url") or hit.get("price_nzd") is None for hit in hits):
        raise CliError("search returned an incomplete Petstock NZ product record")
    return {
        "retailer": "Petstock NZ",
        "command": "search",
        "query": query,
        "page": page,
        "count": len(hits),
        "total": result.get("nbHits"),
        "total_pages": result.get("nbPages"),
        "currency": "NZD",
        "results": hits,
        "source_url": source_url,
        "retrieved_at": timestamp(),
        "identifier_semantics": "sku is retailer-supplied; gtin/barcode stay null unless independently validated (none are exposed here).",
    }


def product_detail(value: str, timeout: int) -> dict[str, Any]:
    handle, sku = parse_product_input(value)
    if handle is None:
        handle = resolve_handle_from_sku(str(sku), timeout)
    detail, variants, source_url = fetch_product(handle, timeout)
    if sku and not any(item.get("sku") == sku for item in variants):
        raise CliError(f"product page did not contain exact SKU {sku}")
    detail["variants"] = variants
    return {
        "retailer": "Petstock NZ",
        "command": "product",
        "product": detail,
        "source_url": source_url,
        "retrieved_at": timestamp(),
        "identifier_semantics": "variant identifiers are SKUs only; no value is labelled as GTIN/barcode without a validated source field.",
    }


def snapshot(value: str, timeout: int, command: str) -> dict[str, Any]:
    data = product_detail(value, timeout)
    product = data["product"]
    variants = product["variants"]
    if command == "availability":
        rows = [{k: item.get(k) for k in ("sku", "title", "size", "online_available", "stock_available", "home_delivery_allowed", "click_and_collect_allowed", "source_url")} for item in variants]
    else:
        rows = [{k: item.get(k) for k in ("sku", "gtin", "barcode", "title", "size", "price_nzd", "original_price_nzd", "on_sale", "online_available", "autoship", "member_price", "rewards", "source_url")} for item in variants]
    return {
        "retailer": "Petstock NZ",
        "command": command,
        "name": product.get("name"),
        "currency": "NZD",
        "variants": rows,
        "source_url": data["source_url"],
        "retrieved_at": data["retrieved_at"],
        "identifier_semantics": data["identifier_semantics"],
    }


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if data["command"] == "search":
        print(f"{data['count']} Petstock NZ result(s) for {data['query']!r}")
        for item in data["results"]:
            price = item.get("price_nzd")
            print(f"${price:.2f}  {item.get('title')}\n          {item.get('source_url')}") if price is not None else print(f"-  {item.get('title')}")
    elif data["command"] == "product":
        product = data["product"]
        print(f"{product.get('name')}\n{len(product.get('variants', []))} variant(s)\n{data['source_url']}")
    else:
        print(f"{data.get('name')}: {len(data.get('variants', []))} variant(s)\n{data['source_url']}")


def bounded_int(value: str, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= number <= maximum:
        raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="petstock-nz", description="Read-only Petstock NZ catalogue, price, offer, and availability snapshots.")
    parser.add_argument("--timeout", type=lambda value: bounded_int(value, MAX_TIMEOUT), default=10, help=f"network timeout in seconds (1-{MAX_TIMEOUT}; default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)
    search_parser = sub.add_parser("search", help="search the shipped public Petstock catalogue index")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=lambda value: bounded_int(value, MAX_RESULTS), default=10)
    search_parser.add_argument("--page", type=lambda value: bounded_int(value, MAX_PAGE), default=1)
    search_parser.add_argument("--json", action="store_true")
    for name, help_text in (
        ("product", "get public product and offer detail by handle, URL, or SKU"),
        ("price-snapshot", "capture current standard, Autoship, and rewards-aware prices"),
        ("availability", "capture current online and fulfilment availability"),
    ):
        item_parser = sub.add_parser(name, help=help_text)
        item_parser.add_argument("product")
        item_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "search":
            data = search(args.query, args.limit, args.page, args.timeout)
        elif args.command == "product":
            data = product_detail(args.product, args.timeout)
        else:
            data = snapshot(args.product, args.timeout, args.command)
        emit(data, args.json)
        return 0
    except (CliError, ValueError) as exc:
        print(f"petstock-nz: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
