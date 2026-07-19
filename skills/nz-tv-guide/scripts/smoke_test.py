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


def test_freeview_range_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_tv_guide_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    parsed = module.parse_freeview_range("2026-07-19", "11:30 PM - 12:15 AM")
    assert parsed is not None
    start, end = parsed
    assert start.isoformat().startswith("2026-07-19T23:30")
    assert end.isoformat().startswith("2026-07-20T00:15")
    print("[PASS] fixture Freeview overnight time-range parser")
    return True


results.append(test("fixture programme range parser", test_freeview_range_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_channels():
    result = run(["channels", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("channels"), list) or len(data["channels"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected channels[] with at least one result")
        return False
    return True


results.append(test("channels returns channels[]", test_channels))


def test_tonight():
    result = run(["tonight", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("programmes"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected programmes[] in tonight response")
        return False
    return True


results.append(test("tonight returns programmes[]", test_tonight))


def test_now():
    result = run(["now", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("programmes"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected programmes[] in now response")
        return False
    return True


results.append(test("now returns programmes[]", test_now))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
