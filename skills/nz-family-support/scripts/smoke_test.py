#!/usr/bin/env python3
"""Smoke tests for nz-family-support.

All core tests are deterministic and keyless. The optional live URL check treats
network/upstream failures as a skip because this skill is primarily a static
official-source map.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
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
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}\n  error: {e}")
        return False


def test_help() -> bool:
    return run(["--help"]).returncode == 0


def test_sources_json() -> bool:
    r = run(["sources", "--json"])
    if r.returncode != 0:
        print(r.stderr[:300])
        return False
    data = json.loads(r.stdout)
    ids = {item["id"] for item in data.get("sources", [])}
    expected = {
        "ird-support-for-families",
        "ird-working-for-families",
        "ird-wff-msd-handoff",
        "ird-best-start",
        "ird-familyboost",
        "msd-checker",
        "msd-accommodation-supplement-checker",
        "winz-accommodation-supplement",
        "winz-childcare-subsidy",
        "winz-working-for-families",
    }
    return expected.issubset(ids) and "does not calculate" in data.get("disclaimer", "")


def test_search_childcare() -> bool:
    r = run(["search", "childcare fees familyboost subsidy", "--json"])
    if r.returncode != 0:
        print(r.stderr[:300])
        return False
    data = json.loads(r.stdout)
    ids = [item["id"] for item in data.get("results", [])]
    return "ird-familyboost" in ids and "winz-childcare-subsidy" in ids


def test_pathway_housing() -> bool:
    r = run(["pathway", "housing", "--json"])
    if r.returncode != 0:
        print(r.stderr[:300])
        return False
    data = json.loads(r.stdout)
    ids = [item["id"] for item in data.get("sources", [])]
    return ids[:2] == ["msd-accommodation-supplement-checker", "winz-accommodation-supplement"]


def test_invalid_source() -> bool:
    r = run(["show", "not-a-source", "--json"])
    if r.returncode == 0:
        print("expected non-zero return code")
        return False
    data = json.loads(r.stderr)
    return data.get("error") == "invalid_input" and "unknown source id" in data.get("message", "")


def test_verify_first_url() -> bool:
    r = run(["verify", "--limit", "1", "--timeout", "10", "--json"], timeout=20)
    if r.returncode == 0:
        data = json.loads(r.stdout)
        ok = bool(data.get("results")) and data["results"][0].get("ok") is True
        if ok:
            print("[PASS] live official support URL verification")
        return ok
    # Upstream/network failures are acceptable skips for smoke tests.
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"  [SKIP] live verify unavailable: {r.stderr[:160]}")
        return True
    result = (data.get("results") or [{}])[0]
    if result.get("error") or result.get("status", 500) >= 500:
        print(f"  [SKIP] live verify unavailable: {result}")
        return True
    print(r.stdout[:300])
    print(r.stderr[:300])
    return False


results = [
    test("--help exits 0", test_help),
    test("sources JSON includes all official mappings and disclaimer", test_sources_json),
    test("search maps childcare to IRD FamilyBoost and WINZ subsidy", test_search_childcare),
    test("housing pathway includes MSD checker and WINZ page", test_pathway_housing),
    test("invalid source returns clean JSON error", test_invalid_source),
    test("optional live URL verification works or skips transiently", test_verify_first_url),
]

if all(results):
    print("[PASS] fixture official support map, search, pathway and error handling")
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
