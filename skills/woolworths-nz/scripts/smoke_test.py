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
        timeout=45,
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


def test_product_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("woolworths_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.parse_product(
        {
            "sku": "705692",
            "name": "Synthetic Milk",
            "brand": "Example",
            "slug": "synthetic-milk",
            "price": {"originalPrice": 4.5, "salePrice": 3.9, "isSpecial": True, "savePrice": 0.6},
            "size": {"volumeSize": "2L", "cupPrice": 0.20, "cupMeasure": "100ml"},
            "quantity": {"min": 1, "max": 12, "increment": 1},
            "availabilityStatus": "In Stock",
            "breadcrumb": {"department": {"name": "Fresh"}, "aisle": {"name": "Dairy"}},
        }
    )
    assert record["sku"] == "705692"
    assert record["sale_price"] == 3.9
    assert record["is_special"] is True and record["in_stock"] is True
    assert record["category"] == "Fresh / Dairy"
    print("[PASS] fixture Woolworths product normalisation")
    return True


results.append(test("fixture product parser", test_product_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_search_sku = "705692"


def test_search():
    global _search_sku
    result = run(["search", "milk", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list) or len(search["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths search JSON to include products[]")
        return False
    sku = search["products"][0].get("sku")
    if sku:
        _search_sku = str(sku)
    return True


results.append(test("search milk returns products[]", test_search))


def test_product():
    result = run(["product", _search_sku, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    product = json.loads(result.stdout)
    if not isinstance(product.get("products"), list) or len(product["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths product JSON to include a SKU product")
        return False
    if not product["products"][0].get("sku"):
        print("  Expected Woolworths product JSON to include a SKU product")
        return False
    return True


results.append(test("product <sku> returns products[].sku", test_product))


def test_specials():
    result = run(["specials", "cheese", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    specials = json.loads(result.stdout)
    if not isinstance(specials.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Woolworths specials JSON to include products[]")
        return False
    return True


results.append(test("specials cheese returns products[]", test_specials))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
