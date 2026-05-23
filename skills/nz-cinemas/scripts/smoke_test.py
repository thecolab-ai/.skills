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


def test_cinemas():
    result = run(["cinemas", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("cinemas"), list) or len(data["cinemas"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected cinemas[] with at least one result")
        return False
    return True


results.append(test("cinemas returns cinemas[]", test_cinemas))


def test_movies():
    result = run(["movies", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("movies"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected movies[] in response")
        return False
    return True


results.append(test("movies returns movies[]", test_movies))


def test_nowplaying():
    result = run(["nowplaying", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("sessions"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sessions[] in nowplaying response")
        return False
    return True


results.append(test("nowplaying returns sessions[]", test_nowplaying))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
