#!/usr/bin/env python3
"""Live read-only smoke tests for the nz-local-government-data skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=timeout,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def json_cmd(args: list[str]) -> dict:
    result = run(args + ["--json"])
    if result.returncode != 0:
        # Upstream public sources can be flaky; make network failures visible but non-fatal.
        if any(token in result.stderr.lower() for token in ("timed out", "http 5", "failed fetching", "urlopen error")):
            print(f"  SKIP upstream/network error for {' '.join(args)}: {result.stderr[:240]}")
            return {"_skipped": True}
        raise AssertionError(f"command failed: {result.stderr[:500]}")
    return json.loads(result.stdout)


results: list[bool] = []


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "datasets" in result.stdout and "councils" in result.stdout


results.append(test("--help exits 0", test_help))


def test_datasets_discovery() -> bool:
    data = json_cmd(["datasets", "--limit", "3"])
    if data.get("_skipped"):
        return True
    return data.get("kind") == "datasets" and len(data.get("sources", [])) >= 4 and "stats_nz" in data


results.append(test("datasets discovers official sources", test_datasets_discovery))


def test_performance_preview() -> bool:
    data = json_cmd(["performance-metrics", "--limit", "2"])
    if data.get("_skipped"):
        return True
    records = data.get("records", [])
    return data.get("kind") == "performance-metrics" and data.get("record_count", 0) >= 70 and records and "Council" in records[0]


results.append(test("performance-metrics previews DIA workbook", test_performance_preview))


def test_council_filter() -> bool:
    data = json_cmd(["councils", "--query", "Auckland"])
    if data.get("_skipped"):
        return True
    councils = data.get("councils", [])
    return bool(councils) and any("Auckland" in c.get("name", "") for c in councils)


results.append(test("councils filters Auckland", test_council_filter))


def test_compare_edge_case() -> bool:
    result = run(["compare", "--metric", "not-a-real-metric", "--councils", "Auckland", "--json"])
    return result.returncode != 0 and "unknown metric" in result.stderr


results.append(test("compare rejects unknown metric", test_compare_edge_case))

if all(results):
    print("All tests passed.")
    sys.exit(0)

print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
