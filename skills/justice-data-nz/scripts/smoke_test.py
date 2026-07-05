#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
MOJ_TABLES_URL = "https://www.justice.govt.nz/justice-sector-policy/research-data/justice-statistics/data-tables/"


def run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=timeout,
    )


def upstream_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "upstream",
            "network error",
            "timeout",
            "http 403",
            "http 429",
            "rate-limiting",
        )
    )


def check(name: str, fn) -> bool:
    try:
        ok = bool(fn())
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def upstream_available() -> bool:
    try:
        req = urllib.request.Request(MOJ_TABLES_URL, headers={"User-Agent": "justice-data-nz-smoke-test"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] Ministry of Justice data-tables page unavailable: {exc}")
        return False


if not upstream_available():
    raise SystemExit(0)

results: list[bool] = []


def parse_json(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        if upstream_error(result.stderr):
            print(f"[SKIP] Upstream became unavailable during {' '.join(args)}: {result.stderr.strip()}")
            raise SystemExit(0)
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout: {result.stdout[:300]}\nstderr: {result.stderr[:300]}")
    return json.loads(result.stdout)


results.append(check("--help exits 0", lambda: run(["--help"]).returncode == 0))


def test_tables() -> bool:
    data = parse_json(["tables", "--json"])
    assert data.get("status") == "ok"
    assert data.get("count", 0) >= 4
    assert any("family violence" in table.get("topic", "").lower() for table in data["tables"])
    years = [table.get("period", {}).get("year") for table in data["tables"] if table.get("period")]
    assert any(isinstance(year, int) for year in years)
    return True


results.append(check("tables returns MoJ workbook metadata", test_tables))


tables_payload = parse_json(["tables", "--json"])
latest_year = max(
    table["period"]["year"]
    for table in tables_payload["tables"]
    if isinstance(table.get("period"), dict) and isinstance(table["period"].get("year"), int)
)


def test_convictions() -> bool:
    data = parse_json(["convictions", "--year", str(latest_year), "--offence", "assault", "--json"])
    assert data.get("status") == "ok"
    assert data.get("people_convicted_by_offence")
    assert any(row.get("value", 0) for row in data["people_convicted_by_offence"])
    assert data.get("convicted_charges_by_offence")
    return True


results.append(check("convictions returns assault rows", test_convictions))


def test_sentencing() -> bool:
    data = parse_json(["sentencing", "--year", str(latest_year), "--json"])
    assert data.get("status") == "ok"
    labels = json.dumps(data.get("people_convicted_by_most_serious_sentence", []))
    assert "Imprisonment" in labels
    return True


results.append(check("sentencing returns sentence rows", test_sentencing))


def test_family_violence() -> bool:
    data = parse_json(["family-violence", "--year", str(latest_year), "--json"])
    assert data.get("status") == "ok"
    assert data.get("family_violence_charges_by_outcome")
    assert data.get("people_convicted_by_sentence")
    return True


results.append(check("family-violence returns outcome and sentence rows", test_family_violence))


def test_youth() -> bool:
    data = parse_json(["youth", "--year", str(latest_year), "--json"])
    assert data.get("status") == "ok"
    assert data.get("charges_by_outcome")
    assert data.get("children_and_young_people_by_offence")
    return True


results.append(check("youth returns charge and people rows", test_youth))


def test_bad_year() -> bool:
    result = run(["convictions", "--year", "1900", "--json"])
    assert result.returncode != 0
    assert "year 1900" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()
    return True


results.append(check("unavailable year fails clearly", test_bad_year))

if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
