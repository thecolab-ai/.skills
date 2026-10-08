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
        payload = json.loads(output.getvalue())
        result = payload["results"][0]
        assert result["status"] == status
        assert [{"id": item["id"], "address": item["address"]} for item in result["matches"]] == items
        assert all("match_score" in item for item in result["matches"])
        assert {"source_url", "publisher", "retrieved_at"} <= payload["meta"].keys()
        assert "licence" not in payload["meta"]
        schedule.assert_not_called()
    print("[PASS] contract unresolved addresses return candidates without fetching any schedule")
    item = {"id": "synthetic-0", "address": "12 Tawa Road, Onehunga"}
    output = io.StringIO()
    with patch.object(cli, "lookup_properties", return_value=[item]), patch.object(cli, "get_schedule", return_value={"address": item["address"]}) as schedule, redirect_stdout(output):
        assert cli.main(["12 Tawa Road Onehunga", "--json"]) == 0
    schedule.assert_called_once_with(item["id"])
    matched = json.loads(output.getvalue())["results"][0]["matched_property"]
    assert matched["id"] == item["id"] and matched["address"] == item["address"]
    assert matched["match_score"] == 100 and matched["exact_match"]
    print("[PASS] contract exact singleton selects schedule and legacy invocation works")


def test_bad_request():
    output = io.StringIO()
    with patch.object(cli, "lookup_properties", side_effect=cli.nzfetch.FetchError("HTTP 400: Bad Request")), redirect_stdout(output):
        assert cli.main(["schedule", "1 Dominion Road Mount Eden", "--json"]) == 6
    assert json.loads(output.getvalue())["error"]["type"] == "schema_failure"
    print("[PASS] contract HTTP 400 fails instead of being skipped as a network outage")


def test_limits_and_errors():
    for argv in (["lookup", "12 Tawa Road", "--limit", "21"],
                 ["lookup", "12 Tawa Road", "--limit", "0"],
                 ["schedule", "--property-id", "abc"], ["schedule"],
                 ["lookup", "12 Tawa Road", "--limit", "x"]):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(cli, "lookup_properties") as lookup:
            assert cli.main([*argv, "--json"]) == 2
        payload = json.loads(out.getvalue())
        assert err.getvalue() == "" and payload["results"] == []
        assert payload["error"]["type"] == "invalid_input" and payload["error"]["code"] == 2
        if argv[-1] in {"21", "0"}:
            assert payload["error"]["message"] == "--limit must be between 1 and 20"
        lookup.assert_not_called()
    for exc, code, kind in [(cli.nzfetch.RateLimited("rate limited", retry_after="60"), 4, "blocked"),
                            (cli.nzfetch.Blocked("blocked"), 4, "blocked"),
                            (cli.nzfetch.FetchError("timeout"), 5, "upstream_unavailable"),
                            (ValueError("bad schema"), 6, "schema_failure")]:
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "lookup_properties", side_effect=exc), redirect_stdout(out), redirect_stderr(err):
            assert cli.main(["lookup", "12 Tawa Road", "--json"]) == code
        payload = json.loads(out.getvalue())
        assert not err.getvalue() and payload["results"] == []
        assert payload["error"]["type"] == kind and payload["error"]["code"] == code
        assert "licence" not in payload["meta"]
        if isinstance(exc, cli.nzfetch.RateLimited):
            assert payload["error"]["retry_after"] == "60"
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        assert cli.main(["lookup", "12 Tawa Road", "--limit", "21"]) == 2
    assert not out.getvalue() and "between 1 and 20" in err.getvalue()
    print("[PASS] contract Council cap rejects limit 21 before fetching; JSON and human errors use correct streams")


def test_normalised_upstream_query():
    with patch.object(cli, "current_public_token", return_value="synthetic-public-token"), \
         patch.object(cli, "fetch_json", return_value={"items": []}) as fetch:
        assert cli.lookup_properties("12 Tawa Rd, Onehunga, Auckland 1061", 20) == []
    url = fetch.call_args.args[0]
    assert cli.urllib.parse.parse_qs(cli.urllib.parse.urlparse(url).query) == {
        "query": ["12 tawa road onehunga"], "pageSize": ["20"]}
    assert cli.normalised_query("2/12A Mt Eden Rd, Mt Eden, Auckland 1024") == "2/12a mount eden road mount eden"
    print("[PASS] contract upstream query normalises punctuation, postcode, units, suffix and street names")


