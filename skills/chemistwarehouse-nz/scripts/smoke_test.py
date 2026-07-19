#!/usr/bin/env python3
"""Live read-only smoke tests for the Chemist Warehouse NZ skill."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("chemistwarehouse_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)


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
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


def load_json(result: subprocess.CompletedProcess[str]) -> dict:
    if result.returncode != 0:
        raise AssertionError(f"command failed: {result.stderr[:300]}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"invalid JSON: {e}; stdout={result.stdout[:300]!r}")
    if not isinstance(data, dict):
        raise AssertionError("expected JSON object")
    return data


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "Chemist Warehouse NZ" in result.stdout


def test_suggest() -> bool:
    data = load_json(run(["suggest", "panadol", "--limit", "2", "--json"]))
    groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
    products = groups.get("products")
    keywords = groups.get("keywords")
    if not isinstance(products, list) or not products:
        raise AssertionError("expected product suggestions")
    if not isinstance(keywords, list) or not keywords:
        raise AssertionError("expected keyword suggestions")
    return bool(products[0].get("product_id") and products[0].get("name"))


def test_search() -> str:
    data = load_json(run(["search", "vitamin c", "--limit", "3", "--json"]))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("expected search items")
    if not data.get("total") or data.get("total") < len(items):
        raise AssertionError("expected total >= returned items")
    product_id = str(items[0].get("product_id") or "")
    if not product_id:
        raise AssertionError("expected product_id in first search result")
    return product_id


def test_category() -> bool:
    data = load_json(run(["category", "256", "--limit", "3", "--json"]))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("expected category items")
    if not data.get("total") or data.get("total") < len(items):
        raise AssertionError("expected category total >= returned items")
    return True


def test_product(product_id: str) -> bool:
    data = load_json(run(["product", product_id, "--json"]))
    items = data.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise AssertionError("expected one product detail item")
    item = items[0]
    if item.get("product_id") != product_id:
        raise AssertionError(f"expected product_id {product_id}, got {item.get('product_id')}")
    if not item.get("name") or not item.get("url"):
        raise AssertionError("expected detail name and URL")
    return True


results: list[bool] = []


def test_fixture_product_normalisation() -> bool:
    product = fixture_cli.normalize_product(
        {
            "secondid": "FIX-1",
            "name": "Fixture Vitamin",
            "brand": "Fixture Brand",
            "price_cw_nz": "12.49",
            "rrp_cw_nz": "15.99",
            "is_prescription": "false",
            "producturl": "https://www.chemistwarehouse.co.nz/buy/FIX-1",
        }
    )
    return bool(
        product["product_id"] == "FIX-1"
        and product["price"] == 12.49
        and product["rrp"] == 15.99
        and product["currency"] == "NZD"
        and product["is_prescription"] is False
    )


results.append(test("fixture search product normalisation", test_fixture_product_normalisation))
results.append(test("--help exits 0", test_help))
results.append(test("suggest panadol returns keyword and product suggestions", test_suggest))

search_product_id = ""


def capture_search() -> bool:
    global search_product_id
    search_product_id = test_search()
    return bool(search_product_id)


results.append(test("search vitamin c returns products", capture_search))
results.append(test("category 256 returns products", test_category))

if search_product_id:
    results.append(test("product detail returns a live item", lambda: test_product(search_product_id)))
else:
    results.append(False)
    print("[FAIL] product detail returns a live item")
    print("  error: skipped because search did not produce a product ID")

if all(results):
    print("[PASS] live smoke assertions completed")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
