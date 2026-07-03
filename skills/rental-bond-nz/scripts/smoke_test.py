#!/usr/bin/env python3
"""Smoke tests for rental-bond-nz skill."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return bool(ok)
    except Exception as exc:
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def upstream_unavailable(process: subprocess.CompletedProcess) -> bool:
    if process.returncode != 2:
        return False
    text = process.stdout.strip() or process.stderr.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    return payload.get("error") == "upstream_unavailable"


def is_json(process: subprocess.CompletedProcess) -> dict:
    text = process.stdout.strip()
    return json.loads(text) if text else {}


def test_help() -> bool:
    result = run(["--help"], timeout=20)
    return result.returncode == 0 and "market-rent" in result.stdout


def test_datasets() -> bool:
    result = run(["datasets", "--limit", "5", "--json"], timeout=120)
    if upstream_unavailable(result):
        print("  [SKIP] upstream unavailable")
        return True
    if result.returncode != 0:
        print(result.stderr)
        return False
    data = is_json(result)
    return data.get("kind") == "tenancy_bond_datasets" and isinstance(data.get("tenancy_asset_datasets"), list)


def test_areas() -> bool:
    result = run(["areas", "--query", "Auckland", "--limit", "5", "--json"], timeout=120)
    if upstream_unavailable(result):
        print("  [SKIP] upstream unavailable")
        return True
    if result.returncode != 0:
        print(result.stderr)
        return False
    data = is_json(result)
    return data.get("kind") == "tenancy_market_rent_areas" and isinstance(data.get("areas"), list)


def test_bonds() -> bool:
    result = run(["bonds", "--from", "2026-01", "--to", "2026-06", "--json"], timeout=120)
    if upstream_unavailable(result):
        print("  [SKIP] upstream unavailable")
        return True
    if result.returncode != 0:
        print(result.stderr)
        return False
    data = is_json(result)
    return data.get("kind") == "tenancy_bond_series" and isinstance(data.get("records"), list)


def test_market_rent() -> bool:
    result = run(["market-rent", "--area", "Auckland - Avondale", "--period", "2025-10", "--json"], timeout=120)
    if upstream_unavailable(result):
        print("  [SKIP] upstream unavailable")
        return True
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        return False
    data = is_json(result)
    return data.get("kind") == "tenancy_market_rent" and isinstance(data.get("records"), list)


def main() -> int:
    tests = [
        ("--help includes market-rent", test_help),
        ("datasets returns tenancy/CKAN data", test_datasets),
        ("areas returns suggestion records", test_areas),
        ("bonds returns monthly rows", test_bonds),
        ("market-rent returns records or explicit skip", test_market_rent),
    ]
    results = [test(name, fn) for name, fn in tests]

    if all(results):
        print("All smoke tests passed")
        return 0

    failed = results.count(False)
    print(f"{failed} smoke test(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
