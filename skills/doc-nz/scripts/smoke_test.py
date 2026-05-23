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


def test_great_walks():
    result = run(["great-walks", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("great_walks"), list) or len(data["great_walks"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected great_walks[] with at least one result")
        return False
    return True


results.append(test("great-walks returns great_walks[]", test_great_walks))


def test_alerts():
    result = run(["alerts", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("regions"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected regions[] in alerts response")
        return False
    return True


results.append(test("alerts returns regions[]", test_alerts))


def test_huts():
    result = run(["huts", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("places"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected places[] in huts response")
        return False
    return True


results.append(test("huts returns places[]", test_huts))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
