#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=str(SKILL_DIR), capture_output=True, text=True, timeout=timeout)


def check(name: str, fn) -> bool:
    try:
        ok = bool(fn())
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def parse_json(args: list[str], timeout: int = 60) -> dict:
    result = run(args, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout: {result.stdout[:400]}\nstderr: {result.stderr[:400]}")
    return json.loads(result.stdout)


def parse_result(args: list[str], timeout: int = 60) -> tuple[subprocess.CompletedProcess, dict]:
    result = run(args, timeout=timeout)
    text = result.stdout or result.stderr or "{}"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}
    return result, payload


def is_upstream_skip(result: subprocess.CompletedProcess, payload: dict) -> bool:
    if result.returncode == 0:
        return False
    return payload.get("code") in {"blocked", "upstream_http", "upstream_schema"} or "network" in (result.stderr + result.stdout).lower()


results: list[bool] = []
results.append(check("--help exits 0", lambda: run(["--help"]).returncode == 0))


def test_csv_row_fixture() -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("healthcert_rest_homes_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalise_row(
        {
            "Premises Name": "Synthetic Rest Home",
            "Service Types": "Rest home care, Hospital care",
            "Total Beds": "24",
            "Certification Period (Months)": "36",
            "Legal Name": "Synthetic Provider Limited",
        }
    )
    assert record["slug"] == "synthetic-rest-home"
    assert record["service_types"] == ["Rest home care", "Hospital care"]
    assert record["total_beds"] == 24
    assert record["certification_period_months"] == 36
    print("[PASS] fixture certified-provider CSV row normalisation")
    return True


results.append(check("fixture CSV parser", test_csv_row_fixture))


def test_list() -> bool:
    result, data = parse_result(["list", "--limit", "1", "--json"])
    if is_upstream_skip(result, data):
        print("  SKIP upstream CSV unavailable")
        return True
    assert result.returncode == 0
    assert data["status"] == "ok"
    assert data["count"] >= 1
    first = data["facilities"][0]
    assert "premises_name" in first
    assert "legal_name" in first
    assert isinstance(first.get("service_types"), list)
    return True


results.append(check("list returns CSV-backed facilities", test_list))


def test_sample() -> bool:
    result, listing = parse_result(["list", "--limit", "1", "--json"])
    if is_upstream_skip(result, listing):
        print("  SKIP upstream CSV unavailable")
        return True
    provider = listing["facilities"][0]["legal_name"]
    data = parse_json(["sample", "--provider", provider, "--json"])
    assert data["status"] == "ok"
    assert data["kind"] == "provider_sample"
    assert data["facility_count"] >= 1
    assert data["sample"][0]["legal_name"]
    return True


results.append(check("sample returns provider rows", test_sample))


def test_facility_live_or_blocked() -> bool:
    result, listing = parse_result(["list", "--limit", "1", "--json"])
    if is_upstream_skip(result, listing):
        print("  SKIP upstream CSV unavailable")
        return True
    name = listing["facilities"][0]["premises_name"]
    data = parse_json(["facility", name, "--json"], timeout=45)
    assert data["status"] in {"ok", "blocked"}
    assert data["kind"] == "facility"
    assert data.get("csv_fallback", {}).get("premises_name") == name
    if data["status"] == "ok":
        assert data.get("reports") is not None
        assert "corrective_action_note" in data
    else:
        assert data["code"] == "blocked"
    return True


results.append(check("facility returns page data or explicit blocked state", test_facility_live_or_blocked))


def test_reports_live_or_blocked() -> bool:
    result, listing = parse_result(["list", "--limit", "1", "--json"])
    if is_upstream_skip(result, listing):
        print("  SKIP upstream CSV unavailable")
        return True
    slug = listing["facilities"][0]["slug"]
    data = parse_json(["reports", slug, "--json"], timeout=45)
    assert data["status"] in {"ok", "blocked"}
    assert data["kind"] == "reports"
    if data["status"] == "ok":
        assert isinstance(data.get("reports"), list)
    else:
        assert data["code"] == "blocked"
    return True


results.append(check("reports returns links or explicit blocked state", test_reports_live_or_blocked))

if all(results):
    print("[PASS] live smoke assertions completed")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
