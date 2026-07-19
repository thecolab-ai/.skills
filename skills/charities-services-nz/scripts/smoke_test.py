#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("charities_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=60,
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


def test_fixture_row_safety() -> bool:
    cleaned = fixture_cli.clean_row(
        {"RegistrationNumber": "CC123", "__metadata": {"uri": "fixture"}, "Deferred": {"__deferred": {}}}
    )
    public = fixture_cli.strip_officer_private(
        {"FullName": "Fixture Officer", "Email": "fixture@example.invalid", "MailAddress": "Private"}
    )
    return cleaned == {"RegistrationNumber": "CC123"} and public == {"FullName": "Fixture Officer"}


results.append(test("fixture OData row cleanup and officer privacy filter", test_fixture_row_safety))


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


def parse_json_result(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        print(result.stderr[:500])
        raise AssertionError(f"command failed: {' '.join(args)}")
    return json.loads(result.stdout)


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "Charities Services" in result.stdout and "officers" in result.stdout and "returns" in result.stdout


results.append(test("--help exits 0 and lists targeted commands", test_help))


def test_collections() -> bool:
    data = parse_json_result(["collections", "--json"])
    names = {c.get("name") for c in data.get("collections", [])}
    return {"Organisations", "Officers", "Activities", "GrpOrgLatestReturns"}.issubset(names)


results.append(test("collections includes targeted entity sets", test_collections))


def test_fields() -> bool:
    data = parse_json_result(["fields", "Organisations", "--json"])
    names = {f.get("name") for f in data.get("fields", [])}
    return "PurposeToGiveGrantsAndDonations" in names and "CharityRegistrationNumber" in names


results.append(test("Organisations fields include grant-purpose flag", test_fields))


def test_search_and_org() -> bool:
    data = parse_json_result(["search", "Auckland Foundation", "--limit", "1", "--json"])
    rows = data.get("rows", [])
    if not rows or rows[0].get("CharityRegistrationNumber") != "CC44688":
        return False
    org = parse_json_result(["org", "CC44688", "--json"])
    org_rows = org.get("rows", [])
    return bool(org_rows) and org_rows[0].get("OrganisationId") == rows[0].get("OrganisationId")


results.append(test("search and org targeted lookup return Auckland Foundation", test_search_and_org))


def test_officers_privacy() -> bool:
    data = parse_json_result(["officers", "50607", "--limit", "3", "--json"])
    rows = data.get("rows", [])
    if not rows:
        return False
    lowered_keys = [key.lower() for row in rows for key in row.keys()]
    return bool(data.get("privacy_note")) and all("email" not in key and "mailaddress" not in key for key in lowered_keys)


results.append(test("officers returns public rows with email-like fields stripped", test_officers_privacy))


def test_returns() -> bool:
    latest = parse_json_result(["returns", "50607", "--limit", "1", "--json"])
    latest_rows = latest.get("rows", [])
    all_returns = parse_json_result(["returns", "50607", "--all", "--limit", "1", "--json"])
    all_rows = all_returns.get("rows", [])
    return (
        bool(latest_rows)
        and latest.get("entity") == "GrpOrgLatestReturns"
        and latest_rows[0].get("CharityRegistrationNumber") == "CC44688"
        and bool(all_rows)
        and all_returns.get("entity") == "GrpOrgAllReturns"
    )


results.append(test("returns latest and --all annual-return rows", test_returns))


def test_activities() -> bool:
    data = parse_json_result(["activities", "--limit", "10", "--json"])
    rows = data.get("rows", [])
    names = {str(r.get("Name", "")).lower() for r in rows}
    return len(rows) > 0 and any("grant" in name for name in names)


results.append(test("activities taxonomy includes grant activity rows", test_activities))


def test_grant_intent() -> bool:
    data = parse_json_result(["grant-intent", "--limit", "2", "--json"])
    rows = data.get("rows", [])
    return len(rows) > 0 and all(r.get("PurposeToGiveGrantsAndDonations") is True for r in rows)


results.append(test("grant-intent spot query returns true flag rows", test_grant_intent))


def test_grants_paid() -> bool:
    data = parse_json_result(["grants-paid", "--limit", "2", "--json"])
    rows = data.get("rows", [])
    return len(rows) > 0 and all((r.get("GrantsPaidWithinNZ") or 0) > 0 for r in rows)


results.append(test("grants-paid spot query returns positive GrantsPaidWithinNZ", test_grants_paid))


if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)

print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
