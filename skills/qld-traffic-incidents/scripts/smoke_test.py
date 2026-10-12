#!/usr/bin/env python3
"""Fixture checks and one bounded live probe for Queensland traffic incidents."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import cli  # noqa: E402

FIXTURES = SCRIPT_DIR.parent / "tests" / "fixtures"
OUTAGE = re.compile(r"network error|timed out|http (?:429|503)|HTTP 5\d\d", re.I)


def load_json(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_cli(argv: list[str], *, fixture: str | None) -> tuple[int, str, str]:
    previous = os.environ.get(cli.FIXTURE_ENV)
    if fixture is None:
        os.environ.pop(cli.FIXTURE_ENV, None)
    else:
        os.environ[cli.FIXTURE_ENV] = fixture
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(argv)
    finally:
        if previous is None:
            os.environ.pop(cli.FIXTURE_ENV, None)
        else:
            os.environ[cli.FIXTURE_ENV] = previous
    return code, stdout.getvalue(), stderr.getvalue()


def exercise_fixtures() -> list[str]:
    """Run offline parser and argument checks. Raise AssertionError on failure."""
    lines: list[str] = []
    original_fetch = cli.fetch_json

    def refuse_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network fetch during offline fixture")

    cli.fetch_json = refuse_network
    try:
        code, stdout, stderr = run_cli(["incidents", "--limit", "1", "--json"], fixture="positive")
        assert code == 0, stderr or stdout
        assert stderr == ""
        payload = json.loads(stdout)
        assert payload["meta"]["licence"] == "CC BY 4.0"
        assert payload["meta"]["publisher"] == "Queensland"
        assert payload["meta"]["latest_data"] == "2026-10-11T18:03:09+00:00"
        assert payload["meta"]["total_count"] == "1"
        assert payload["meta"]["source_url"].startswith("https://queensland.opendatasoft.com/")
        assert "error" not in payload
        record = payload["results"][0]
        assert record["id"] == "fixture-1001"
        assert record["category"] == "Hazard"
        assert record["duration_start"] == "2026-01-02T03:04:05+00:00"
        assert record["longitude"] == 153.0
        assert record["latitude"] == -27.5
        lines.append("[PASS] fixture positive incident keeps id, category, point and licence")

        code, stdout, stderr = run_cli(["incidents", "--limit", "1", "--format", "geojson"], fixture="positive")
        assert code == 0, stderr or stdout
        collection = json.loads(stdout)
        assert collection["type"] == "FeatureCollection"
        assert collection["features"][0]["geometry"]["coordinates"] == [153.0, -27.5]
        assert collection["features"][0]["properties"]["id"] == "fixture-1001"
        lines.append("[PASS] fixture geojson point is longitude then latitude")

        total, rows = cli.parse_records(load_json("records-empty.json"), limit=1)
        assert total == 0 and rows == []
        lines.append("[PASS] fixture empty result stays empty")

        try:
            cli.loads_strict((FIXTURES / "records-truncated.txt").read_bytes())
        except cli.SourceFailure as failure:
            assert failure.code == 6
        else:
            raise AssertionError("truncated JSON accepted")
        try:
            cli.loads_strict((FIXTURES / "records-html.txt").read_bytes())
        except cli.SourceFailure as failure:
            assert failure.code == 6
        else:
            raise AssertionError("HTML payload accepted")
        lines.append("[PASS] fixture malformed payload is schema_failure")

        try:
            cli.parse_records(load_json("records-over-limit.json"), limit=1)
        except cli.SourceFailure as failure:
            assert failure.code == 6
        else:
            raise AssertionError("over-limit payload accepted")
        lines.append("[PASS] fixture over-limit payload is schema_failure")

        limited = json.loads((FIXTURES / "http-429.json").read_text(encoding="utf-8"))
        blocked = cli.failure_from_status(int(limited["status"]), {"retry-after": str(limited["retry_after"])})
        assert blocked.code == 4 and blocked.retry_after == "30"
        envelope = cli.error_envelope(blocked.code, blocked.message, cli.source_meta(None, cli.DATASET_URL), retry_after=blocked.retry_after)
        assert envelope["error"]["type"] == "blocked"
        assert envelope["results"] == []
        lines.append("[PASS] fixture http 429 is blocked and keeps retry_after")

        unavailable = json.loads((FIXTURES / "http-503.json").read_text(encoding="utf-8"))
        down = cli.failure_from_status(int(unavailable["status"]), {})
        assert down.code == 5 and "503" in down.message
        lines.append("[PASS] fixture http 503 is upstream_unavailable")

        try:
            cli.parse_dataset(load_json("dataset-unlicensed.json"))
        except cli.SourceFailure as failure:
            assert failure.code == 4
        else:
            raise AssertionError("missing licence accepted")
        lines.append("[PASS] fixture missing licence is blocked")

        try:
            cli.parse_dataset(load_json("dataset-other-licence.json"))
        except cli.SourceFailure as failure:
            assert failure.code == 4
        else:
            raise AssertionError("other licence accepted")
        lines.append("[PASS] fixture other licence is blocked")

        handler = cli.AllowlistRedirectHandler()
        request = urllib.request.Request(cli.DATASET_URL)
        try:
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/elsewhere")
        except cli.SourceFailure as failure:
            assert failure.code == 7
        else:
            raise AssertionError("off-host redirect accepted")
        try:
            handler.redirect_request(request, None, 302, "Found", {}, "http://queensland.opendatasoft.com/records")
        except cli.SourceFailure as failure:
            assert failure.code == 7
        else:
            raise AssertionError("HTTP downgrade accepted")
        lines.append("[PASS] fixture off-host redirect is rejected")

        where = cli.build_where(
            status=None,
            category=None,
            lga=None,
            bbox=(153.0, -28.2, 153.1, -28.1),
        )
        assert where == "in_bbox(geo_point_2d,-28.2,153,-28.1,153.1)"
        query = cli.records_query_url(limit=1, bbox=(153.0, -28.2, 153.1, -28.1))
        cli.assert_official_url(query)
        assert "example.com" not in query
        lines.append("[PASS] fixture bbox filter is upstream point-in-box")

        for argv in (
            ["incidents", "--limit", "0", "--json"],
            ["incidents", "--limit", "21", "--json"],
            ["incidents", "--json"],
            ["incidents", "--limit", "1", "--category", 'say"no', "--json"],
            ["incidents", "--limit", "1", "--bbox", "153,-28,152,-27", "--json"],
            ["--thecolab-invalid-option", "--json"],
        ):
            code, stdout, stderr = run_cli(argv, fixture="positive")
            assert code == 2, argv
            assert stderr == ""
            error = json.loads(stdout)
            assert error["results"] == []
            assert error["error"]["code"] == 2
            assert error["error"]["type"] == "invalid_input"
        lines.append("[PASS] contract malformed arguments exit 2 before fetch")
    finally:
        cli.fetch_json = original_fetch
    return lines


def live_probe() -> int:
    env = os.environ.copy()
    env.pop(cli.FIXTURE_ENV, None)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "cli.py"), "incidents", "--limit", "1", "--json"],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
        env=env,
    )
    text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        if OUTAGE.search(text):
            print(text)
            return 5
        print("[FAIL] live incidents command failed")
        print(text)
        return 1
    if completed.stderr.strip():
        print("[FAIL] live incidents wrote stderr")
        print(completed.stderr)
        return 1
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print("[FAIL] live incidents response was not JSON")
        return 1
    meta = payload.get("meta") if isinstance(payload, dict) else None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(meta, dict) or not isinstance(results, list):
        print("[FAIL] live incidents envelope was incomplete")
        return 1
    if meta.get("licence") != "CC BY 4.0":
        print("[FAIL] live dataset licence was not CC BY 4.0")
        return 1
    if not str(meta.get("source_url", "")).startswith("https://queensland.opendatasoft.com/"):
        print("[FAIL] live source_url left the official host")
        return 1
    try:
        total = int(meta.get("total_count", "0"))
    except (TypeError, ValueError):
        total = 0
    if total < 1 or not results:
        print("[FAIL] live zero incidents")
        return 1
    if len(results) > 1:
        print("[FAIL] live response exceeded limit 1")
        return 1
    record = results[0]
    if not isinstance(record, dict) or not str(record.get("id", "")).strip():
        print("[FAIL] live incident id was missing")
        return 1
    longitude = record.get("longitude")
    latitude = record.get("latitude")
    if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
        print("[FAIL] live incident point was missing")
        return 1
    if not (-180 <= float(longitude) <= 180 and -90 <= float(latitude) <= 90):
        print("[FAIL] live incident point was outside WGS84 range")
        return 1
    print(
        f"[PASS] live incident {record['id']} licence CC BY 4.0 "
        f"total_count {total} point {longitude},{latitude}"
    )
    return 0


def main() -> int:
    try:
        for line in exercise_fixtures():
            print(line)
    except AssertionError as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    return live_probe()


if __name__ == "__main__":
    raise SystemExit(main())
