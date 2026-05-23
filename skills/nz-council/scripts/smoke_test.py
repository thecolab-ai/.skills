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


def test_events():
    result = run(["events", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("events"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected events[] in response")
        return False
    return True


results.append(test("events returns events[]", test_events))


def test_pools():
    result = run(["pools", "--council", "akl", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("pools"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected pools[] in response")
        return False
    return True


results.append(test("pools akl returns pools[]", test_pools))


def test_facilities():
    result = run(["facilities", "--council", "akl", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("facilities"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected facilities[] in response")
        return False
    return True


results.append(test("facilities akl returns facilities[]", test_facilities))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
