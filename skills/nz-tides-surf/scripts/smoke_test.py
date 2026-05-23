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


def test_ports():
    result = run(["ports", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("ports"), list) or len(data["ports"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected ports[] with at least one result")
        return False
    return True


results.append(test("ports returns ports[]", test_ports))


def test_next_tide():
    result = run(["next-tide", "Wellington", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("next_high") and not data.get("next_low"):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected next_high or next_low in response")
        return False
    return True


results.append(test("next-tide Wellington returns next_high or next_low", test_next_tide))


def test_breaks():
    result = run(["breaks", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("breaks"), list) or len(data["breaks"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected breaks[] with at least one result")
        return False
    return True


results.append(test("breaks returns breaks[]", test_breaks))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
