#!/usr/bin/env python3
"""Smoke tests for ird-wff-rates-nz."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=30)


def assert_json(cp: subprocess.CompletedProcess[str]) -> dict:
    assert cp.returncode == 0, cp.stderr or cp.stdout
    return json.loads(cp.stdout)


def test_help() -> None:
    cp = run("--help")
    assert cp.returncode == 0
    assert "FamilyBoost" in cp.stdout or "WFF" in cp.stdout


def test_rates_json() -> None:
    data = assert_json(run("rates", "--year", "2027", "--json"))
    assert data["ok"] is True
    assert data["data"]["tax_year"] == 2027
    assert data["data"]["thresholds"]["wff_family_income_abatement_threshold"]["amount"] == 44900
    ftc = data["data"]["credits"]["family-tax-credit"]
    assert ftc["amounts"][0]["annual"] == 7921
    assert ftc["amounts"][1]["weekly"] == 124
    assert any("ird.govt.nz" in s for s in data["sources"])


def test_credit_alias_json() -> None:
    data = assert_json(run("credit", "get", "best-start", "--year", "2027", "--json"))
    assert data["data"]["slug"] == "best-start"
    assert data["data"]["amounts"][0]["weekly"] == 77
    assert data["data"]["thresholds"]["best_start_abatement_rate"]["rate"] == 0.21


def test_familyboost_json() -> None:
    data = assert_json(run("familyboost", "--json"))
    current = data["data"]["periods"][-1]
    assert current["reimbursement_rate"] == 0.40
    assert current["maximum_payment_quarterly"] == 1560
    assert current["household_income_cap_quarterly"] == 57286
    assert "licensed early childhood education" in " ".join(data["data"]["eligibility_summary"])


def test_unknown_year_clean_error() -> None:
    cp = run("thresholds", "--year", "1999", "--json")
    assert cp.returncode == 2
    err = json.loads(cp.stderr)
    assert err["ok"] is False
    assert err["error"] == "not_found"


def main() -> int:
    tests = [test_help, test_rates_json, test_credit_alias_json, test_familyboost_json, test_unknown_year_clean_error]
    for test in tests:
        try:
            test()
            kind = "fixture" if test is test_rates_json else "contract"
            print(f"[PASS] {kind} {test.__name__}")
        except Exception as exc:
            print(f"not ok - {test.__name__}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
