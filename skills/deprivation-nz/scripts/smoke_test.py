#!/usr/bin/env python3
import json
import importlib.util
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
        timeout=60,
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


def test_fixture_arcgis_helpers():
    spec = importlib.util.spec_from_file_location("deprivation_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    data = {"features": [{"attributes": {"SA12023_V1_00": "7000000", "NZDep2023": "10"}}]}
    rows = cli.features(data)
    return len(rows) == 1 and cli.as_int(rows[0]["NZDep2023"]) == 10 and cli.decile_band(10).startswith("most deprived")


results.append(test("fixture ArcGIS feature and deprivation normalization", test_fixture_arcgis_helpers))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_sa1():
    result = run(["sa1", "--code", "7000000", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("sa1_code") != "7000000":
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sa1_code 7000000")
        return False
    if data.get("nzdep2023_decile") is None:
        print("  Expected nzdep2023_decile to be set")
        return False
    if data.get("population_2023") is None:
        print("  Expected population_2023 to be set")
        return False
    return True


results.append(test("sa1 returns decile and population", test_sa1))


def test_sa2():
    result = run(["sa2", "--code", "127100", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("sa2_code") != "127100":
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sa2_code 127100")
        return False
    if data.get("average_nzdep2023_decile") is None:
        print("  Expected average_nzdep2023_decile to be set")
        return False
    return True


results.append(test("sa2 returns average decile", test_sa2))


def test_search():
    result = run(["search", "--name", "Auckland", "--level", "sa2", "--limit", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("results"), list) or data.get("count", 0) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one search result")
        return False
    return True


results.append(test("search returns results", test_search))


def test_decile():
    result = run(["decile", "--value", "10", "--level", "sa2", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("decile") != 10 or not isinstance(data.get("results"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected decile 10 with results list")
        return False
    return True


results.append(test("decile lists areas", test_decile))


def test_region():
    result = run(["region", "--sa3", "Northcote (Auckland)", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("count", 0) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one SA2 area in region")
        return False
    return True


results.append(test("region lists SA2 areas", test_region))


def test_stats():
    result = run(["stats", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("total_sa1_areas") is None or len(data.get("distribution", [])) != 10:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected total_sa1_areas and 10 deciles")
        return False
    return True


results.append(test("stats returns decile distribution", test_stats))


def test_bad_code():
    result = run(["sa1", "--code", "abc"])
    if result.returncode == 0:
        print("  Expected non-zero exit for invalid code")
        return False
    return True


results.append(test("invalid SA1 code exits non-zero", test_bad_code))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