def test_scores_and_pick():
    fixture = json.loads((S / "tests/fixtures/property-search.json").read_text())
    items = fixture["items"]
    query = "42 Example Road, Mount Eden"
    ranked = cli.rank_properties(items, query)
    with patch.object(cli, "current_public_token", return_value="synthetic-public-token"), \
         patch.object(cli, "fetch_json", return_value=fixture):
        fetched = cli.lookup_properties(query)
    assert [{"id": item["id"], "address": item["address"]} for item in fetched] == items
    assert all(item["publisher"] == "Auckland Council" and item["retrieved_at"].endswith("Z")
               and item["source_url"] == cli.property_url(query, 10) for item in fetched)
    assert [item["match_score"] for item in ranked] == [100, 90, 85, 75, 60]
    assert [item["candidate_number"] for item in ranked] == list(range(1, 6))
    assert [item["exact_match"] for item in ranked] == [True, False, False, False, False]
    assert ranked[-1]["match_components"] == {
        "number": True, "suffix": False, "street": True, "type": False, "suburb": False, "unit": True}
    assert cli.rank_properties(list(reversed(items)), query) == ranked
    assert len(cli.rank_properties([*items, items[0]], query)) == len(items)
    assert cli.rank_properties(items, "incomplete query")[0]["match_score"] == 0
    for pick, limit in ((1, 10), (2, 10), (1, 5)):
        out = io.StringIO()
        with patch.object(cli, "lookup_properties", return_value=items), \
             patch.object(cli, "get_schedule", return_value={"address": "Synthetic schedule"}) as schedule, redirect_stdout(out):
            assert cli.main([query, "--pick", str(pick), "--limit", str(limit), "--json"]) == 0
        chosen = json.loads(out.getvalue())["results"][0]
        assert chosen["status"] == "picked"
        assert chosen["matched_property"] == ranked[pick - 1]
        schedule.assert_called_once_with(ranked[pick - 1]["id"])
    out = io.StringIO()
    with patch.object(cli, "lookup_properties", return_value=items), redirect_stdout(out):
        assert cli.main(["lookup", query, "--json"]) == 0
    assert json.loads(out.getvalue())["results"][0]["matches"] == ranked
    for argv in ([query, "--pick", "0"], [query, "--pick", "21"], [query, "--pick", "bad"],
                 ["lookup", query, "--pick", "1"], [query, "--list", "--pick", "1"],
                 ["--property-id", "10000000001", "--pick", "1"]):
        out = io.StringIO()
        with patch.object(cli, "lookup_properties") as lookup, redirect_stdout(out):
            assert cli.main([*argv, "--json"]) == 2
        assert json.loads(out.getvalue())["error"]["type"] == "invalid_input"
        lookup.assert_not_called()
    for items_returned in ([], items[:1]):
        out = io.StringIO()
        with patch.object(cli, "lookup_properties", return_value=items_returned), \
             patch.object(cli, "get_schedule") as schedule, redirect_stdout(out):
            assert cli.main([query, "--pick", "2", "--json"]) == 2
        assert json.loads(out.getvalue())["results"] == []
        schedule.assert_not_called()
    out = io.StringIO()
    with patch.object(cli, "lookup_properties", return_value=[items[1]]), \
         patch.object(cli, "get_schedule") as schedule, redirect_stdout(out):
        assert cli.main(["42 Example Road", "--json"]) == 0
    candidate = json.loads(out.getvalue())["results"][0]
    assert candidate["status"] == "ambiguous" and candidate["matches"][0]["match_score"] == 85
    assert not candidate["matches"][0]["exact_match"]
    schedule.assert_not_called()
    out = io.StringIO()
    with patch.object(cli, "lookup_properties", return_value=items), redirect_stdout(out):
        assert cli.main(["lookup", query]) == 0
    assert "1\t100/100\t10000000001\t42 Example Road, Mount Eden" in out.getvalue()
    print("[PASS] fixture scored source items, stable numbering, strict suburb, explicit picks and invalid selections")


if __name__ == "__main__":
    status = run_contract_test(S)
    test_matching()
    test_cli()
    test_bad_request()
    test_limits_and_errors()
    test_normalised_upstream_query()
    test_scores_and_pick()
    raise SystemExit(status)
