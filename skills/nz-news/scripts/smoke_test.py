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
    if not isinstance(data.get("top5"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected top5[] in summary response")
        return False
    if data.get("sourcesOk", 0) < 1:
        print("  Expected at least one source to be OK")
        return False
    return True


results.append(test("summary returns top5[] with sources", test_summary))


def test_headlines():
    result = run(["headlines", "--limit", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("items"), list) or len(data["items"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected items[] with at least one headline")
        return False
    return True


results.append(test("headlines returns items[]", test_headlines))


def test_search():
    result = run(["search", "cyclone", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("items"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected items[] in search response")
        return False
    return True


results.append(test("search cyclone returns items[]", test_search))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
