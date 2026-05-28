#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=30,
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


def parse_json(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


results = []

results.append(test("--help exits 0", lambda: run(["--help"]).returncode == 0))

results.append(test("list returns locations", lambda: (
    (r := run(["list", "--limit", "3"])).returncode == 0 and
    "SafeSwim NZ locations:" in r.stdout and
    len([line for line in r.stdout.splitlines() if any(code in line for code in ("GREEN", "AMBER", "RED", "BLACK"))]) >= 1
)))

results.append(test("list --json returns structured data", lambda: (
    (data := parse_json(["list", "--limit", "3", "--json"])).get("kind") == "list" and
    isinstance(data.get("locations"), list) and
    len(data["locations"]) >= 1
)))

results.append(test("list --search takapuna returns results", lambda: (
    len(parse_json(["list", "--search", "takapuna", "--json"]).get("locations", [])) >= 1
)))

results.append(test("detail takapuna returns forecast data", lambda: (
    (data := parse_json(["detail", "takapuna", "--json"])).get("kind") == "detail" and
    data.get("location", {}).get("name") is not None and
    data["location"].get("forecast_hours", 0) > 0
)))

results.append(test("nearby returns locations sorted by distance", lambda: (
    (data := parse_json(["nearby", "-36.8485", "174.7633", "--radius", "10", "--limit", "5", "--json"])).get("kind") == "nearby" and
    isinstance(data.get("locations"), list) and
    len(data["locations"]) >= 1 and
    [item["distance_km"] for item in data["locations"]] == sorted(item["distance_km"] for item in data["locations"])
)))

results.append(test("nearby --min-risk RED returns only RED or worse", lambda: (
    all(
        item.get("quality", "") in ("RED", "RED+", "BLACK")
        for item in parse_json(["nearby", "-36.8485", "174.7633", "--radius", "20", "--min-risk", "RED", "--json"]).get("locations", [])
    )
)))

results.append(test("invalid coordinates fail before fetching", lambda: (
    (r := run(["nearby", "91", "174", "--json"])).returncode == 2 and
    "between -90 and 90" in r.stderr
)))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
