#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
USE_BROWSER = os.environ.get("COLAB_SMOKE_USE_BROWSER") == "1"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=120,
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


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_operators():
    result = run(["operators", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("operators"), list) or len(data["operators"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected operators[] with at least one result")
        return False
    return True


results.append(test("operators returns operators[]", test_operators))


def test_routes():
    result = run(["routes", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("routes"), list) or len(data["routes"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected routes[] with at least one result")
        return False
    return True


results.append(test("routes returns routes[]", test_routes))


def test_cook_strait():
    result = run(["cook-strait", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("sailings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sailings[] in cook-strait response")
        return False
    return True


results.append(test("cook-strait returns sailings[]", test_cook_strait))


def test_fullers_browser_probe():
    if not USE_BROWSER:
        return True
    result = run(["sailings", "auckland-devonport", "--json", "--browser"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    probe = data.get("browser_probe")
    if not isinstance(probe, dict) or probe.get("status") not in {"loaded", "blocked"}:
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected browser_probe with loaded/blocked status")
        return False
    if not isinstance(data.get("sailings"), list):
        print("  Expected AT GTFS fallback sailings[] alongside browser probe")
        return False
    return True


results.append(test("fullers browser probe returns status", test_fullers_browser_probe))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
