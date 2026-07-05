#!/usr/bin/env python3
"""Smoke tests for nzta-crash-data-nz.

The live data path is public but network-dependent. Upstream/network failures
are reported as skips; local CLI contract failures remain hard failures.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

UPSTREAM_MARKERS = (
    "network error",
    "timed out",
    "timeout",
    "HTTP 429",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
    "upstream",
)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def is_upstream_failure(result: subprocess.CompletedProcess[str]) -> bool:
    text = f"{result.stderr}\n{result.stdout}"
    return any(marker.lower() in text.lower() for marker in UPSTREAM_MARKERS)


def report(name: str, status: str, detail: str = "") -> bool | None:
    print(f"[{status}] {name}")
    if detail:
        print(f"  {detail}")
    if status == "PASS":
        return True
    if status == "SKIP":
        return None
    return False


def test_help() -> bool | None:
    result = run(["--help"])
    if result.returncode == 0 and "road-toll" in result.stdout:
        return report("--help lists commands", "PASS")
    return report("--help lists commands", "FAIL", result.stderr[:300] or result.stdout[:300])


def test_datasets_json() -> bool | None:
    result = run(["datasets", "--json"])
    if result.returncode != 0:
        if is_upstream_failure(result):
            return report("datasets returns source status", "SKIP", result.stderr[:300])
        return report("datasets returns source status", "FAIL", result.stderr[:300])
    data = json.loads(result.stdout)
    sources = data.get("sources", [])
    if data.get("kind") == "datasets" and len(sources) >= 2:
        return report("datasets returns source status", "PASS")
    return report("datasets returns source status", "FAIL", "expected kind=datasets and at least two sources")


def test_road_toll_json() -> bool | None:
    result = run(["road-toll", "--year", "2025", "--json"])
    if result.returncode != 0:
        if is_upstream_failure(result):
            return report("road-toll returns fatality summary", "SKIP", result.stderr[:300])
        return report("road-toll returns fatality summary", "FAIL", result.stderr[:300])
    data = json.loads(result.stdout)
    if data.get("kind") == "road-toll" and isinstance(data.get("fatalities"), int):
        return report("road-toll returns fatality summary", "PASS")
    return report("road-toll returns fatality summary", "FAIL", "expected integer fatalities")


def test_invalid_date_edge_case() -> bool | None:
    result = run(["crashes", "--from", "2025-99-99", "--json"])
    combined = f"{result.stderr}\n{result.stdout}"
    if result.returncode != 0 and "traceback" not in combined.lower() and "invalid date" in combined.lower():
        return report("invalid date fails cleanly", "PASS")
    return report("invalid date fails cleanly", "FAIL", combined[:300])


tests = [
    test_help,
    test_datasets_json,
    test_road_toll_json,
    test_invalid_date_edge_case,
]

results = [test() for test in tests]
failures = results.count(False)
passes = results.count(True)
skips = results.count(None)

if failures:
    print(f"{failures} test(s) failed, {passes} passed, {skips} skipped.")
    sys.exit(1)

print(f"All non-skipped tests passed ({passes} passed, {skips} skipped).")
