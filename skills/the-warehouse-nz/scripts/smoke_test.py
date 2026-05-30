#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
USE_BROWSER = os.environ.get("HERMES_SMOKE_USE_BROWSER") == "1"


def with_browser(args: list) -> list:
    return args + (["--browser"] if USE_BROWSER else [])


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


def test_search():
    result = run(with_browser(["search", "toys", "--limit", "3", "--json"]))
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list) or len(data["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] with at least one result")
        return False
    return True


results.append(test("search toys returns products[]", test_search))


def test_stores():
    result = run(with_browser(["stores", "--json"]))
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stores"), list) or len(data["stores"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stores[] with at least one result")
        return False
    return True


results.append(test("stores returns stores[]", test_stores))


def test_specials():
    result = run(with_browser(["specials", "--limit", "3", "--json"]))
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] in specials response")
        return False
    return True


results.append(test("specials returns products[]", test_specials))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
