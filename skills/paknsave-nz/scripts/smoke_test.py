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


def test_stores():
    result = run(["stores", "--query", "papakura", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    stores = json.loads(result.stdout)
    if not isinstance(stores, list) or len(stores) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one PAK'nSAVE store for Papakura")
        return False
    return True


results.append(test("stores --query papakura returns >= 1 result", test_stores))


def test_search():
    result = run(["search", "milk", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected PAK'nSAVE search JSON to include products[]")
        return False
    return True


results.append(test("search milk returns products[]", test_search))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
