#!/usr/bin/env python3
import json
import importlib.util
import os
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


def test_fixture_weather_helpers():
    spec = importlib.util.spec_from_file_location("metservice_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    location = cli.resolve_location("auckland")
    return location["name"] == "Auckland CBD" and cli.deg_to_compass(225) == "SW" and cli.num(12.345, 1) == "12.3"


results.append(test("fixture location and weather-value normalization", test_fixture_weather_helpers))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_warnings():
    # CRITICAL: must work without METOCEAN_API_KEY
    result = run(["warnings", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("warnings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected warnings[] in response")
        return False
    return True


results.append(test("warnings returns warnings[] (no API key needed)", test_warnings))


def test_locations():
    result = run(["locations", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, list) or len(data) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected list of locations")
        return False
    return True


results.append(test("locations returns list of known locations", test_locations))


def test_now():
    if not os.environ.get("METOCEAN_API_KEY"):
        print("  [SKIP] requires METOCEAN_API_KEY")
        return True
    result = run(["now", "auckland", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from now")
        return False
    return True


results.append(test("now auckland returns dict (skips without METOCEAN_API_KEY)", test_now))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
