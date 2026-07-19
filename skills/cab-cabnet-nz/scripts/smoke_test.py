#!/usr/bin/env python3
"""Smoke tests for cab-cabnet-nz.

Network-dependent checks treat CAB/data.govt.nz outages as skips. A genuine
CABNET enquiry export is not publicly reachable; that blocked state is an
expected behaviour this smoke test verifies.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 80) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def parse_json(proc: subprocess.CompletedProcess[str]) -> dict:
    text = (proc.stdout or proc.stderr).strip()
    return json.loads(text or "{}")


def is_upstream_skip(proc: subprocess.CompletedProcess[str]) -> bool:
    if proc.returncode != 2:
        return False
    try:
        data = parse_json(proc)
    except json.JSONDecodeError:
        return False
    return data.get("error") == "upstream_unavailable"


def test(name: str, fn) -> bool:
    try:
        result = fn()
    except Exception as exc:
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False
    if result == "skip":
        print(f"[SKIP] {name}")
        return True
    print(f"[{'PASS' if result else 'FAIL'}] {name}")
    return bool(result)


def test_help() -> bool:
    proc = run(["--help"], timeout=20)
    return proc.returncode == 0 and "enquiries" in proc.stdout and "sources" in proc.stdout


def test_categories() -> bool | str:
    proc = run(["categories", "--query", "tenancy", "--json"])
    if is_upstream_skip(proc):
        return "skip"
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
        return False
    data = parse_json(proc)
    categories = data.get("categories", [])
    return (
        data.get("kind") == "cab-category-taxonomy"
        and data.get("source") == "cab-public-website-categories"
        and isinstance(categories, list)
        and any("tenancy" in row.get("path", "").lower() for row in categories)
    )


def test_sources() -> bool | str:
    proc = run(["sources", "--query", "welfare report", "--limit", "3", "--json"])
    if is_upstream_skip(proc):
        return "skip"
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
        return False
    data = parse_json(proc)
    return (
        data.get("kind") == "cab-source-discovery"
        and data.get("cabnet_reporting", {}).get("public_status") == "forbidden"
        and isinstance(data.get("public_search_results"), list)
    )


def test_enquiries_blocked() -> bool:
    proc = run(["enquiries", "--year", "2025", "--category", "benefits", "--json"])
    if proc.returncode != 2:
        print(proc.stdout)
        print(proc.stderr)
        return False
    data = parse_json(proc)
    return (
        data.get("kind") == "cabnet-enquiries"
        and data.get("error") == "structured_export_unavailable"
        and data.get("status") == "blocked"
    )


def test_invalid_year() -> bool:
    proc = run(["enquiries", "--year", "20x5", "--json"], timeout=20)
    return proc.returncode != 0 and "year" in (proc.stderr or proc.stdout).lower()


def main() -> int:
    checks = [
        ("contract --help includes command names", test_help),
        ("categories returns filtered public taxonomy", test_categories),
        ("sources discovers public CAB material and blocked CABNET reporting", test_sources),
        ("contract enquiries returns explicit structured-export blocked state", test_enquiries_blocked),
        ("contract invalid year is rejected", test_invalid_year),
    ]
    results = [test(name, fn) for name, fn in checks]
    if all(results):
        print("All smoke tests passed")
        return 0
    print(f"{results.count(False)} smoke test(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
