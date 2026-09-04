#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for this HTML storefront skill."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
NETWORK_MARKERS = ("network error", "timed out", "temporarily unavailable", "http 429", "http 5", "name or service not known")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, check=False, text=True, timeout=40)


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
    search_html = """
    <html><body>
      <div class="col tp-product-item tp-product-item-grid-1" data-product-template-id="123">
        <form class="h-100 bg-white" role="article" data-publish="on" aria-label="Fixture Product">
          <input type="hidden" name="product_id" value="456"/>
          <div class="tp-product-content border-top p-2">
            <a class="tp-link-dark text-truncate d-block" itemprop="name" title="Fixture Product" href="/shop/fixture-product-456" content="Fixture Product">Fixture Product</a>
            <div aria-label="Price information" class="product_price">
              <span class="h6 text-primary mb-0"><span class="oe_currency_value">12.34</span></span>
            </div>
            <img src="/web/image/product.product/456/image_1024/fixture.webp"/>
          </div>
        </form>
      </div>
    </body></html>
    """
    parsed_search = module.parse_search_page(search_html, 1)
    require(parsed_search[0]["handle"] == "fixture-product-456", "search parser must preserve the canonical shop handle")
    require(module.normalize_search(parsed_search[0])["url"].endswith("/shop/fixture-product-456"), "search url must be canonical shop-based")
    require(module.product_lookup_url(parsed_search[0]["handle"]).endswith("/shop/fixture-product-456"), "search handle must resolve to a shop URL")
    try:
        module.parse_search_page("<html><body><div class='missing'></div></body></html>", 1)
        malformed_rejected = False
    except module.StorefrontError:
        malformed_rejected = True
    require(malformed_rejected, "malformed search HTML must fail closed")

    product_html = """
    <html><head><link rel="canonical" href="https://www.babycity.co.nz/shop/fixture-product-456"/></head>
    <body>
      <section id="product_detail">
        <input type="hidden" name="product_id" value="456"/>
        <input type="hidden" name="product_type" value="consu"/>
        <h1 class="h3">Fixture Product</h1>
        <span class="product-price"><span class="oe_currency_value">2229.93</span></span>
        <input class="js_variant_change" checked="True" data-value-name="Fixture Option" title="Fixture Option"/>
        <button class="product-add-to-cart btn btn-primary-soft">Add to Cart</button>
        <img src="/web/image/product.product/456/image_1024/fixture.webp"/>
      </section>
    </body></html>
    """
    parsed_product = module.parse_product_page(product_html, "fixture-product-456")
    normalized_product = module.normalize_detail(parsed_product)
    require(normalized_product["handle"] == "fixture-product-456", "product parser must preserve the canonical shop handle")
    require(normalized_product["url"].endswith("/shop/fixture-product-456"), "product url must remain canonical")
    require(normalized_product["price"] == 2229.93 and normalized_product["variants"][0]["price"] == 2229.93, "detail price must preserve decimal NZD values")
    require(isinstance(normalized_product.get("variants"), list) and normalized_product["variants"], "product variants missing")
    try:
        module.parse_product_page("<html><body><h1 class='h3'>Broken</h1></body></html>", "broken")
        malformed_rejected = False
    except module.StorefrontError:
        malformed_rejected = True
    require(malformed_rejected, "malformed product HTML must fail closed")

    search_fixture = {"id": 1, "handle": "fixture", "title": "Fixture", "price_min": 2229.93, "price_max": 2229.93, "compare_at_price_min": 0}
    normalized_search = module.normalize_search(search_fixture)
    require(normalized_search["price_min"] == 2229.93 and normalized_search["price_max"] == 2229.93, "search price must preserve decimal NZD values")
    require(normalized_search["compare_at_price_min"] is None, "zero compare-at sentinel must be null")
    require(module.amount("nan") is None and module.amount(float("inf")) is None and module.amount(-0.01) is None, "non-finite and negative prices must fail closed")
    try:
        module.normalize_search({})
        malformed_search_rejected = False
    except module.StorefrontError:
        malformed_search_rejected = True
    require(malformed_search_rejected, "malformed predictive-search item must fail closed")
    for malformed_product in ({}, {"handle": "fixture", "title": "Fixture", "variants": None}, {"handle": "fixture", "title": "Fixture", "variants": []}, {"handle": "fixture", "title": "Fixture", "variants": ["bad"]}, {"handle": "fixture", "title": "Fixture", "variants": [{}]}, {"handle": "fixture", "title": "Fixture", "price": float("nan"), "variants": [{"id": 1, "price": 2229.93}]}):
        try:
            module.normalize_detail(malformed_product)
            product_rejected = False
        except module.StorefrontError:
            product_rejected = True
        require(product_rejected, "malformed product payload must be a concise error")
    title_parser = module.PageMetadataParser()
    title_parser.feed("<html><head><title>Store locations</title></head><body><svg><title>Visa</title></svg></body></html>")
    require(title_parser.title == "Store locations", "store-page title must ignore SVG titles")
    print("[PASS] fixture storefront normalization, schema rejection, and access guards")

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
    require(str(first.get("url", "")).startswith("https://www.babycity.co.nz/shop/"), "search url must be canonical shop-based")
    require(first.get("availability_scope") == "online storefront, not store stock", "availability scope unclear")

    detail = run("product", first["handle"], "--json")
    if live_or_skip(detail):
        item = json.loads(detail.stdout)
        require("/shop/" in item.get("source_url", ""), "detail source must be the current storefront page")
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
