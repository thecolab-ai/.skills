#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for this Shopify retailer skill."""
from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
NETWORK_MARKERS = ("network error", "timed out", "temporarily unavailable", "http 429", "http 5", "name or service not known")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=40)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def live_or_skip(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return True
    detail = (result.stderr + result.stdout).lower()
    if any(marker in detail for marker in NETWORK_MARKERS):
        print("[SKIP] live storefront unavailable: " + detail.strip()[:240])
        return False
    raise AssertionError(f"command failed ({result.returncode}): {result.stderr[:400]}")


class FakeResponse:
    def __init__(self, final_url: str): self.final_url = final_url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.final_url
    def read(self, size: int): return b"x" * size


class FakeOpener:
    def __init__(self, final_url: str): self.final_url = final_url
    def open(self, request, timeout): return FakeResponse(self.final_url)


def fetch_rejected(module, final_url: str) -> bool:
    original = module.urllib.request.build_opener
    module.urllib.request.build_opener = lambda *handlers: FakeOpener(final_url)
    try:
        module.fetch(module.BASE_URL + "/test", 1, "text/html")
    except module.StorefrontError:
        return True
    finally:
        module.urllib.request.build_opener = original
    return False


def main() -> int:
    spec = importlib.util.spec_from_file_location("retailer_cli", CLI)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load CLI module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.is_allowed_storefront_url(module.BASE_URL + "/products/example"), "storefront HTTPS URL rejected")
    require(not module.is_allowed_storefront_url("http://" + module.BASE_URL.split("//", 1)[1]), "HTTP redirect allowed")
    require(not module.is_allowed_storefront_url("https://evil.example/products/example"), "off-domain redirect allowed")
    require(not module.is_allowed_storefront_url(module.BASE_URL.replace("https://", "https://user@")), "userinfo allowed")
    require(not module.is_allowed_storefront_url(module.BASE_URL + ":444/test"), "non-default port allowed")
    require(module.is_allowed_storefront_url(module.BASE_URL + ":443/test"), "default HTTPS port rejected")
    try:
        module.StorefrontRedirectHandler().redirect_request(None, None, 302, "", {}, "https://evil.example/test")
        redirect_rejected = False
    except module.StorefrontError:
        redirect_rejected = True
    require(redirect_rejected, "redirect handler did not intercept foreign origin")
    require(fetch_rejected(module, "https://evil.example/test"), "foreign final URL was accepted")
    require(fetch_rejected(module, module.BASE_URL + "/test"), "oversized response was accepted")
    original_fetch_json = getattr(module, "fetch_json")
    setattr(module, "fetch_json", lambda url, timeout: ({"resources": {"results": {"products": {}}}}, url))
    try:
        module.search_products("cot", 1, 1)
        malformed_rejected = False
    except module.StorefrontError:
        malformed_rejected = True
    finally:
        setattr(module, "fetch_json", original_fetch_json)
    require(malformed_rejected, "malformed predictive-search products must be a concise error")

    search_fixture = {"id": 1, "handle": "fixture", "title": "Fixture", "price_min": 10.0, "price_max": 10.0, "compare_at_price_min": 0}
    require(module.normalize_search(search_fixture)["compare_at_price_min"] is None, "zero compare-at sentinel must be null")
    try:
        module.normalize_search({})
        malformed_search_rejected = False
    except module.StorefrontError:
        malformed_search_rejected = True
    require(malformed_search_rejected, "malformed predictive-search item must fail closed")
    for malformed_product in ({}, {"handle": "fixture", "title": "Fixture", "variants": None}, {"handle": "fixture", "title": "Fixture", "variants": []}, {"handle": "fixture", "title": "Fixture", "variants": ["bad"]}, {"handle": "fixture", "title": "Fixture", "variants": [{}]}):
        try:
            module.normalize_detail(malformed_product)
            product_rejected = False
        except module.StorefrontError:
            product_rejected = True
        require(product_rejected, "malformed product payload must be a concise error")
    title_parser = module.PageMetadataParser()
    title_parser.feed("<html><head><title>Store locations</title></head><body><svg><title>Visa</title></svg></body></html>")
    require(title_parser.title == "Store locations", "store-page title must ignore SVG titles")

    help_result = run("--help")
    require(help_result.returncode == 0, help_result.stderr)
    require("search" in help_result.stdout and "product" in help_result.stdout, "help missing commands")

    edge = run("search", "cot", "--limit", "0", "--json")
    require(edge.returncode == 2, "--limit 0 must be rejected")

    foreign = run("product", "https://evil.example/products/not-a-storefront-product", "--json")
    require(foreign.returncode == 1, "foreign product URL must be rejected")
    require("configured storefront" in foreign.stderr, "foreign URL rejection must be explicit")

    stores = run("stores", "--json")
    if live_or_skip(stores):
        store_data = json.loads(stores.stdout)
        require(store_data.get("source_url", "").startswith("https://"), "store page missing source_url")
        require(store_data.get("retrieved_at", "").endswith("Z"), "store page missing retrieved_at")

    search = run("search", "cot", "--limit", "3", "--json")
    if not live_or_skip(search):
        print("Offline checks passed.")
        return 0
    payload = json.loads(search.stdout)
    require(payload.get("source_url", "").startswith("https://"), "missing source_url")
    require(payload.get("retrieved_at", "").endswith("Z"), "missing UTC retrieved_at")
    require(payload.get("currency") == "NZD", "currency must be NZD")
    products = payload.get("products")
    require(isinstance(products, list) and bool(products), "search returned no products")
    require(len(products) <= 3, "search exceeded limit")
    first = products[0]
    require(first.get("handle"), "product missing handle")
    require(first.get("availability_scope") == "online storefront, not store stock", "availability scope unclear")

    detail = run("product", first["handle"], "--json")
    if live_or_skip(detail):
        item = json.loads(detail.stdout)
        require(item.get("source_url", "").endswith(".js"), "detail source must be product .js")
        require(item.get("retrieved_at", "").endswith("Z"), "detail missing retrieved_at")
        require(item["product"]["handle"] == first["handle"], "detail handle mismatch")
        require(isinstance(item["product"].get("variants"), list), "variants missing")
        require(all(v.get("availability_scope") == "online storefront, not store stock" for v in item["product"]["variants"]), "variant scope unclear")

    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
