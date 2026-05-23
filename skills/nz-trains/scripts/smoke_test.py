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


def test_lines():
    if not os.environ.get("METLINK_API_KEY"):
        print("  [SKIP] requires METLINK_API_KEY")
        return True
    result = run(["lines", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("lines"), list) or len(data["lines"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected lines[] with at least one result")
        return False
    return True


results.append(test("lines returns lines[] (skips without METLINK_API_KEY)", test_lines))


def test_stations():
    if not os.environ.get("METLINK_API_KEY"):
        print("  [SKIP] requires METLINK_API_KEY")
        return True
    result = run(["stations", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stations"), list) or len(data["stations"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stations[] with at least one result")
        return False
    return True


results.append(test("stations returns stations[] (skips without METLINK_API_KEY)", test_stations))


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
