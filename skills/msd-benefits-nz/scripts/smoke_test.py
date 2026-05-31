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
        timeout=180,
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


def test_list_quarters():
    result = run(["list-quarters", "--csv", "national", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    quarters = data.get("quarters")
    if not isinstance(quarters, list) or "Dec_19" not in quarters:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected quarters list containing Dec_19")
        return False
    return True


results.append(test("list-quarters returns Sep_19", test_list_quarters))


def test_main_benefits():
    result = run(["main-benefits", "--quarter", "Sep_19", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("total_recipients"), int) or data["total_recipients"] <= 0:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected positive total_recipients")
        return False
    if not isinstance(data.get("breakdown"), list) or not data["breakdown"]:
        print("  Expected non-empty breakdown")
        return False
    return True


results.append(test("main-benefits returns total + breakdown", test_main_benefits))


def test_main_benefits_group():
    result = run(["main-benefits", "--quarter", "Sep_19", "--group", "jobseeker support", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("benefit_group") != "Jobseeker Support":
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected case-insensitive group resolution to 'Jobseeker Support'")
        return False
    return True


results.append(test("main-benefits resolves group case-insensitively", test_main_benefits_group))


def test_nz_super():
    result = run(["nz-super", "--quarter", "Sep_19", "--age-group", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("total_recipients"), int) or data["total_recipients"] <= 0:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected positive total_recipients for nz-super")
        return False
    return True


results.append(test("nz-super returns total", test_nz_super))


def test_trend():
    result = run(["trend", "--group", "Sole Parent Support", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    series = data.get("series")
    if not isinstance(series, list) or len(series) < 5:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected a multi-quarter series")
        return False
    if data.get("latest", {}).get("quarter") != "Dec_19":
        print("  Expected latest quarter Dec_19")
        return False
    return True


results.append(test("trend returns multi-quarter series", test_trend))


def test_bad_quarter():
    result = run(["main-benefits", "--quarter", "Sep_99", "--json"])
    if result.returncode == 0:
        print("  Expected non-zero exit for unknown quarter")
        return False
    return True


results.append(test("unknown quarter exits non-zero", test_bad_quarter))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
