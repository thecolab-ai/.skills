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

    spec = importlib.util.spec_from_file_location("gaspy_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rows = module.price_rows(
        {
            "gaspy": {"national": {"1": {"average": 249.9, "minimum": 229.9, "maximum": 269.9, "count": 100}}},
            "datamine": {"Averages": {"91": {"28DayChange": -3.2, "28DayPercent": -1.25}}},
        }
    )
    assert len(rows) == 1
    assert rows[0]["fuel"] == "91"
    assert rows[0]["average"] == 249.9
    assert rows[0]["change_28d_cents"] == -3.2
    print("[PASS] fixture Gaspy national-price normalisation")
    return True


results.append(test("fixture national price parser", test_price_rows_fixture))


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
    if not isinstance(data.get("prices"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected prices[] in summary response")
        return False
    return True


results.append(test("summary returns prices[]", test_summary))


def test_fuel_types():
    result = run(["fuel-types", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("fuel_types"), list) or len(data["fuel_types"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected fuel_types[] with at least one result")
        return False
    return True


results.append(test("fuel-types returns fuel_types[]", test_fuel_types))


def test_prices():
    result = run(["prices", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("prices"), list) or len(data["prices"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected prices[] with at least one result")
        return False
    return True


results.append(test("prices returns prices[]", test_prices))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
