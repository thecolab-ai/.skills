#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("auckland_bin_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
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


def test_fixture_section_parser():
    lines = [
        "Household collection",
        "Rubbish:",
        "Friday, 1 August",
        "Rubbish",
        "Collection day:",
        "Every week",
        ".",
        "Put bins out before 7am",
        "Where you can put your rubbish, food scraps and recycling for collection",
    ]
    parsed = fixture_cli.parse_section(lines, "Household collection")
    return bool(
        parsed
        and parsed["next_dates"]["rubbish"] == "Friday, 1 August"
        and parsed["frequency"]["rubbish"] == "Every week"
        and parsed["put_out"] == "Put bins out before 7am"
    )


results.append(test("fixture household collection section parses", test_fixture_section_parser))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_list():
    result = run(["--list", "12 Tawa Road Onehunga", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("matches"), list) or len(data["matches"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one Auckland Council property match for 12 Tawa Road Onehunga")
        return False
    return True


results.append(test("--list '12 Tawa Road Onehunga' returns matches[]", test_list))


def test_schedule():
    result = run(["12 Tawa Road Onehunga", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    schedule = json.loads(result.stdout)
    if not schedule.get("property_id") or not schedule.get("household"):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected schedule JSON to include property_id and household collection data")
        return False
    return True


results.append(test("'12 Tawa Road Onehunga' returns property_id and household", test_schedule))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
