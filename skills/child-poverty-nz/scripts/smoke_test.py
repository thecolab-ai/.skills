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
        timeout=120,
    )


def test(name: str, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_help():
    return run(["--help"]).returncode == 0


results.append(test("--help exits 0", test_help))


def test_measures():
    result = run(["measures", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("count") != 9:
        print(f"  expected 9 measures, got {data.get('count')}")
        return False
    return True


results.append(test("measures lists 9 CPRA codes", test_measures))


def test_latest():
    result = run(["latest", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("year"), int):
        print("  expected integer year")
        return False
    primary = next((m for m in data.get("measures", []) if m["code"] == "MEASA"), None)
    if not primary or primary.get("proportion_percent") is None:
        print("  expected MEASA proportion_percent to be set")
        return False
    return True


results.append(test("latest returns headline measures", test_latest))


def test_national():
    result = run(["national", "--measure", "MEASA", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    latest = data.get("latest")
    if not isinstance(latest, dict) or latest.get("proportion_percent") is None:
        print(f"  stdout: {result.stdout[:200]}")
        return False
    return True


results.append(test("national returns latest.proportion_percent", test_national))


def test_breakdown():
    result = run(["breakdown", "--measure", "MEASA", "--by", "region", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("breakdown"):
        print("  expected non-empty breakdown")
        return False
    return True


results.append(test("breakdown by region returns rows", test_breakdown))


def test_releases():
    result = run(["releases", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("releases"):
        print("  expected at least one release")
        return False
    return True


results.append(test("releases discovers a CSV release", test_releases))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
