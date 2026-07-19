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


def test_event_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_road_closures_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalize_event(
        {
            "properties": {
                "id": "SYN-1",
                "type": "closures",
                "EventType": "Road closure",
                "Impact": "Road closed",
                "Name": "Synthetic closure",
                "IsPlanned": "true",
            },
            "geometry": {"type": "Point", "coordinates": [174.76, -36.85]},
        },
        {},
    )
    assert record["id"] == "SYN-1"
    assert record["category"] == "closure"
    assert record["severity"] == "severe"
    assert record["is_planned"] is True
    assert record["geometry"]["type"] == "Point"
    print("[PASS] fixture NZTA event normalisation")
    return True


results.append(test("fixture closure event parser", test_event_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_regions():
    result = run(["regions", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("regions"), list) or len(data["regions"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected regions[] with at least one result")
        return False
    return True


results.append(test("regions returns regions[]", test_regions))


def test_closures():
    result = run(["closures", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("events"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected events[] in closures response")
        return False
    return True


results.append(test("closures returns events[]", test_closures))


def test_routes():
    result = run(["routes", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("routes"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected routes[] in response")
        return False
    return True


results.append(test("routes returns routes[]", test_routes))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
