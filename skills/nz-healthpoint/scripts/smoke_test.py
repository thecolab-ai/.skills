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
    if not isinstance(data.get("regions"), list) or len(data["regions"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected regions[] with at least one result")
        return False
    return True


results.append(test("categories returns categories[] and regions[]", test_categories))


def test_pharmacies():
    result = run(["pharmacies", "--region", "Nelson Marlborough", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("results"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected results[] in pharmacies response")
        return False
    return True


results.append(test("pharmacies Nelson Marlborough returns results[]", test_pharmacies))


def test_hospitals():
    result = run(["hospitals", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("results"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected results[] in hospitals response")
        return False
    return True


results.append(test("hospitals returns results[]", test_hospitals))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
