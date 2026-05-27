#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

# Auckland CBD — dense urban, many results expected
AUCKLAND_LAT, AUCKLAND_LON = "-36.8485", "174.7633"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=45,
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

# 2. categories
results.append(test("categories lists filters", lambda: (
    (r := run(["categories"])).returncode == 0 and "food" in r.stdout
)))

# 3. nearby all categories (Auckland CBD)
results.append(test("nearby all categories returns results", lambda: (
    (r := run(["nearby", AUCKLAND_LAT, AUCKLAND_LON, "--radius", "2000", "--limit", "5", "--json"])).returncode == 0 and
    isinstance(json.loads(r.stdout).get("results"), list) and
    len(json.loads(r.stdout)["results"]) >= 3
)))

# 4. nearby food filter
results.append(test("nearby --category food returns restaurants/cafes", lambda: (
    (r := run(["nearby", AUCKLAND_LAT, AUCKLAND_LON, "--category", "food", "--limit", "5", "--json"])).returncode == 0 and
    isinstance(json.loads(r.stdout).get("results"), list) and
    len(json.loads(r.stdout)["results"]) >= 1
)))

# 5. nearby transport
results.append(test("nearby --category transport returns bus/train stops", lambda: (
    (r := run(["nearby", AUCKLAND_LAT, AUCKLAND_LON, "--category", "transport", "--limit", "5", "--json"])).returncode == 0 and
    isinstance(json.loads(r.stdout).get("results"), list) and
    len(json.loads(r.stdout)["results"]) >= 1
)))

# 6. nearby — JSON has distance_m, walking_min fields
results.append(test("nearby results have distance/travel fields", lambda: (
    (r := run(["nearby", AUCKLAND_LAT, AUCKLAND_LON, "--radius", "1000", "--category", "food", "--limit", "3", "--json"])).returncode == 0 and
    all(
        "distance_m" in x and "walking_min" in x and "travel_mode" in x
        for x in json.loads(r.stdout).get("results", [])
    )
)))

# 7. nearby invalid category errors cleanly
results.append(test("nearby --category invalid errors cleanly", lambda: (
    (r := run(["nearby", AUCKLAND_LAT, AUCKLAND_LON, "--category", "nonexistent"])).returncode != 0 and
    "unknown category" in r.stderr.lower()
)))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
