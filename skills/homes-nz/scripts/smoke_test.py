#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

# Known regression test property
REGRESSION_ADDRESS = "65 Riverside Drive Whangarei"
REGRESSION_PROPERTY_ID = "c1bf1078-9c44-4f03-b9e0-b2ada7a4f992"


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


def test_address_regression():
    result = run(["address", REGRESSION_ADDRESS, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("matches"), list) or len(data["matches"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected matches[] with at least one result")
        return False
    found_id = None
    for match in data["matches"]:
        if match.get("property_id") == REGRESSION_PROPERTY_ID:
            found_id = match["property_id"]
            break
    if not found_id:
        returned_ids = [m.get("property_id") for m in data["matches"]]
        print(f"  REGRESSION FAIL: expected property_id {REGRESSION_PROPERTY_ID}")
        print(f"  Got: {returned_ids}")
        return False
    return True


results.append(test(
    f"address '{REGRESSION_ADDRESS}' returns property_id {REGRESSION_PROPERTY_ID}",
    test_address_regression,
))


def test_property():
    result = run(["property", REGRESSION_PROPERTY_ID, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("property"), dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected property{} in response")
        return False
    pid = data["property"].get("property_id")
    if pid != REGRESSION_PROPERTY_ID:
        print(f"  Expected property_id {REGRESSION_PROPERTY_ID}, got {pid}")
        return False
    return True


results.append(test(
    f"property {REGRESSION_PROPERTY_ID} returns property.property_id",
    test_property,
))


def test_nearby():
    result = run(["nearby", REGRESSION_PROPERTY_ID, "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("comparables"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected comparables[] in nearby response")
        return False
    return True


results.append(test(f"nearby {REGRESSION_PROPERTY_ID} returns comparables[]", test_nearby))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
