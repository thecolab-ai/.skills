#!/usr/bin/env python3
"""Fixture and outage-aware live checks for petstock-nz."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
spec = importlib.util.spec_from_file_location("petstock_cli", CLI)
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
FAILURES = 0
SKIPS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global FAILURES
    if condition:
        print(f"[PASS] {name}")
    else:
        FAILURES += 1
        print(f"[FAIL] {name}: {detail}")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(CLI), *args]
    try:
        return subprocess.run(command, text=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "network error: CLI subprocess timed out after 60s")


def outage(result: subprocess.CompletedProcess[str]) -> bool:
    text = result.stderr.lower()
    return any(marker in text for marker in ("network error", "timed out", "http 429", "http 500", "http 502", "http 503", "http 504"))


class FakeResponse:
    def __init__(self, final_url: str, body: bytes):
        self.final_url = final_url
        self.body = body

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.final_url
    def read(self, size: int): return self.body[:size]


class FakeOpener:
    def __init__(self, final_url: str, body: bytes):
        self.final_url = final_url
        self.body = body

    def open(self, request, timeout): return FakeResponse(self.final_url, self.body)


def request_rejected(final_url: str, body: bytes) -> bool:
    original = cli.urllib.request.build_opener
    cli.urllib.request.build_opener = lambda *handlers: FakeOpener(final_url, body)
    try:
        cli.request_bytes(cli.BASE + "/test", 10)
    except cli.CliError:
        return True
    finally:
        cli.urllib.request.build_opener = original
    return False


raw_hit = {
    "objectID": "122731000059",
    "sku": "122731000059",
    "title": "Fixture Food",
    "handle": "fixture-food",
    "price": 66.49,
    "originalPrice": 70,
    "discountApplied": True,
    "stockAvailableOnline": True,
    "subscriptionAvailable": True,
    "subscriptionPrice": 59.84,
    "loyalties": [{"loyaltyPromoCode": "PETCASH", "isEarning": False, "isRedeeming": True, "rate": 0}],
    "edr": {"edrPoints": "66", "sellingPlanEdrPoints": "60"},
}
item = cli.normalise_hit(raw_hit)
check("fixture preserves SKU without inventing barcode", item["sku"] == "122731000059" and item["gtin"] is None and item["barcode"] is None)
check("fixture distinguishes standard and Autoship prices", item["price_nzd"] == 66.49 and item["autoship"]["price_nzd"] == 59.84 and item["member_price"]["price_nzd"] is None)
check("fixture keeps rewards separate from price", item["rewards"]["everyday_rewards_points"] == "66" and item["rewards"]["programmes"][0]["code"] == "PETCASH")
check("malformed prices fail closed", cli.as_number("nan") is None and cli.as_number("inf") is None and cli.as_number(-0.01) is None and cli.as_number(10**10000) is None)
for field in ("price", "originalPrice"):
    malformed_hit = dict(raw_hit)
    malformed_hit[field] = -0.01
    malformed_item = cli.normalise_hit(malformed_hit)
    target = "price_nzd" if field == "price" else "original_price_nzd"
    check(f"negative {field} fails closed through product normalisation", malformed_item[target] is None)
malformed_hit = dict(raw_hit)
malformed_hit["subscriptionPrice"] = 10**10000
check("overflowing Autoship price fails closed through product normalisation", cli.normalise_hit(malformed_hit)["autoship"]["price_nzd"] is None)
markup = '<script type="application/ld+json">{"@type":"Product","name":"Fixture","offers":[{"price":"12.50","priceCurrency":"NZD"}]}</script>'
check("fixture Product JSON-LD parses", cli.json_ld_objects(markup)[0]["name"] == "Fixture")
original_request_bytes = cli.request_bytes
setattr(cli, "request_bytes", lambda *args, **kwargs: (b'<script type="application/ld+json">{"@type":"Product","name":"Fixture","offers":[{"price":"12.50","url":"https://www.petstock.co.nz/products/fixture-variant-12345"}]}</script>', cli.BASE + "/products/fixture"))
try:
    cli.fetch_product("fixture", 10)
    missing_currency_rejected = False
except cli.CliError:
    missing_currency_rejected = True
finally:
    setattr(cli, "request_bytes", original_request_bytes)
check("missing JSON-LD offer currency fails closed", missing_currency_rejected)
check("canonical origins enforced", cli.allowed_storefront_url("https://www.petstock.co.nz/products/x") and not cli.allowed_storefront_url("http://www.petstock.co.nz/products/x") and not cli.allowed_storefront_url("https://user@www.petstock.co.nz/products/x") and not cli.allowed_storefront_url("https://www.petstock.co.nz:444/products/x") and cli.allowed_algolia_url(cli.ALGOLIA_URL) and not cli.allowed_algolia_url("https://example.org/1/indexes/*/queries"))
try:
    cli.algolia_query("unapproved_index", "food", 1, 0, 10)
    index_rejected = False
except cli.CliError:
    index_rejected = True
check("Algolia index allowlist enforced before network", index_rejected)
try:
    cli.algolia_query(cli.VARIANT_INDEX, "", 1, 0, 10, exact_sku='bad"filter')
    sku_filter_rejected = False
except cli.CliError:
    sku_filter_rejected = True
check("exact SKU filter rejects injection characters", sku_filter_rejected)
try:
    cli.SafeRedirectHandler(cli.allowed_storefront_url, "storefront").redirect_request(None, None, 302, "", {}, "https://example.org/x")
    redirect_rejected = False
except cli.CliError:
    redirect_rejected = True
check("foreign redirect rejected before follow", redirect_rejected)
check("final URL rejection enforced", request_rejected("https://example.org/x", b"ok"))
check("oversized response rejected", request_rejected(cli.BASE + "/test", b"x" * (cli.MAX_RESPONSE_BYTES + 1)))
check("product input accepts handle, URL, and SKU", cli.parse_product_input("fixture-food") == ("fixture-food", None) and cli.parse_product_input(cli.BASE + "/products/fixture-food-variant-12345") == ("fixture-food", "12345") and cli.parse_product_input("122731000059") == (None, "122731000059"))
help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("bounds enforced", run("search", "food", "--limit", "25").returncode != 0 and run("search", "food", "--page", "51").returncode != 0 and run("--timeout", "61", "search", "food").returncode != 0)
check("empty search rejected", run("search", " ", "--json").returncode != 0)
check("foreign product URL rejected", run("product", "https://example.org/products/x", "--json").returncode != 0)

live = run("search", "dog food", "--limit", "1", "--json")
if live.returncode and outage(live):
    SKIPS += 1
    print(f"[SKIP] live search: upstream unavailable ({live.stderr.strip()[:180]})")
else:
    check("live search exits zero", live.returncode == 0, live.stderr[:300])
    if live.returncode == 0:
        data = json.loads(live.stdout)
        results = data.get("results")
        check("live search is NZD and evidenced", data.get("currency") == "NZD" and bool(results and data.get("source_url") and data.get("retrieved_at")))
        first = results[0] if results else {}
        check("live record resolves to Petstock NZ", cli.allowed_storefront_url(str(first.get("source_url"))))
        product = run("product", str(first.get("source_url")), "--json")
        if product.returncode and outage(product):
            SKIPS += 1
            print(f"[SKIP] live product: upstream unavailable ({product.stderr.strip()[:180]})")
        else:
            check("live product exits zero", product.returncode == 0, product.stderr[:300])
            if product.returncode == 0:
                detail = json.loads(product.stdout)
                variants = detail.get("product", {}).get("variants")
                check("live product has NZD offers and variants", bool(variants) and all(offer.get("currency") == "NZD" for offer in detail["product"].get("offers", [])))
                check("live offers and exact-filtered variants have identical SKUs", {o.get("sku") for o in detail["product"].get("offers", [])} == {v.get("sku") for v in variants})
                check("live variants preserve identifier semantics", all(v.get("sku") and v.get("gtin") is None and v.get("barcode") is None for v in variants))
                availability = run("availability", str(first.get("source_url")), "--json")
                if availability.returncode and outage(availability):
                    SKIPS += 1
                    print(f"[SKIP] live availability: upstream unavailable ({availability.stderr.strip()[:180]})")
                else:
                    check("live availability exits zero", availability.returncode == 0, availability.stderr[:300])

print(f"{FAILURES} failure(s), {SKIPS} outage skip(s)")
raise SystemExit(1 if FAILURES else 0)
