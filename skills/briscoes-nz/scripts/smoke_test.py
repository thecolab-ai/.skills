#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("briscoes_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)


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


def test_fixture_klevu_product_parser():
    product = fixture_cli.parse_klevu_product(
        {
            "sku": "FIX-1",
            "name": "Fixture Towel",
            "salePrice": "19.99",
            "basePrice": "29.99",
            "isDiscountPrice": "yes",
            "inStock": "true",
            "currency": "NZD",
            "url": "https://www.briscoes.co.nz/product/fixture/",
        }
    )
    return bool(
        product["sku"] == "FIX-1"
        and product["sale_price"] == 19.99
        and product["save_price"] == 10.0
        and product["is_special"] is True
        and product["in_stock"] is True
    )


results.append(test("fixture Klevu product parser", test_fixture_klevu_product_parser))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

# search towel and capture sku for subsequent test
_search_sku = "1129433"


def test_search():
    global _search_sku
    result = run(["search", "towel", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list) or len(search["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Briscoes search JSON to include products[]")
        return False
    sku = search["products"][0].get("sku")
    if sku:
        _search_sku = str(sku)
    return True


results.append(test("search towel returns products[]", test_search))


def test_product():
    result = run(["product", _search_sku, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    product = json.loads(result.stdout)
    if not isinstance(product.get("products"), list) or len(product["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Briscoes product JSON to include a SKU product")
        return False
    if not product["products"][0].get("sku"):
        print("  Expected Briscoes product JSON to include a SKU product")
        return False
    return True


results.append(test("product <sku> returns products[].sku", test_product))


def test_stores_auckland():
    result = run(["stores", "--region", "auckland", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    stores = json.loads(result.stdout)
    if not isinstance(stores.get("stores"), list) or len(stores["stores"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Briscoes stores JSON to include Auckland stores[]")
        return False
    return True


results.append(test("stores --region auckland returns stores[]", test_stores_auckland))


def test_stores_wellington():
    result = run(["stores", "--region", "wellington", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    wellington_stores = json.loads(result.stdout)
    if not isinstance(wellington_stores.get("stores"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Briscoes Wellington stores to be a list")
        return False
    # Wellington filter must not include Auckland stores
    for store in wellington_stores["stores"]:
        city = str(store.get("city") or "").lower()
        if city == "auckland":
            print("  Expected Wellington store filter not to include Auckland street-address matches")
            return False
    return True


results.append(test("stores --region wellington does not include Auckland", test_stores_wellington))


def test_specials():
    result = run(["specials", "towel", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    specials = json.loads(result.stdout)
    if not isinstance(specials.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Briscoes specials JSON to include products[]")
        return False
    for p in specials["products"]:
        price = float(p.get("price") or 0)
        sale_price = float(p.get("sale_price") or 0)
        save_price = float(p.get("save_price") or 0)
        if not (price > 0 and sale_price > 0 and sale_price < price and save_price > 0):
            print(f"  Expected every Briscoes specials product to have a verified discount: {p}")
            return False
        haystack = f"{p.get('name') or ''} {p.get('category') or ''} {p.get('source_url') or ''}".lower()
        if "towel" not in haystack:
            print(f"  Expected Briscoes specials towel query to constrain returned products: {p}")
            return False
    return True


results.append(test("specials towel returns discounted towel products", test_specials))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
