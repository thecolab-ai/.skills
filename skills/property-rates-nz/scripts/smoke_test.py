#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

# Known Auckland Council property ID — Auckland Town Hall
TOWN_HALL_ID = "12343300679"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=30,
    )


def test(name: str, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def live_rates_json():
    result = run(["rates", TOWN_HALL_ID, "--json"])
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        if "network error" in detail.lower() or "blocked after" in detail.lower():
            print("[SKIP] Auckland Council live rates assertion: upstream unavailable")
            return None
    return result

# 1. help
results.append(test("--help exits 0", lambda: run(["--help"]).returncode == 0))

# 2. rates — invalid ID format fails before any network request and preserves JSON errors
results.append(test("rates with nonnumeric ID returns JSON error", lambda: (
    (r := run(["rates", "abc/../123", "--json"])).returncode != 0 and
    (data := json.loads(r.stderr)) and
    "numeric" in data.get("error", "").lower()
)))

# 3. rates — JSON
def test_live_json_values():
    r = live_rates_json()
    if r is None:
        return True
    data = json.loads(r.stdout)
    return data.get("property", {}).get("capital_value") is not None and data["property"].get("annual_rates") is not None


results.append(test(f"rates {TOWN_HALL_ID} --json returns CV and rates", test_live_json_values))

# 4. rates — human-readable
def test_live_human_values():
    r = run(["rates", TOWN_HALL_ID])
    if r.returncode != 0 and ("network error" in (r.stderr or r.stdout).lower() or "blocked after" in (r.stderr or r.stdout).lower()):
        print("[SKIP] Auckland Council live human assertion: upstream unavailable")
        return True
    return r.returncode == 0 and "Capital Value" in r.stdout and "Annual Rates" in r.stdout


results.append(test(f"rates {TOWN_HALL_ID} prints CV and rates", test_live_human_values))

# 5. rates — invalid ID errors cleanly
results.append(test("rates with invalid ID errors cleanly", lambda: (
    (r := run(["rates", "00000000000"])).returncode != 0 or
    "no valuation data" in r.stdout.lower() or
    "API returned empty" in r.stdout
)))

# 6. rates JSON has all expected fields
def test_live_json_structure():
    r = live_rates_json()
    if r is None:
        return True
    prop = json.loads(r.stdout).get("property", {})
    return bool(prop) and all(k in prop for k in ["property_id", "capital_value", "land_value", "annual_rates", "rates_url"])


results.append(test(f"rates {TOWN_HALL_ID} JSON has full property structure", test_live_json_structure))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
