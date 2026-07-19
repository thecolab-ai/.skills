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


def test_series_row_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("stats_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.serialize_series_row(
        {
            "Period": "2026Q2",
            "Data_value": "123.45",
            "STATUS": "F",
            "UNITS": "Index",
            "MAGNITUDE": "0",
            "Series_title_1": "Synthetic series",
            "Series_title_2": "All groups",
        }
    )
    assert record["period"] == "2026Q2"
    assert record["value"] == 123.45
    assert record["magnitude"] == 0
    assert record["series_title"] == "Synthetic series - All groups"
    assert module.normalize_region("Wellington Region") == "wellington-region"
    print("[PASS] fixture Stats NZ CSV series-row normalisation")
    return True


results.append(test("fixture Stats NZ series parser", test_series_row_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_cpi():
    result = run(["cpi", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("latest"), dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected latest{} in cpi response")
        return False
    if data["latest"].get("value") is None:
        print("  Expected latest.value to be set")
        return False
    return True


results.append(test("cpi returns latest.value", test_cpi))


def test_fpi():
    result = run(["fpi", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("latest"), dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected latest{} in fpi response")
        return False
    if data["latest"].get("value") is None:
        print("  Expected latest.value to be set")
        return False
    return True


results.append(test("fpi returns latest.value", test_fpi))


def test_population():
    result = run(["population", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from population")
        return False
    return True


results.append(test("population returns dict", test_population))


def test_migration():
    result = run(["migration", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from migration")
        return False
    return True


results.append(test("migration returns dict", test_migration))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
