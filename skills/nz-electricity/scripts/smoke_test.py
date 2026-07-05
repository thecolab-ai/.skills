#!/usr/bin/env python3
import json
import importlib.util
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

spec = importlib.util.spec_from_file_location("nz_electricity_cli", CLI)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cli)


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


def test_spot():
    result = run(["spot", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("prices"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected prices[] in spot response")
        return False
    return True


results.append(test("spot returns prices[]", test_spot))


def test_carbon():
    result = run(["carbon", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("readings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected readings[] in carbon response")
        return False
    return True


results.append(test("carbon returns readings[]", test_carbon))


def test_demand():
    result = run(["demand", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from demand")
        return False
    return True


results.append(test("demand returns dict", test_demand))


DG_SAMPLE = """Installed distributed generation trends

From www.emi.ea.govt.nz provided by the Electricity Authority (New Zealand)
Run at: 20260705203343

Parameters
Date range,01 Jan 2025 - 31 Dec 2025
Region type,New Zealand
Market segment,Residential
Capacity,All combined
Fuel type,Solar (all)

Month end,Region ID,Region name,Capacity,Fuel type,ICP count,ICP uptake rate (%),Total capacity installed (MW),Avg. capacity installed (kW),ICP count - new installations,Avg. capacity - new installations (kW)
31/01/2025,NZ,New Zealand,All combined,Solar (All),"64,571",3.25294,326.594,5.058,622,7.726
28/02/2025,NZ,New Zealand,All combined,Solar (All),65286,3.28550,332.142,5.087,760,
"""


def test_dg_parser_handles_metadata_and_numbers():
    parsed = cli.parse_dg_report_csv(DG_SAMPLE, "https://example.invalid/GUEHMT.csv")
    rows = parsed["rows"]
    if parsed["metadata"].get("run_at") != "20260705203343":
        print(f"  metadata: {parsed['metadata']}")
        return False
    if rows[0]["month_end"] != "2025-01-31":
        print(f"  first row: {rows[0]}")
        return False
    if rows[0]["icp_count"] != 64571:
        print(f"  Expected comma-formatted ICP count to normalise, got {rows[0]['icp_count']}")
        return False
    if rows[1]["avg_new_installation_capacity_kw"] is not None:
        print(f"  Expected blank numeric value to be None, got {rows[1]['avg_new_installation_capacity_kw']}")
        return False
    return True


results.append(test("DG parser skips metadata and normalises numbers", test_dg_parser_handles_metadata_and_numbers))


def test_dg_latest_command():
    result = run(["dg-latest", "--fuel", "solar_all", "--market-segment", "All", "--json"])
    if result.returncode != 0:
        stderr = result.stderr.lower()
        flaky = ("network error" in stderr or "timeout" in stderr or "http 5" in stderr)
        if flaky:
            print(f"  skipping upstream failure: {result.stderr[:200]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("report_code") != "GUEHMT" or not isinstance(data.get("latest"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected GUEHMT latest[] response")
        return False
    return True


results.append(test("dg-latest returns GUEHMT latest[]", test_dg_latest_command))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
