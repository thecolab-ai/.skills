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
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
