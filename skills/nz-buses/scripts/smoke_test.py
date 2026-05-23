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


def test_routes():
    if not os.environ.get("METLINK_API_KEY"):
        print("  [SKIP] requires METLINK_API_KEY")
        return True
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


results.append(test("routes returns routes[] (skips without METLINK_API_KEY)", test_routes))


def test_stops():
    if not os.environ.get("METLINK_API_KEY"):
        print("  [SKIP] requires METLINK_API_KEY")
        return True
    result = run(["stops", "wellington", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stops"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stops[] in response")
        return False
    return True


results.append(test("stops wellington returns stops[] (skips without METLINK_API_KEY)", test_stops))


def test_alerts():
    if not os.environ.get("METLINK_API_KEY"):
        print("  [SKIP] requires METLINK_API_KEY")
        return True
    result = run(["alerts", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("alerts"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected alerts[] in response")
        return False
    return True


results.append(test("alerts returns alerts[] (skips without METLINK_API_KEY)", test_alerts))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
