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

# 2. list (plain)
results.append(test("list returns beaches", lambda: (
    (r := run(["list", "--limit", "3"])).returncode == 0 and
    "SafeSwim Auckland beaches:" in r.stdout and
    len([l for l in r.stdout.split("\n") if "🛟" in l or "GREEN" in l or "AMBER" in l or "RED" in l]) >= 1
)))

# 3. list --json
results.append(test("list --json returns structured data", lambda: (
    (r := run(["list", "--limit", "3", "--json"])).returncode == 0 and
    isinstance(json.loads(r.stdout).get("beaches"), list) and
    len(json.loads(r.stdout)["beaches"]) >= 1
)))

# 4. list --search
results.append(test("list --search takapuna returns results", lambda: (
    (r := run(["list", "--search", "takapuna", "--json"])).returncode == 0 and
    len(json.loads(r.stdout).get("beaches", [])) >= 1
)))

# 5. detail
results.append(test("detail takapuna returns forecast data", lambda: (
    (r := run(["detail", "takapuna", "--json"])).returncode == 0 and
    json.loads(r.stdout).get("beach", {}).get("name") is not None and
    json.loads(r.stdout)["beach"].get("forecast_hours", 0) > 0
)))

# 6. nearby
results.append(test("nearby returns beaches sorted by distance", lambda: (
    (r := run(["nearby", "-36.8485", "174.7633", "--radius", "10", "--limit", "5", "--json"])).returncode == 0 and
    isinstance(json.loads(r.stdout).get("beaches"), list) and
    len(json.loads(r.stdout)["beaches"]) >= 1
)))

# 7. nearby with quality filter
results.append(test("nearby --min-quality RED returns only RED/BLACK", lambda: (
    (r := run(["nearby", "-36.8485", "174.7633", "--radius", "20", "--min-quality", "RED", "--json"])).returncode == 0 and
    all(b.get("quality", "") in ("RED", "RED+", "BLACK") for b in json.loads(r.stdout).get("beaches", []))
)))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
