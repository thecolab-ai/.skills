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
        timeout=120,
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
    return run(["--help"]).returncode == 0


results.append(test("--help exits 0", test_help))


def _estimates(args, group_key):
    result = run(args)
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return None
    data = json.loads(result.stdout)
    estimates = data.get("estimates")
    if not isinstance(estimates, list) or not estimates:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected non-empty estimates[]")
        return None
    first = estimates[0]
    if group_key not in first:
        print(f"  Expected '{group_key}' in estimate: {first}")
        return None
    return estimates


def test_hardship_region():
    estimates = _estimates(["hardship", "--region", "auckland", "--json"], "region")
    if estimates is None:
        return False
    if not any(e.get("households") is not None for e in estimates):
        print("  Expected at least one households count")
        return False
    return True


results.append(test("hardship --region auckland returns estimates", test_hardship_region))


def test_hardship_ethnicity():
    estimates = _estimates(["hardship", "--ethnicity", "--json"], "ethnicity")
    return estimates is not None


results.append(test("hardship --ethnicity returns estimates", test_hardship_ethnicity))


def test_affordability_lowincome():
    estimates = _estimates(
        ["affordability", "--ethnicity", "--threshold", "30", "--lowincome", "--json"],
        "ethnicity",
    )
    if estimates is None:
        return False
    if not all("More than 30%" == e.get("affordability") for e in estimates):
        print("  Expected all rows at the 30% threshold")
        return False
    return True


results.append(test("affordability --lowincome --threshold 30 filters rows", test_affordability_lowincome))


def test_gini():
    result = run(["gini", "--region", "auckland", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    est = (data.get("estimates") or [{}])[0]
    if not isinstance(est.get("gini"), (int, float)):
        print(f"  Expected numeric gini, got: {est}")
        return False
    return True


results.append(test("gini --region auckland returns numeric gini", test_gini))


def test_search():
    result = run(["search", "warm and dry", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("datasets"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected datasets[] in search response")
        return False
    return True


results.append(test("search returns datasets list", test_search))


def test_bad_region_fails():
    result = run(["hardship", "--region", "nowhere", "--json"])
    if result.returncode == 0:
        print("  Expected non-zero exit for unknown region")
        return False
    return True


results.append(test("unknown region exits non-zero", test_bad_region_fails))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
