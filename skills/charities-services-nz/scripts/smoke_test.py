#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return bool(ok)
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results: list[bool] = []


def upstream_available() -> bool:
    try:
        req = urllib.request.Request(
            "https://www.odata.charities.govt.nz/",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/xml"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[SKIP] Charities Services OData unavailable: {e}")
        return False


if not upstream_available():
    sys.exit(0)


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "Charities Services" in result.stdout


results.append(test("--help exits 0", test_help))


def test_collections() -> bool:
    result = run(["collections", "--json"])
    if result.returncode != 0:
        print(result.stderr[:300])
        return False
    data = json.loads(result.stdout)
    names = {c.get("name") for c in data.get("collections", [])}
    return "Organisations" in names and "GrpOrgLatestReturns" in names


results.append(test("collections includes Organisations and GrpOrgLatestReturns", test_collections))


def test_fields() -> bool:
    result = run(["fields", "Organisations", "--json"])
    if result.returncode != 0:
        print(result.stderr[:300])
        return False
    data = json.loads(result.stdout)
    names = {f.get("name") for f in data.get("fields", [])}
    return "PurposeToGiveGrantsAndDonations" in names and "CharityRegistrationNumber" in names


results.append(test("Organisations fields include grant-purpose flag", test_fields))


def test_grant_intent() -> bool:
    result = run(["grant-intent", "--limit", "2", "--json"])
    if result.returncode != 0:
        print(result.stderr[:300])
        return False
    data = json.loads(result.stdout)
    rows = data.get("rows", [])
    return len(rows) > 0 and all(r.get("PurposeToGiveGrantsAndDonations") is True for r in rows)


results.append(test("grant-intent spot query returns true flag rows", test_grant_intent))


def test_grants_paid() -> bool:
    result = run(["grants-paid", "--limit", "2", "--json"])
    if result.returncode != 0:
        print(result.stderr[:300])
        return False
    data = json.loads(result.stdout)
    rows = data.get("rows", [])
    return len(rows) > 0 and all((r.get("GrantsPaidWithinNZ") or 0) > 0 for r in rows)


results.append(test("grants-paid spot query returns positive GrantsPaidWithinNZ", test_grants_paid))

if all(results):
    print("All tests passed.")
    sys.exit(0)

print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
