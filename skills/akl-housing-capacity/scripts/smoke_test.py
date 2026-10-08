#!/usr/bin/env python3
"""Synthetic parsers plus bounded, outage-aware public download probes."""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_contract import fixture_checks

CLI = Path(__file__).with_name("cli.py")


def probe(arguments):
    try:
        result = subprocess.run([sys.executable, str(CLI), *arguments, "--json"],
                                capture_output=True, text=True, timeout=55)
    except subprocess.TimeoutExpired:
        print(f"[SKIP] network error: {' '.join(arguments)} exceeded the bounded 55-second probe")
        return True
    payload = json.loads(result.stdout)
    if result.returncode in (4, 5):
        print(f"[SKIP] network error: {' '.join(arguments)}: {payload['error']['message']}")
        return True
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["meta"]["source_url"].startswith("https://")
    assert payload["meta"]["retrieved_at"].endswith("Z")
    rows = payload["results"]
    assert rows, "Source returned no records for the meaningful live probe"
    if arguments[0] == "housing-update":
        assert payload["meta"]["latest_data"]
        if "hud" in arguments:
            assert all(r["series"] == "Delivery" and r["area"] == "Auckland" for r in rows)
            assert payload["meta"]["licence"].startswith("CC BY")
        else:
            assert any(r["area"] == "Henderson - Massey" for r in rows)
            assert all(r["measures"]["all_dwellings"] is not None for r in rows)
    elif "business" in arguments:
        assert all(r["record_type"] == "archive_inventory" and r["files"] > 0 for r in rows)
    elif "typology" in arguments:
        assert {r["selection"] for r in rows} == {"Max_Profit", "MinDUPrice"}
    else:
        assert all(r["plan_enabled_capacity"] >= r["feasible_capacity"] >= 0 for r in rows)
    print(f"[PASS] live {' '.join(arguments)}: {len(rows)} records; latest_data={payload['meta'].get('latest_data')}")
    return True


def main():
    try:
        fixture_checks(report=True)
    except Exception as exc:
        print(f"[FAIL] fixture parser: {exc}")
        return 1
    commands = [("housing-update", "--area", "Henderson-Massey"),
                ("housing-update", "--source", "hud"),
                ("capacity", "--area", "Whau"),
                ("capacity", "--detail", "typology", "--area", "Whau"),
                ("capacity", "--dataset", "business")]
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(probe, commands))
        return 0 if all(results) else 1
    except Exception as exc:
        print(f"[FAIL] live source/schema: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
