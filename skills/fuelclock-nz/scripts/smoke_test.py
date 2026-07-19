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


def test_price_rows_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fuelclock_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rows = module.select_price_rows(
        [
            {"type": "Diesel", "price": 1.99, "stationCount": 20},
            {"type": "91 Unleaded", "price": 2.49, "stationCount": 30},
        ]
    )
    assert [row["fuel"] for row in rows] == ["91", "diesel"]
    assert rows[0]["price"] == 2.49
    assert rows[1]["stationCount"] == 20
    print("[PASS] fixture FuelClock price-row normalisation")
    return True


results.append(test("fixture price row parser", test_price_rows_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_summary():
    result = run(["summary", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from summary")
        return False
    return True


results.append(test("summary returns dict", test_summary))


def test_prices():
    result = run(["prices", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from prices")
        return False
    return True


results.append(test("prices returns dict", test_prices))


def test_supply():
    result = run(["supply", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from supply")
        return False
    return True


results.append(test("supply returns dict", test_supply))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
