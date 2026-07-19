#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=30,
    )


def test(name: str, fn):
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_product_card_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_pricewatch_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalize_card(
        {
            "data": {
                "product": {
                    "id": 1234,
                    "name": "Synthetic Headphones",
                    "brandName": "Example",
                    "category": {"categoryId": 10, "categoryName": "Headphones"},
                    "productLink": "/product.php?p=1234",
                    "storeCount": 4,
                },
                "offer": {"price": "199.95", "storeName": "Example Store", "stockStatus": "In stock"},
            }
        }
    )
    assert record and record["product_id"] == 1234
    assert record["current_price"] == 199.95
    assert record["merchant"] == "Example Store"
    assert record["product_url"].startswith("https://")
    print("[PASS] fixture PriceSpy product-card normalisation")
    return True


results.append(test("fixture product card parser", test_product_card_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_categories():
    result = run(["categories", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("categories"), list) or len(data["categories"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected categories[] with at least one result")
        return False
    return True


results.append(test("categories returns categories[]", test_categories))


def test_search():
    result = run(["search", "airpods", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] in search response")
        return False
    return True


results.append(test("search airpods returns products[]", test_search))


def test_trending():
    result = run(["trending", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("trending"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected trending[] in trending response")
        return False
    return True


results.append(test("trending returns trending[]", test_trending))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
