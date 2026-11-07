#!/usr/bin/env python3
"""Deterministic repository contract test and store-finder fixture checks for this skill."""
import importlib.util
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402

spec = importlib.util.spec_from_file_location("the_warehouse_nz_cli_contract", Path(__file__).with_name("cli.py"))
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)


def fixture_checks() -> None:
    # No region must not fall back to caller geo-IP (a non-NZ host got zero stores).
    national = cli.stores_params(None)
    assert "region" not in national and national["radius"] >= 1600
    assert -48 < national["lat"] < -34 and 166 < national["long"] < 179
    assert cli.stores_params("NZ-AUK") == {"region": "NZ-AUK"}
    url = cli.url_with_params(cli.STORES_PATH, national)
    assert "lat=-41.0" in url and "long=174.0" in url and "radius=2000" in url
    print("[PASS] stores without region send an explicit NZ-wide search circle")

    payload = json.loads((SKILL / "tests" / "fixtures" / "stores-findstores.json").read_text(encoding="utf-8"))
    stores = cli.parse_stores_payload(payload)
    assert [store["id"] for store in stores] == ["9001", "9002"]
    assert stores[0]["region"] == "Auckland" and stores[0]["hours_today"] == "8am - 9pm"
    assert stores[1]["address"] == "2 Fixture Street, Dunedin"
    print("[PASS] fixture Stores-FindStores payload parses")

    for malformed in ({}, {"stores": []}, {"stores": {"searchKey": {}}}):
        try:
            cli.parse_stores_payload(malformed)
        except SystemExit:
            continue
        raise AssertionError(f"malformed store payload accepted: {malformed!r}")
    print("[PASS] malformed store payloads fail closed")


if __name__ == "__main__":
    fixture_checks()
    raise SystemExit(run_contract_test(SKILL))
