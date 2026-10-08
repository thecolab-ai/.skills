#!/usr/bin/env python3
"""Deterministic regressions and one bounded, outage-aware live schedule probe."""
import json
import subprocess
import sys
from pathlib import Path

from test_contract import cli, test_bad_request, test_cli, test_matching, test_limits_and_errors, test_normalised_upstream_query

S = Path(__file__).resolve().parents[1]
test_matching()
test_cli()
test_bad_request()
test_limits_and_errors()
test_normalised_upstream_query()
lines = ["Household collection", "Rubbish:", "Friday, 1 August", "Rubbish", "Collection day:",
         "Every week", ".", "Put bins out before 7am", "Where you can put your rubbish, food scraps and recycling for collection"]
parsed = cli.parse_section(lines, "Household collection")
assert parsed["next_dates"]["rubbish"] == "Friday, 1 August"
assert parsed["frequency"]["rubbish"] == "Every week"
print("[PASS] fixture household collection section")
result = subprocess.run([sys.executable, str(S / "scripts/cli.py"), "schedule", "12 Tawa Road Onehunga", "--json"],
                        capture_output=True, text=True, timeout=35)
if result.returncode in {4, 5}:
    print(f"[SKIP] network error Auckland Council unavailable: {(result.stdout or result.stderr).strip()}")
elif result.returncode:
    print(f"[FAIL] live schedule: {(result.stdout or result.stderr).strip()}")
    raise SystemExit(1)
else:
    envelope = json.loads(result.stdout)
    payload = envelope["results"][0]
    assert payload["matched_property"]["address"]
    assert payload["household"] and payload["property_id"]
    assert cli.parse_address(payload["matched_property"]["address"]) == cli.parse_address("12 Tawa Road Onehunga")
    assert all(envelope["meta"].get(key) for key in ("source_url", "publisher", "retrieved_at"))
    print(f"[PASS] live exact Onehunga schedule: {payload['address']} ({payload['property_id']})")
