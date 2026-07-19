#!/usr/bin/env python3
import json
import os
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


def test_airports():
    result = run(["airports", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("airports"), list) or len(data["airports"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected airports[] with at least one result")
        return False
    codes = [a.get("code") for a in data["airports"]]
    if "AKL" not in codes:
        print("  Expected AKL in airport list")
        return False
    return True


results.append(test("airports returns airports[] containing AKL", test_airports))


def test_arrivals_akl():
    if not (os.environ.get("AKL_API_USERNAME") and os.environ.get("AKL_API_PASSWORD")):
        print("  [SKIP] missing configuration: AKL_API_USERNAME/AKL_API_PASSWORD")
        return True
    result = run(["arrivals", "--airport", "AKL", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("flights"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected flights[] in arrivals response")
        return False
    return True


results.append(test("arrivals AKL returns flights[]", test_arrivals_akl))


def test_departures_akl():
    if not (os.environ.get("AKL_API_USERNAME") and os.environ.get("AKL_API_PASSWORD")):
        print("  [SKIP] missing configuration: AKL_API_USERNAME/AKL_API_PASSWORD")
        return True
    result = run(["departures", "--airport", "AKL", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("flights"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected flights[] in departures response")
        return False
    return True


results.append(test("departures AKL returns flights[]", test_departures_akl))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
