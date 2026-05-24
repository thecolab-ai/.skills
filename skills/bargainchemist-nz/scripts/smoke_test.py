#!/usr/bin/env python3
"""Live read-only smoke tests for the Bargain Chemist NZ skill."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results: list[bool] = []
search_handle = ""


def test_help() -> bool:
    result = run(["--help"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_search() -> bool:
    global search_handle
    result = run(["search", "panadol", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    products = data.get("results")
    if not isinstance(products, list) or not products:
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected search JSON to include non-empty results[]")
        return False
    if not isinstance(data.get("total_product"), int) or data["total_product"] < 1:
        print("  Expected total_product > 0")
        return False
    first = products[0]
    required = ("title", "handle", "url", "price_min", "price_max", "available", "variants", "images")
    missing = [key for key in required if key not in first]
    if missing:
        print(f"  Missing normalized product keys: {missing}")
        return False
    search_handle = str(first.get("handle") or "")
    return bool(search_handle)


results.append(test("search panadol returns normalized products", test_search))


def test_suggest() -> bool:
    result = run(["suggest", "panadol", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    if data.get("source") != "boost-commerce-suggest":
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected source=boost-commerce-suggest")
        return False
    products = data.get("results")
    if not isinstance(products, list) or not products:
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected suggest JSON to include non-empty results[]")
        return False
    return isinstance(data.get("total_product"), int)


results.append(test("suggest panadol returns suggested products", test_suggest))


def test_product() -> bool:
    if not search_handle:
        print("  No handle captured from search")
        return False
    result = run(["product", search_handle, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    product = data.get("product")
    if not isinstance(product, dict):
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected product object")
        return False
    if product.get("handle") != search_handle:
        print(f"  Expected handle {search_handle!r}, got {product.get('handle')!r}")
        return False
    if data.get("source") != "shopify-product-json":
        print(f"  Expected source=shopify-product-json, got {data.get('source')!r}")
        return False
    if not isinstance(product.get("variants"), list) or not product["variants"]:
        print("  Expected product variants[]")
        return False
    if not isinstance(product.get("images"), list):
        print("  Expected product images[]")
        return False
    return bool(product.get("url")) and product.get("price_min") is not None


results.append(test("product <handle> returns Shopify product JSON", test_product))

if all(results):
    print("All tests passed.")
    sys.exit(0)

print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
