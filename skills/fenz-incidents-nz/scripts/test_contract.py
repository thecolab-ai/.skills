#!/usr/bin/env python3
"""Deterministic repository, source-parser and required-query-parameter contracts."""
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

S = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S.parents[1] / "lib"))
from contract_test import run_contract_test  # noqa: E402
import cli  # noqa: E402
from fenz_incidents import parse_incident_lines, parse_incidents  # noqa: E402

AT = "2026-10-08T00:00:00Z"


def test_source_fixtures():
    source = cli.incident_url("Wednesday", "1")
    rows = parse_incident_lines((S / "tests/fixtures/incidents-live-visible.txt").read_text().splitlines(), source, AT)
    assert len(rows) == 2
    assert rows[0]["incident_number"] == "F4558395"
    assert rows[1]["attending_stations_brigades"] == "Henderson, Te Atatu, Auckland City"
    assert rows[1]["call_type"] == "Sprinkler Investigation"
    assert all(row["latest_data"] == "2026-10-07" for row in rows)
    assert all(row["publisher"] == "Fire and Emergency New Zealand" and row["licence"] == "CC BY-NC-ND 4.0" for row in rows)
    assert parse_incidents((S / "tests/fixtures/incidents.html").read_text(), source, AT)[0]["call_type"] == "Structure fire"
    try:
        parse_incidents((S / "tests/fixtures/blocked-live.html").read_text(), source, AT)
    except ValueError:
        pass
    else:
        raise AssertionError("real challenge response must never parse as an empty successful feed")
    print("[PASS] fixture two real FENZ visible records, legacy HTML, licence, date and blocked response")


def test_request_contract():
    document = (S / "tests/fixtures/incidents.html").read_text()
    output = io.StringIO()
    with patch.object(sys, "argv", ["cli.py", "recent", "--day", "Wednesday", "--limit", "2", "--json"]), \
         patch.object(cli.nzfetch, "fetch_text", return_value=document) as fetch, redirect_stdout(output):
        assert cli.main() == 0
    assert [call.args[0] for call in fetch.call_args_list] == [cli.incident_url("Wednesday", region) for region in ("1", "2", "3")]
    assert all(call.kwargs["timeout"] == 10 for call in fetch.call_args_list)
    payload = json.loads(output.getvalue())
    assert len(payload["data"]) == 2 and payload["publisher"] == "Fire and Emergency New Zealand"
    assert all("day=Wednesday&region=" in row["source_url"] for row in payload["data"])
    output = io.StringIO()
    with patch.object(sys, "argv", ["cli.py", "type", "Medical", "--day", "Wednesday", "--report-region", "north", "--json"]), \
         patch.object(cli.nzfetch, "fetch_text", return_value=document) as fetch, redirect_stdout(output):
        assert cli.main() == 0
    fetch.assert_called_once_with(cli.incident_url("Wednesday", "1"), timeout=10, allowed_hosts=cli.HOSTS)
    assert [row["call_type"] for row in json.loads(output.getvalue())["data"]] == ["Medical"]
    print("[PASS] contract required day and numeric region, all three regions, type filter and 10 s requests")


def test_http_400_is_a_failure():
    output = io.StringIO()
    with patch.object(sys, "argv", ["cli.py", "recent", "--day", "Wednesday", "--json"]), \
         patch.object(cli.nzfetch, "fetch_text", side_effect=cli.nzfetch.FetchError("HTTP 400: Bad Request")), redirect_stderr(output):
        assert cli.main() == 6
    assert json.loads(output.getvalue())["error"] == "source_schema_failure"
    print("[PASS] contract HTTP 400 remains a hard source failure, never an outage skip")


if __name__ == "__main__":
    status = run_contract_test(S)
    test_source_fixtures()
    test_request_contract()
    test_http_400_is_a_failure()
    raise SystemExit(status)
