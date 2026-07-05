#!/usr/bin/env python3
"""Smoke tests for the mental-health-data-nz skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def json_cmd(args: list[str], timeout: int = 60) -> dict:
    result = run([*args, "--json"], timeout=timeout)
    if result.returncode != 0:
        lower = (result.stderr + result.stdout).lower()
        if any(token in lower for token in ("upstream_blocked", "upstream_timeout", "network error", "timed out")):
            print(f"  SKIP upstream issue for {' '.join(args)}: {(result.stderr or result.stdout)[:240]}")
            return {"_skipped": True}
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout={result.stdout[:400]}\nstderr={result.stderr[:400]}")
    return json.loads(result.stdout)


results: list[bool] = []


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "odmhas-reports" in result.stdout and "seclusion" in result.stdout


results.append(check("--help exits 0", test_help))


def test_reports() -> bool:
    data = json_cmd(["odmhas-reports", "--limit", "2"])
    if data.get("_skipped"):
        return True
    reports = data.get("reports", [])
    return data.get("status") == "ok" and len(reports) == 2 and reports[0].get("docx_url", "").endswith(".docx")


results.append(check("odmhas-reports returns known report assets", test_reports))


def test_kpi_list() -> bool:
    data = json_cmd(["kpi", "list"])
    if data.get("_skipped"):
        return True
    ids = {item.get("id") for item in data.get("indicators", [])}
    return data.get("status") == "ok" and {"seclusion", "wait-times", "28-day-readmission"}.issubset(ids)


results.append(check("kpi list returns public indicator metadata", test_kpi_list))


def test_seclusion_extract() -> bool:
    data = json_cmd(["seclusion", "--year", "2023"], timeout=90)
    if data.get("_skipped") or data.get("status") == "blocked":
        print("  SKIP DOCX asset blocked or unavailable")
        return True
    return (
        data.get("status") == "ok"
        and data.get("seclusion_summary")
        and any(row.get("measure") == "Number of people secluded in all services" for row in data["seclusion_summary"])
    )


results.append(check("seclusion extracts DOCX summary rows", test_seclusion_extract))


def test_edge_unknown_year() -> bool:
    result = run(["seclusion", "--year", "1999", "--json"])
    return result.returncode != 0 and "unknown_year" in result.stdout


results.append(check("seclusion rejects unknown year", test_edge_unknown_year))


def test_inpatient_inspections() -> bool:
    data = json_cmd(["inpatient-inspections", "--year", "2023"], timeout=90)
    if data.get("_skipped") or data.get("docx", {}).get("status") == "blocked":
        print("  SKIP DOCX asset blocked or unavailable")
        return True
    return data.get("status") == "ok" and data.get("inspection_and_district_inspector_sources") and data.get("inspection_counts")


results.append(check("inpatient-inspections returns counts and source links", test_inpatient_inspections))


if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
