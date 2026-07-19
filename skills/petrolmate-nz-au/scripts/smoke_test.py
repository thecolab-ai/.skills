#!/usr/bin/env python3
"""Smoke test for petrolmate-nz-au skill — basic API smoke tests, no live data quality checks."""
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


def test_distance_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("petrolmate_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    distance = module.haversine_km(-36.8485, 174.7633, -41.2866, 174.7756)
    assert 490 < distance < 500
    assert module.fmt_price("249.9") == "$2.499"
    assert module.fmt_dist(1500) == "1.5km"
    print("[PASS] fixture PetrolMate distance and price normalisation")
    return True


results.append(test("fixture station result normalisation", test_distance_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_fuel_types():
    result = run(["fuel-types"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    for code in ("ULP", "DIESEL", "PULP95", "PULP98", "B20", "DIESEL_PREMIUM"):
        if code not in result.stdout:
            print(f"  Missing fuel type: {code}")
            return False
    return True


results.append(test("fuel-types lists all codes", test_fuel_types))


def test_locations():
    result = run(["locations"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    for loc in ("auckland", "wellington", "sydney", "brisbane"):
        if loc not in result.stdout:
            print(f"  Missing location: {loc}")
            return False
    return True


results.append(test("locations lists AU+NZ names", test_locations))


def test_search_json():
    result = run(["search", "--location", "auckland", "--fuel", "ULP", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stations"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stations[] in search response")
        return False
    return True


results.append(test("search auckland ULP returns stations[]", test_search_json))


def test_search_geoip():
    result = run(["search", "--geoip", "--fuel", "DIESEL", "--radius", "100", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stations"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stations[] in geoip response")
        return False
    return True


results.append(test("search --geoip returns stations[]", test_search_geoip))


if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
