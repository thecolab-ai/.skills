#!/usr/bin/env python3
"""Deterministic repo contract plus strict address selection and CLI regressions."""
import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

S = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S.parents[1] / "lib"))
from contract_test import run_contract_test  # noqa: E402

spec = importlib.util.spec_from_file_location("bin_cli", S / "scripts/cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_matching():
    fixture = json.loads((S / "tests/fixtures/address-cases.json").read_text())
    for case in fixture["cases"]:
        items = [{"id": f"synthetic-{i}", "address": address} for i, address in enumerate(case["addresses"])]
        chosen = cli.choose_property(items, case["query"])
        expected = None if case["selected"] is None else items[case["selected"]]
        assert chosen == expected, case
    print(f"[PASS] fixture {len(fixture['cases'])} strict address cases including Dominion Road regression")


def test_cli():
    for addresses, status, limit in [
        (["1A Dominion Street, Takapuna"], "no_exact_match", 10),
        (["1 Dominion Road, Mount Eden", "1 Dominion Road, Takapuna"], "ambiguous", 10),
        (["1 Dominion Road, Mount Eden"], "search_limit", 1),
    ]:
        query = "1 Dominion Road, Mount Eden" if status != "ambiguous" else "1 Dominion Road"
        items = [{"id": f"synthetic-{i}", "address": address} for i, address in enumerate(addresses)]
        output = io.StringIO()
        with patch.object(cli, "lookup_properties", return_value=items), patch.object(cli, "get_schedule") as schedule, redirect_stdout(output):
            assert cli.main(["schedule", query, "--json", "--limit", str(limit)]) == 0
        result = json.loads(output.getvalue())
        assert result["status"] == status
        assert result["matches"] == items
        assert {"source_url", "publisher", "licence", "retrieved_at"} <= result.keys()
        schedule.assert_not_called()
    print("[PASS] contract unresolved addresses return candidates without fetching any schedule")
    item = {"id": "synthetic-0", "address": "12 Tawa Road, Onehunga"}
    output = io.StringIO()
    with patch.object(cli, "lookup_properties", return_value=[item]), patch.object(cli, "get_schedule", return_value={"address": item["address"]}) as schedule, redirect_stdout(output):
        assert cli.main(["12 Tawa Road Onehunga", "--json"]) == 0
    schedule.assert_called_once_with(item["id"])
    assert json.loads(output.getvalue())["matched_property"] == item
    print("[PASS] contract exact singleton selects schedule and legacy invocation works")


def test_bad_request():
    output = io.StringIO()
    with patch.object(cli, "lookup_properties", side_effect=cli.nzfetch.FetchError("HTTP 400: Bad Request")), redirect_stderr(output):
        assert cli.main(["schedule", "1 Dominion Road Mount Eden", "--json"]) == 6
    assert json.loads(output.getvalue())["error"] == "source_schema_failure"
    print("[PASS] contract HTTP 400 fails instead of being skipped as a network outage")


if __name__ == "__main__":
    status = run_contract_test(S)
    test_matching()
    test_cli()
    test_bad_request()
    raise SystemExit(status)
