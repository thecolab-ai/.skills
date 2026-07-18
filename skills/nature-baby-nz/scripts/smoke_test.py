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


def main() -> int:
    spec = importlib.util.spec_from_file_location("retailer_cli", CLI)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load CLI module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.is_allowed_storefront_url(module.BASE_URL + "/products/example"), "storefront HTTPS URL rejected")
    require(not module.is_allowed_storefront_url("http://" + module.BASE_URL.split("//", 1)[1]), "HTTP redirect allowed")
    require(not module.is_allowed_storefront_url("https://evil.example/products/example"), "off-domain redirect allowed")

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
