#!/usr/bin/env python3
"""Smoke tests for the energy-hardship-nz skill.

Network-backed checks skip rather than hard-fail when public upstreams are
unavailable. Local validation and deterministic MBIE summary checks still fail
normally.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def is_network_failure(result: subprocess.CompletedProcess) -> bool:
    text = (result.stderr + "\n" + result.stdout).lower()
    markers = [
        "network error",
        "timeout",
        "http 403",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "urlopen error",
    ]
    return any(marker in text for marker in markers)


def report(status: str, name: str, detail: str = "") -> str:
    if name.startswith("--help") or name.startswith("invalid month"):
        kind = "contract"
    elif name.startswith("measures 2024"):
        kind = "fixture"
    else:
        kind = "live"
    prefix = f"[{status}] {kind}" if status == "PASS" else f"[{status}]"
    print(f"{prefix} {name}")
    if detail:
        print(f"  {detail}")
    return status


results: list[str] = []


def test_help() -> str:
    result = run(["--help"])
    if result.returncode == 0 and "energy-hardship" in result.stdout.lower():
        return report("PASS", "--help exits 0")
    return report("FAIL", "--help exits 0", result.stderr[:240] or result.stdout[:240])


results.append(test_help())


def test_measures_2024() -> str:
    result = run(["measures", "--year-ended", "2024", "--json"])
    if result.returncode != 0:
        return report("FAIL", "measures 2024 returns JSON", result.stderr[:240])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return report("FAIL", "measures 2024 returns JSON", str(e))
    measures = data.get("measures")
    if data.get("status") == "ok" and isinstance(measures, list) and len(measures) == 5:
        if all(isinstance(item.get("percent"), (int, float)) for item in measures):
            return report("PASS", "measures 2024 returns five numeric measures")
    return report("FAIL", "measures 2024 returns five numeric measures", result.stdout[:240])


results.append(test_measures_2024())


def test_burden_2023() -> str:
    result = run(["burden", "--breakdown", "income-quintile", "--year", "2023", "--json"])
    if result.returncode != 0:
        if is_network_failure(result):
            return report("SKIP", "burden 2023 live HES path", result.stderr[:240])
        return report("FAIL", "burden 2023 live HES path", result.stderr[:240])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return report("FAIL", "burden 2023 live HES path", str(e))
    records = data.get("records")
    if data.get("status") == "partial" and isinstance(records, list) and records:
        if any(item.get("hec_code") == "04.5.01" for item in records):
            return report("PASS", "burden 2023 returns electricity expenditure")
    return report("FAIL", "burden 2023 returns electricity expenditure", result.stdout[:240])


results.append(test_burden_2023())


def test_disconnections_metadata() -> str:
    result = run(["disconnections", "--from", "2021-10", "--to", "2021-12", "--json"])
    if result.returncode != 0:
        if is_network_failure(result):
            return report("SKIP", "disconnections returns metadata", result.stderr[:240])
        return report("FAIL", "disconnections returns metadata", result.stderr[:240])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return report("FAIL", "disconnections returns metadata", str(e))
    if data.get("status") == "metadata_only" and data.get("source", {}).get("page_url"):
        return report("PASS", "disconnections returns metadata")
    return report("FAIL", "disconnections returns metadata", result.stdout[:240])


results.append(test_disconnections_metadata())


def test_invalid_month_fails() -> str:
    result = run(["disconnections", "--from", "2021-13", "--to", "2021-12", "--json"])
    if result.returncode != 0 and "month must be" in result.stderr:
        return report("PASS", "invalid month exits non-zero")
    return report("FAIL", "invalid month exits non-zero", result.stderr[:240] or result.stdout[:240])


results.append(test_invalid_month_fails())

failures = results.count("FAIL")
skips = results.count("SKIP")
if failures:
    print(f"{failures} test(s) failed; {skips} skipped.")
    sys.exit(1)

print(f"All non-skipped tests passed; {skips} skipped.")
sys.exit(0)
