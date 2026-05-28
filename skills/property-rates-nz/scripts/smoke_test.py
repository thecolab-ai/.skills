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

# 1. help
results.append(test("--help exits 0", lambda: run(["--help"]).returncode == 0))

# 2. rates — invalid ID format fails before any network request and preserves JSON errors
results.append(test("rates with nonnumeric ID returns JSON error", lambda: (
    (r := run(["rates", "abc/../123", "--json"])).returncode != 0 and
    (data := json.loads(r.stderr)) and
    "numeric" in data.get("error", "").lower()
)))

# 3. rates — JSON
results.append(test(f"rates {TOWN_HALL_ID} --json returns CV and rates", lambda: (
    (r := run(["rates", TOWN_HALL_ID, "--json"])).returncode == 0 and
    (data := json.loads(r.stdout)) and
    data.get("property", {}).get("capital_value") is not None and
    data["property"].get("annual_rates") is not None
)))

# 4. rates — human-readable
results.append(test(f"rates {TOWN_HALL_ID} prints CV and rates", lambda: (
    (r := run(["rates", TOWN_HALL_ID])).returncode == 0 and
    "Capital Value" in r.stdout and
    "Annual Rates" in r.stdout
)))

# 5. rates — invalid ID errors cleanly
results.append(test("rates with invalid ID errors cleanly", lambda: (
    (r := run(["rates", "00000000000"])).returncode != 0 or
    "no valuation data" in r.stdout.lower() or
    "API returned empty" in r.stdout
)))

# 6. rates JSON has all expected fields
results.append(test(f"rates {TOWN_HALL_ID} JSON has full property structure", lambda: (
    (r := run(["rates", TOWN_HALL_ID, "--json"])).returncode == 0 and
    (data := json.loads(r.stdout)) and
    (prop := data.get("property", {})) and
    all(k in prop for k in ["property_id", "capital_value", "land_value", "annual_rates", "rates_url"])
)))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
