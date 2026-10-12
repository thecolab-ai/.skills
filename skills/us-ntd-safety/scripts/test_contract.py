#!/usr/bin/env python3
"""Deterministic contract tests for US NTD safety commands."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cli
from fields import DENIED_FIELDS, EVENTS_FIELDS, MODES_FIELDS

SKILL = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL.parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import audit_skill  # noqa: E402
from provenance import (  # noqa: E402
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    parse_bbox,
    provenance,
    result_envelope,
)

DATA_COMMAND = ("events", "--limit", "1", "--fixture", "events-positive", "--json")
MARKERS = ("fixture-narrative-marker", "fixture-person-marker", "fixture-address-marker")


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "cli.py"), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    assert not completed.stderr, completed.stderr
    return json.loads(completed.stdout)


def expect_error(function, code: int) -> None:
    try:
        function()
    except cli.SkillError as exc:
        assert exc.code == code, exc
    else:
        raise AssertionError(f"expected exit {code}")


def check_provenance_contract() -> None:
    cases = (
        ((*DATA_COMMAND,), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = run_cli(list(arguments))
        assert completed.returncode == expected_code, completed.stderr or completed.stdout
        payload = load_json(completed)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"] == "Federal Transit Administration"
        assert meta["geography"] == "United States"
        assert meta["retrieved_at"].endswith("Z")
        retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
        assert retrieved.utcoffset() == timedelta(0)
        assert isinstance(payload["results"], list)
        if expected_code:
            assert payload["results"] == []
            assert payload["error"]["code"] == expected_code
            assert payload["error"]["type"] == "invalid_input"
        else:
            assert "error" not in payload
            assert payload["results"]

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    assert "licence" not in meta and "latest_data" not in meta
    cached = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    assert cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09"
    assert cached["retrieved_at"] == "2026-10-01T01:02:03Z"
    normalised = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    assert normalised["retrieved_at"] == cached["retrieved_at"]
    try:
        provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    assert result_envelope([], cached)["results"] == []
    failure = error_envelope(4, "rate-limited", meta, retry_after="60")
    assert failure["error"]["type"] == "blocked" and failure["error"]["retry_after"] == "60"
    assert parse_bbox("174,-37,175,-36") == (174.0, -37.0, 175.0, -36.0)
    for invalid in ("174,-37,175", "nan,-37,175,-36", "175,-37,174,-36"):
        try:
            parse_bbox(invalid)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"invalid bbox accepted: {invalid}")
    parser = argparse.ArgumentParser()
    add_spatial_arguments(parser)
    args = parser.parse_args(["--bbox", "174,-37,175,-36", "--format", "geojson"])
    assert args.bbox == (174.0, -37.0, 175.0, -36.0) and args.format == "geojson"
    collection = geojson_envelope([], meta)
    assert collection["type"] == "FeatureCollection" and collection["features"] == []


def query(limit: int = 1, **kwargs) -> cli.Query:
    return cli.Query(
        limit=limit,
        year=kwargs.get("year"),
        month=kwargs.get("month"),
        mode=kwargs.get("mode"),
        ntd_id=kwargs.get("ntd_id"),
    )


def fixture_checks() -> None:
    contract = json.loads((SKILL / "tests" / "fixtures" / "contract.json").read_text(encoding="utf-8"))
    assert contract["skill"] == "us-ntd-safety"
    assert contract["contains_personal_data"] is False
    assert contract["contains_live_credentials"] is False
    assert not DENIED_FIELDS.intersection(name for name, _dtype in EVENTS_FIELDS + MODES_FIELDS)
    print("[PASS] fixture contract sentinel and withheld fields stay off the allowlist")

    events_url = cli.rows_url("events", query(year=2024, mode="MB", ntd_id="00000"))
    modes_url = cli.rows_url("modes", query(year=2024, month="January", mode="HR"))
    for url, resource_id in ((events_url, "9ivb-8ae9"), (modes_url, "5ti2-5uiv")):
        parsed = urlparse(url)
        assert parsed.scheme == "https" and parsed.hostname == "data.transportation.gov"
        assert parsed.username is None and resource_id in parsed.path
        query_text = parsed.query
        for denied in ("incident_description", "person_list", "approximate_address", "latitude", "longitude"):
            assert denied not in query_text
        params = parse_qs(query_text)
        assert params["$limit"] == ["1"]
    events_where = parse_qs(urlparse(events_url).query)["$where"][0]
    assert events_where == "year=2024 AND mode='MB' AND _5_digit_ntd_id='00000'"
    modes_where = parse_qs(urlparse(modes_url).query)["$where"][0]
    assert modes_where == "year=2024 AND month='January' AND mode='HR'"
    assert len(events_url) < 8000 and len(modes_url) < 8000
    print("[PASS] fixture request URLs stay on the official host and omit narratives")

    expect_error(lambda: cli.assert_official_url("https://evil.example/resource"), 4)
    expect_error(lambda: cli.assert_official_url("http://data.transportation.gov/resource/9ivb-8ae9.json"), 4)
    userinfo = "https://" + "user" + ":" + "pw" + "@" + cli.HOST + "/resource/9ivb-8ae9.json"
    expect_error(lambda: cli.assert_official_url(userinfo), 4)
    handler = cli.AllowlistRedirectHandler()
    request = cli.urllib.request.Request(cli.view_url("events"))
    expect_error(
        lambda: handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/steal"),
        4,
    )
    print("[PASS] fixture off-host redirects and non-HTTPS URLs are refused")

    called = {"count": 0}

    def boom(url: str) -> dict:
        called["count"] += 1
        raise AssertionError(url)

    original = cli.fetch_exchange
    cli.fetch_exchange = boom
    try:
        rejected = (
            ["events", "--limit", "0", "--json"],
            ["events", "--limit", "101", "--json"],
            ["events", "--year", "1899", "--json"],
            ["events", "--mode", "mb", "--json"],
            ["modes", "--month", "Jan", "--json"],
            ["events", "--ntd-id", "12", "--json"],
            ["events", "--fixture", "../events-positive", "--json"],
            ["events", "--fixture", "no-such-fixture", "--json"],
        )
        for arguments in rejected:
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(arguments)
            assert code == 2, arguments
        assert called["count"] == 0
    finally:
        cli.fetch_exchange = original
    print("[PASS] fixture malformed limits, filters and fixture names fail before any request")

    positive = cli.execute("events", query(), "events-positive")
    encoded = json.dumps(positive)
    row = positive["results"][0]
    assert positive["meta"]["licence"] == "USGOV_WORKS"
    assert positive["meta"]["licence_name"] == "Public Domain U.S. Government"
    assert positive["meta"]["latest_data"] == "2026-10-06T19:04:06Z"
    assert positive["meta"]["resource_id"] == "9ivb-8ae9"
    assert positive["meta"]["units"]["property_damage"] == "US dollars"
    assert "vehicle_speed" not in positive["meta"]["units"]
    assert row["agency"] == "Synthetic Transit Agency"
    assert row["year"] == 2024 and row["total_fatalities"] == 0 and row["total_injuries"] == 1
    assert row["property_damage"] == "n/a"
    assert positive["meta"]["unparsed_measures"] == ["property_damage"]
    assert row["fixed_route_flag"] is True
    assert row["incident_date"] == "2024-06-01T00:00:00.000"
    assert row["incident_time"] == "9:00:00 AM"
    for marker in MARKERS:
        assert marker not in encoded
    for denied in ("incident_description", "person_list", "approximate_address", "latitude", "longitude", "latlon"):
        assert denied not in row
    print("[PASS] fixture events keep coded fields, units, source dates and drop narratives")

    empty = cli.execute("events", query(), "events-empty")
    assert empty["results"] == [] and empty["meta"]["count"] == 0 and "error" not in empty
    print("[PASS] fixture empty events stay empty")

    expect_error(lambda: cli.execute("events", query(), "events-malformed"), 6)
    expect_error(lambda: cli.execute("events", query(), "events-schema"), 6)
    expect_error(lambda: cli.execute("events", query(), "events-bad-row"), 6)
    try:
        cli.execute("events", query(), "events-long-text")
    except cli.SkillError as exc:
        assert exc.code == 6 and "AAAA" not in str(exc)
    else:
        raise AssertionError("over-long coded text was accepted")
    print("[PASS] fixture malformed, schema, bad-row and over-long text fail closed")

    limited = run_cli(["events", "--limit", "1", "--fixture", "events-429", "--json"])
    assert limited.returncode == 4
    limited_payload = load_json(limited)
    assert limited_payload["results"] == []
    assert limited_payload["error"]["type"] == "blocked"
    assert limited_payload["error"]["retry_after"] == "30"
    unavailable = run_cli(["events", "--limit", "1", "--fixture", "events-503", "--json"])
    assert unavailable.returncode == 5
    unavailable_payload = load_json(unavailable)
    assert unavailable_payload["error"]["type"] == "upstream_unavailable"
    assert "HTTP 503" in unavailable_payload["error"]["message"]
    print("[PASS] fixture HTTP 429 and 503 keep typed errors and an empty result")

    for resource, fixture, required in (
        ("events", "events-licence", "USGOV_WORKS"),
        ("modes", "modes-licence", "PUBLIC_DOMAIN"),
    ):
        try:
            cli.execute(resource, query(), fixture)
        except cli.SkillError as exc:
            assert exc.code == 4
            assert required in str(exc)
            assert "Should Not Emit" not in str(exc)
            for marker in MARKERS:
                assert marker not in str(exc)
        else:
            raise AssertionError(f"{resource} accepted the other resource licence")
    print("[PASS] fixture each resource refuses the other resource licence id")

    modes = cli.execute("modes", query(), "modes-positive")
    mode_row = modes["results"][0]
    assert modes["meta"]["licence"] == "PUBLIC_DOMAIN"
    assert modes["meta"]["licence_name"] == "Public Domain"
    assert modes["meta"]["latest_data"] == "2026-10-06T18:51:31Z"
    assert modes["meta"]["resource_id"] == "5ti2-5uiv"
    assert modes["meta"]["units"]["ridership"] == "boardings"
    assert modes["meta"]["units"]["vehicle_revenue_miles"] == "miles"
    assert mode_row["month"] == "January" and mode_row["year"] == 2024
    assert mode_row["ridership"] == 12 and mode_row["vehicle_revenue_miles"] == 10
    assert mode_row["vehicles"] is None
    assert "total_derailments" not in mode_row
    assert mode_row["collisions_with_person"] == 0
    assert mode_row["personal_security_events"] == 0
    assert "incident_description" not in mode_row
    print("[PASS] fixture modes keep monthly aggregates, stated units and explicit nulls")


def main() -> int:
    result = audit_skill(SKILL)
    if result["ok"]:
        check_provenance_contract()
        fixture_checks()
        result["checks"].extend(("provenance", "json_errors", "fixtures_behaviour", "licence_gate"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
