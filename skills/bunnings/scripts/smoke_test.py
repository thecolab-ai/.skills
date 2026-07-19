#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("bunnings_fixture_cli", CLI)
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


def test_fixture_product_parser():
    product = fixture_cli.parse_raw_product(
        {
            "code": "FIX-1",
            "name": "Fixture Drill",
            "price": 99.0,
            "currency": "NZD",
            "productroutingurl": "/fixture-drill_p0001",
            "supercategories": ["Tools--tools", "Power Tools--power-tools"],
            "newarrival": "true",
        },
        fixture_cli.country_cfg("nz"),
    )
    return bool(
        product["sku"] == "FIX-1"
        and product["price"] == 99.0
        and product["currency"] == "NZD"
        and product["category"] == "Tools / Power Tools"
        and product["source_url"].startswith("https://www.bunnings.co.nz/")
    )


results.append(test("fixture search product parser", test_fixture_product_parser))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_search():
    result = run(["search", "drill", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list) or len(data["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] with at least one result")
        return False
    return True


results.append(test("search drill returns products[]", test_search))


def test_stores():
    result = run(["stores", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stores"), list) or len(data["stores"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stores[] with at least one result")
        return False
    return True


results.append(test("stores returns stores[]", test_stores))


def test_browse():
    result = run(["browse", "tools/power-tools/drills", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] in browse response")
        return False
    return True


results.append(test("browse tools/power-tools/drills returns products[]", test_browse))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
