#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("bookme_fixture_cli", CLI)
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


def test_fixture_deal_normalisation():
    deal = fixture_cli.normalize_deal(
        {
            "deal_id": "fixture-1",
            "deal_name": "Kayak &amp; Cruise",
            "price_raw": "49",
            "deal_saving": "Save $20",
            "reduction_raw": "29%",
            "activity_ref": "/things-to-do/auckland/activity/fixture",
        }
    )
    return bool(
        deal["title"] == "Kayak & Cruise"
        and deal["price"] == 49.0
        and deal["normal_price"] == 69.0
        and deal["discount_percent"] == 29.0
        and deal["region"] == "auckland"
    )


results.append(test("fixture deal normalisation", test_fixture_deal_normalisation))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_regions():
    result = run(["regions", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("regions"), list) or len(data["regions"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected regions[] with at least one result")
        return False
    return True


results.append(test("regions returns regions[]", test_regions))


def test_deals():
    result = run(["deals", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("deals"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected deals[] in response")
        return False
    return True


results.append(test("deals returns deals[]", test_deals))


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

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
