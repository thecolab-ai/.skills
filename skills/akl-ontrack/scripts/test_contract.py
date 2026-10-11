#!/usr/bin/env python3
"""Deterministic repository contract test for AKLOnTrack observations."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
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

import cli  # noqa: E402

DATA_COMMAND = ("index", "--fixture", "index-positive.json", "--limit", "2", "--json")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def check_provenance_contract() -> None:
    script = Path(__file__).with_name("cli.py")
    cases = (
        ((*DATA_COMMAND, ), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = subprocess.run(
            [sys.executable, str(script), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert completed.returncode == expected_code, completed.stderr or completed.stdout
        assert not completed.stderr, completed.stderr
        payload = json.loads(completed.stdout)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"]
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
            assert payload["results"][0]["date"] == "2026-10-11"
            assert payload["results"][0]["rows"] == 7293
            assert payload["results"][0]["bytes"] == 239224
            assert payload["meta"]["latest_data"] == "2026-10-11"
            assert "CC BY 4.0" in payload["meta"]["licence"]
            assert "Auckland Transport" in payload["meta"]["licence"]

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
    invalid_boxes = (
        "174,-37,175",
        "a,b,c,d",
        "nan,-37,175,-36",
        "174,-37,inf,-36",
        "175,-37,174,-36",
        "174,-36,175,-37",
        "-181,-37,175,-36",
        "174,-91,175,-36",
        "174,-37,181,-36",
        "174,-37,175,91",
        "174,-37,174,-36",
    )
    for invalid in invalid_boxes:
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
    assert parser.parse_args(["--bbox=-180,-90,180,90"]).bbox == (-180.0, -90.0, 180.0, 90.0)
    collection = geojson_envelope([], meta)
    assert collection == {"type": "FeatureCollection", "features": [], "meta": meta}


def _loads(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_checks() -> list[str]:
    """Offline parser, status and bounds checks. Prints one line per case."""
    failures: list[str] = []

    def check(kind: str, name: str, condition: bool) -> None:
        if condition:
            print(f"[PASS] {kind} {name}")
            return
        print(f"[FAIL] {kind} {name}")
        failures.append(f"{kind} {name}")

    records = cli.parse_day_document(
        _loads("day-positive.json"),
        expected_date="2026-07-23",
        source_url=cli.INDEX_URL,
    )
    first, second, omitted, partial = records
    check(
        "fixture",
        "positive day keeps delay seconds and Auckland time",
        first["departure_delay"] == 47
        and first["arrival_delay"] == 0
        and first["arrival_time"] == "2026-07-23T05:08:00+12:00"
        and first["departure_time"] == "2026-07-23T05:08:47+12:00"
        and first["stop_id"] == "9322-6bc7f9b8"
        and first["state_label"] == "stopped"
        and second["state"] == 3
        and second["state_label"] == "no_report"
        and second["arrival_delay"] == -5
        and second["stop_rel"] == 7,
    )
    check(
        "fixture",
        "omitted times stay null",
        omitted["state"] == 3
        and omitted["arrival_delay"] is None
        and omitted["departure_delay"] is None
        and omitted["arrival"] is None
        and omitted["departure"] is None
        and omitted["arrival_time"] is None
        and omitted["departure_time"] is None
        and partial["arrival_delay"] == 217
        and partial["departure_delay"] is None
        and partial["arrival"] == 26617
        and partial["departure"] is None
        and partial["arrival_time"] == "2026-07-23T07:23:37+12:00"
        and partial["departure_time"] is None,
    )
    empty = cli.parse_day_document(
        _loads("day-empty.json"),
        expected_date="2026-07-09",
        source_url=cli.INDEX_URL,
    )
    check("fixture", "empty day returns no invented rows", empty == [])
    malformed = False
    try:
        cli.parse_json_bytes((FIXTURES / "malformed-body.txt").read_bytes(), source_url=cli.INDEX_URL)
    except cli.SchemaError as exc:
        malformed = "non-JSON" in str(exc)
    check("fixture", "malformed payload is schema_failure", malformed)
    limited = cli.status_error(429, {"Retry-After": "30"})
    unavailable = cli.status_error(503, {})
    check(
        "fixture",
        "status 429 is blocked and preserves retry_after",
        isinstance(limited, cli.BlockedError)
        and limited.code == 4
        and limited.retry_after == "30",
    )
    check(
        "fixture",
        "status 503 is an unavailable response",
        isinstance(unavailable, cli.UpstreamError)
        and unavailable.code == 5
        and "HTTP 503" in str(unavailable),
    )
    off_host = False
    try:
        cli.parse_index_document(_loads("index-off-host.json"))
    except cli.SchemaError as exc:
        off_host = "allowlist" in str(exc)
    check("fixture", "off-host base_url is rejected", off_host)
    refused = False
    try:
        cli.parse_index_document(_loads("index-unlicensed.json"))
    except cli.BlockedError as exc:
        refused = exc.code == 4 and "CC BY 4.0" in str(exc)
    check("fixture", "uncertain licence is refused", refused)
    fetched = False

    def boom(url: str, limit: int) -> cli.HttpResult:
        nonlocal fetched
        fetched = True
        raise AssertionError(url)

    invalid_date = False
    try:
        cli.execute(["day", "2026-02-31", "--json"], boom)
    except cli.InputError as exc:
        invalid_date = exc.code == 2 and not fetched
    check("fixture", "invalid date does not fetch", invalid_date)

    bad_width = False
    try:
        cli.parse_day_document(
            _loads("day-bad-width.json"),
            expected_date="2026-07-23",
            source_url=cli.INDEX_URL,
        )
    except cli.SchemaError:
        bad_width = True
    check("fixture", "short stop row is schema_failure", bad_width)

    calls: list[str] = []
    index_body = (FIXTURES / "index-match.json").read_bytes()
    day_body = (FIXTURES / "day-positive.json").read_bytes()
    day_url = "https://data.aklontrack.com/open/v1/observations/2026/07/23.json"

    def transport(url: str, limit: int) -> cli.HttpResult:
        calls.append(url)
        if url == cli.INDEX_URL and limit == cli.MAX_INDEX_BYTES:
            return cli.HttpResult(200, {}, url, index_body)
        if url == day_url and limit == cli.MAX_DAY_BYTES:
            return cli.HttpResult(200, {}, url, day_body)
        raise AssertionError((url, limit))

    with redirect_stdout(io.StringIO()):
        code = cli.execute(["day", "--latest", "--limit", "1", "--json"], transport)
    check(
        "contract",
        "day fetch performs two GETs",
        code == 0 and calls == [cli.INDEX_URL, day_url],
    )
    handler = cli.AllowlistRedirect()
    request = urllib.request.Request(cli.INDEX_URL)
    redirected = False
    try:
        handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/elsewhere")
    except cli.BlockedError as exc:
        redirected = exc.code == 4
    check("fixture", "off-host redirect is rejected", redirected)
    empty_index = cli.parse_index_document(_loads("index-empty.json"))
    check(
        "fixture",
        "empty index is an empty catalogue",
        empty_index.days == () and empty_index.latest_data is None and "CC BY 4.0" in empty_index.licence,
    )
    return failures


def main() -> int:
    check_provenance_contract()
    failures = fixture_checks()
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"] and not failures:
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "fixtures"))
    elif failures:
        result["ok"] = False
        result["errors"].extend(failures)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
