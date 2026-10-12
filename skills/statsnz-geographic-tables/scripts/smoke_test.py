#!/usr/bin/env python3
"""Fixture contracts and one bounded live probe for Stats NZ geographic tables."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import cli

CLI = Path(__file__).with_name("cli.py")
PROFILE_MARKER = "fixture-profile-must-not-leak"
LIVE_TABLE = "122777"


def run_cli(args: list[str], *, fixture: str | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop(cli.FIXTURE_ENV, None)
    if fixture is not None:
        env[cli.FIXTURE_ENV] = fixture
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    if completed.stderr:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


def assert_no_profile(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if "created_by" in text or PROFILE_MARKER in text or cli.LEAK_MARKER in text:
        raise AssertionError("output included a user profile or a refused payload")


def walk_keys(value: object) -> None:
    if isinstance(value, dict):
        if "created_by" in value:
            raise AssertionError("created_by was emitted")
        for item in value.values():
            walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            walk_keys(item)


def check(kind: str, name: str, fn) -> bool:
    try:
        fn()
    except Exception as exc:
        print(f"[FAIL] {kind} {name}: {exc}")
        return False
    print(f"[PASS] {kind} {name}")
    return True


def fixture_positive() -> None:
    completed = run_cli(["table", "122777", "--json"], fixture="positive")
    payload = load_json(completed)
    if completed.returncode != 0:
        raise AssertionError(payload)
    record = payload["results"][0]
    assert record["table_id"] == "122777"
    assert record["feature_count"] == 47
    assert record["licence"] == "Creative Commons Attribution 4.0 International"
    assert payload["meta"]["latest_data"] == "2026-03-29T20:36:31.056278Z"
    assert payload["meta"]["publisher"] == "Stats NZ"
    walk_keys(payload)
    assert PROFILE_MARKER not in completed.stdout
    sample = run_cli(["sample", "122777", "--json"], fixture="positive")
    sample_payload = load_json(sample)
    if sample.returncode != 0:
        raise AssertionError(sample_payload)
    sample_record = sample_payload["results"][0]
    assert sample_record["sample_row_count"] == 47
    assert sample_record["feature_count"] == 47
    names = [row["Current_Geography_Name"] for row in sample_record["rows"]]
    assert "General Electorates\u00a02025" in names
    assert "Meshblock 2026 " in names
    assert sample_payload["meta"]["source_url"].endswith("/data/sample/")
    walk_keys(sample_payload)


def fixture_empty() -> None:
    completed = run_cli(["sample", "122777", "--json"], fixture="empty")
    payload = load_json(completed)
    if completed.returncode != 0:
        raise AssertionError(payload)
    record = payload["results"][0]
    assert record["feature_count"] == 0
    assert record["sample_row_count"] == 0
    assert record["rows"] == []
    assert "Community Board" not in completed.stdout


def fixture_wide() -> None:
    completed = run_cli(["sample", "123518", "--json"], fixture="wide")
    payload = load_json(completed)
    if completed.returncode != 0:
        raise AssertionError(payload)
    record = payload["results"][0]
    assert record["feature_count"] == 57575
    assert record["sample_row_count"] == 1
    assert record["rows"][0]["MB2026_code"] == "0176515"
    assert record["rows"][0]["SA22026_name"] == "Kingsway"
    assert record["sample_row_count"] != record["feature_count"]


def fixture_malformed() -> None:
    for mode in ("malformed", "schema"):
        completed = run_cli(["table", "122777", "--json"], fixture=mode)
        payload = load_json(completed)
        if completed.returncode != 6 or payload["error"]["type"] != "schema_failure":
            raise AssertionError((mode, completed.returncode, payload))
        assert payload["results"] == []


def fixture_truncated() -> None:
    completed = run_cli(["table", "122777", "--json"], fixture="truncated")
    payload = load_json(completed)
    if completed.returncode != 6:
        raise AssertionError(payload)
    assert "truncated" in payload["error"]["message"]
    assert payload["results"] == []


def fixture_http_status() -> None:
    limited = load_json(run_cli(["table", "122777", "--json"], fixture="http-429"))
    completed = run_cli(["table", "122777", "--json"], fixture="http-429")
    if completed.returncode != 4 or limited["error"]["retry_after"] != "17":
        raise AssertionError(limited)
    assert limited["error"]["type"] == "blocked"
    unavailable = run_cli(["table", "122777", "--json"], fixture="http-503")
    payload = load_json(unavailable)
    if unavailable.returncode != 5 or payload["error"]["type"] != "upstream_unavailable":
        raise AssertionError(payload)
    assert payload["results"] == []


def fixture_timeout() -> None:
    completed = run_cli(["table", "122777", "--json"], fixture="timeout")
    payload = load_json(completed)
    if completed.returncode != 5 or "timed out" not in payload["error"]["message"]:
        raise AssertionError(payload)


def fixture_redirect_and_hosts() -> None:
    redirected = run_cli(["table", "122777", "--json"], fixture="redirect")
    payload = load_json(redirected)
    if redirected.returncode != 7 or "outside" not in payload["error"]["message"]:
        raise AssertionError(payload)
    assert "example.com" not in redirected.stdout
    off_host = run_cli(["sample", "122777", "--json"], fixture="off-host")
    off_payload = load_json(off_host)
    if off_host.returncode != 7:
        raise AssertionError(off_payload)
    assert cli.LEAK_MARKER not in off_host.stdout
    try:
        cli.AllowlistRedirectHandler().redirect_request(
            None, None, 302, "Found", {}, "https://example.com/stolen"
        )
    except cli.SourceError as exc:
        if exc.code != 7:
            raise AssertionError(exc.code) from exc
    else:
        raise AssertionError("off-host redirect was accepted")
    kind, table_id = cli.parse_allowlisted(
        "https://datafinder.stats.govt.nz/services/api/v1/tables/122777/versions/434918/data/sample/"
    )
    assert (kind, table_id) == ("sample", "122777")


def fixture_refuses_query_and_licence() -> None:
    query = run_cli(["sample", "122777", "--json"], fixture="query-url")
    payload = load_json(query)
    if query.returncode != 7:
        raise AssertionError(payload)
    assert cli.LEAK_MARKER not in query.stdout
    assert "/services/query/" not in query.stdout
    licence = run_cli(["table", "122777", "--json"], fixture="bad-licence")
    licence_payload = load_json(licence)
    if licence.returncode != 7 or licence_payload["results"] != []:
        raise AssertionError(licence_payload)


def fixture_rejects_unknown_table_before_network() -> None:
    calls: list[str] = []

    def transport(url: str):
        calls.append(url)
        raise AssertionError("network transport was called")

    try:
        cli.run_command("table", "999999", transport)
    except cli.SourceError as exc:
        if exc.code != 2:
            raise AssertionError(exc.code) from exc
    else:
        raise AssertionError("unknown table was accepted")
    assert calls == []
    completed = run_cli(
        ["table", "https://datafinder.stats.govt.nz/services/query/v1/feature.json/122777/", "--json"]
    )
    payload = load_json(completed)
    if completed.returncode != 2:
        raise AssertionError(payload)
    assert "services/query" not in completed.stdout
    assert "Traceback" not in completed.stdout


def fixture_row_bound() -> None:
    header = ["__row__", "name"]
    rows = [[index, "place"] for index in range(cli.MAX_SAMPLE_ROWS + 1)]
    try:
        cli.parse_sample({"sample": [header, rows]})
    except cli.SourceError as exc:
        if exc.code != 7:
            raise AssertionError(exc.code) from exc
    else:
        raise AssertionError("oversized sample was accepted")


def contract_help_and_missing_args() -> None:
    help_run = run_cli(["--help"])
    if help_run.returncode != 0 or "table" not in help_run.stdout or "sample" not in help_run.stdout:
        raise AssertionError(help_run.stderr or help_run.stdout)
    missing = run_cli(["table", "--json"])
    payload = load_json(missing)
    if missing.returncode != 2 or payload["error"]["type"] != "invalid_input":
        raise AssertionError(payload)
    unknown = run_cli(["--thecolab-invalid-option", "--json"])
    unknown_payload = load_json(unknown)
    if unknown.returncode != 2 or unknown_payload["results"] != []:
        raise AssertionError(unknown_payload)


def run_fixture_checks() -> None:
    checks = (
        ("fixture", "positive metadata, sample text, and omitted profile", fixture_positive),
        ("fixture", "empty sample has no invented rows", fixture_empty),
        ("fixture", "wide sample keeps the meshblock code and table count", fixture_wide),
        ("fixture", "malformed and empty objects are schema failures", fixture_malformed),
        ("fixture", "truncated JSON is a schema failure", fixture_truncated),
        ("fixture", "HTTP 429 and 503 keep typed errors", fixture_http_status),
        ("fixture", "timeout is an upstream failure", fixture_timeout),
        ("fixture", "off-host redirect is rejected", fixture_redirect_and_hosts),
        ("fixture", "query URL and unclear licence are refused", fixture_refuses_query_and_licence),
        ("fixture", "unknown table makes no request", fixture_rejects_unknown_table_before_network),
        ("fixture", "sample row bound refuses a bulk extract", fixture_row_bound),
        ("contract", "help and invalid input", contract_help_and_missing_args),
    )
    failed = False
    for kind, name, fn in checks:
        failed = not check(kind, name, fn) or failed
    if failed:
        raise SystemExit(1)


def live_probe() -> None:
    table = run_cli(["table", LIVE_TABLE, "--json"], timeout=40)
    if table.returncode != 0:
        print(f"[FAIL] live table {LIVE_TABLE}: exit {table.returncode}")
        print(table.stdout or table.stderr)
        raise SystemExit(table.returncode or 1)
    table_payload = json.loads(table.stdout)
    record = table_payload["results"][0]
    licence = record.get("licence", "")
    feature_count = record.get("feature_count")
    if "Creative Commons Attribution 4.0" not in licence:
        print(f"[FAIL] live table {LIVE_TABLE} licence was {licence!r}")
        raise SystemExit(1)
    if isinstance(feature_count, bool) or not isinstance(feature_count, int) or feature_count < 1:
        print(f"[FAIL] live table {LIVE_TABLE} feature_count was {feature_count!r}")
        raise SystemExit(1)
    if record.get("table_id") != LIVE_TABLE or not record.get("title") or not record.get("published_at"):
        print(f"[FAIL] live table {LIVE_TABLE} metadata was incomplete")
        raise SystemExit(1)
    if table_payload["meta"].get("latest_data") != record["published_at"]:
        print("[FAIL] live latest_data did not keep published_at")
        raise SystemExit(1)
    walk_keys(table_payload)
    if "/services/query/" in table.stdout or "/export/" in table.stdout:
        print("[FAIL] live table output included a query or export URL")
        raise SystemExit(1)
    print(f"[PASS] live table {LIVE_TABLE} licence, feature count, and publication time")

    sample = run_cli(["sample", LIVE_TABLE, "--json"], timeout=40)
    if sample.returncode != 0:
        print(f"[FAIL] live sample {LIVE_TABLE}: exit {sample.returncode}")
        print(sample.stdout or sample.stderr)
        raise SystemExit(sample.returncode or 1)
    sample_payload = json.loads(sample.stdout)
    sample_record = sample_payload["results"][0]
    rows = sample_record.get("rows")
    if not isinstance(rows, list) or not rows:
        print(f"[FAIL] live sample {LIVE_TABLE} returned no rows")
        raise SystemExit(1)
    if sample_record.get("feature_count") != feature_count:
        print("[FAIL] live sample feature_count did not match table metadata")
        raise SystemExit(1)
    if sample_record.get("sample_row_count") != len(rows) or len(rows) > cli.MAX_SAMPLE_ROWS:
        print("[FAIL] live sample row count was inconsistent")
        raise SystemExit(1)
    names = [row.get("Current_Geography_Name") for row in rows if isinstance(row, dict)]
    if not any(isinstance(name, str) and name.strip() for name in names):
        print("[FAIL] live sample had no geography name")
        raise SystemExit(1)
    if not str(sample_payload["meta"].get("source_url", "")).endswith("/data/sample/"):
        print("[FAIL] live sample source_url was not the published sample endpoint")
        raise SystemExit(1)
    walk_keys(sample_payload)
    if "/services/query/" in sample.stdout or "created_by" in sample.stdout:
        print("[FAIL] live sample included a refused field or endpoint")
        raise SystemExit(1)
    print(f"[PASS] live sample {LIVE_TABLE} published rows and geography name")


def main() -> int:
    try:
        run_fixture_checks()
    except SystemExit as exc:
        return int(exc.code or 1)
    live_probe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
