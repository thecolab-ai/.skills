#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
SKILL_NAME = "bunnings"

_ANTIBOT_SIGNALS = (
    "just a moment",
    "cloudflare",
    "attention required",
    "checking your browser",
    "status 403",
    "status 406",
    "http 403",
    "http 406",
    "403 forbidden",
)


def _is_antibot(result: subprocess.CompletedProcess) -> bool:
    combined = (result.stdout + result.stderr).lower()
    return any(sig in combined for sig in _ANTIBOT_SIGNALS)


def _skip_if_antibot(result: subprocess.CompletedProcess) -> None:
    if _is_antibot(result):
        print(f"[SKIP] {SKILL_NAME} — upstream anti-bot block")
        sys.exit(0)


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
    result = run(["search", "drill", "--limit", "3", "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list) or len(data["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] with at least one result")
        return False
    return True


results.append(test("search drill returns products[]", test_search))


def test_stores():
    result = run(["stores", "--limit", "3", "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stores"), list) or len(data["stores"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stores[] with at least one result")
        return False
    return True


results.append(test("stores returns stores[]", test_stores))


def test_browse():
    result = run(["browse", "tools/power-tools/drills", "--limit", "3", "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] in browse response")
        return False
    return True


results.append(test("browse tools/power-tools/drills returns products[]", test_browse))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
