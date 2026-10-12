#!/usr/bin/env python3
"""Deterministic repository and parser contract for Auckland Ride Report."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_test import audit_skill  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

import cli  # noqa: E402


def invoke(arguments: list[str]) -> tuple[int, dict, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    original_out, original_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr
    try:
        code = cli.main(arguments)
    finally:
        sys.stdout, sys.stderr = original_out, original_err
    text = stdout.getvalue()
    payload = json.loads(text) if "--json" in arguments and text else {}
    return code, payload, stderr.getvalue(), text


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_parser() -> None:
    code, payload, stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "catalogue-ok", "--json"]
    )
    require(code == 0 and stderr == "", stderr)
    record = payload["results"][0]
    require(record["total_trip_count"] == 60, "fixture total changed")
    require(record["period_label"] == "Q3 2026", "fixture label dropped")
    require("series" not in record, "summary invented a series")
    require(payload["meta"]["licence"].startswith("Data may be used"), "licence dropped")
    require(payload["meta"]["source_url"].endswith("/scooter/2026-Q3/trip_metrics.json"), payload["meta"]["source_url"])
    require(payload["meta"]["latest_data"] == "2026-07-03", "latest day was not the last daily bucket")
    require(record["mean_trip_duration_minutes"] == 8.5, "duration average dropped")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--series", "trips", "--limit", "2", "--fixture", "catalogue-ok", "--json"]
    )
    require(code == 0 and len(payload["results"][0]["series"]) == 2, "series limit was ignored")
    require(payload["results"][0]["series"][0]["x"] == "2026-07-01", "series order changed")
    require(any("truncated" in item for item in payload.get("warnings", [])), "truncation was silent")

    code, payload, stderr, _stdout = invoke(
        ["metrics", "--vehicle", "../scooter", "--period", "2026-Q3", "--json"]
    )
    require(code == 2 and payload["error"]["type"] == "invalid_input", "path token was accepted")
    require("Traceback" not in stderr, "path token traced")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "nope", "--period", "2026-Q3", "--fixture", "catalogue-ok", "--json"]
    )
    require(code == 2 and "not in the published" in payload["error"]["message"], "unknown vehicle fetched")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "1999-Q1", "--fixture", "catalogue-ok", "--json"]
    )
    require(code == 2 and "not published" in payload["error"]["message"], "unpublished period was requested")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--limit", "2", "--fixture", "catalogue-ok", "--json"]
    )
    require(code == 2 and "--limit" in payload["error"]["message"], "bare limit was accepted")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--series", "trips", "--limit", "93", "--json"]
    )
    require(code == 2, "oversized limit was accepted")

    code, payload, stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-malformed", "--json"]
    )
    require(code == 6 and payload["error"]["type"] == "schema_failure", "malformed JSON was not a schema failure")
    require("Traceback" not in stderr, "malformed JSON traced")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-nan", "--json"]
    )
    require(code == 6, "NaN JSON was accepted")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-missing", "--json"]
    )
    require(code == 6 and "totalTripCount" in payload["error"]["message"], "empty metrics succeeded")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-absent", "--json"]
    )
    require(code == 0 and payload["results"] == [], "absent export was not an empty success")
    require(any("no_export" in item for item in payload.get("warnings", [])), "absent export had no warning")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-rate-limit", "--json"]
    )
    require(code == 4 and payload["error"]["retry_after"] == "15", "retry_after dropped")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-unavailable", "--json"]
    )
    require(code == 5 and "503" in payload["error"]["message"], "HTTP 503 was not upstream_unavailable")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-timeout", "--json"]
    )
    require(code == 5 and "timed out" in payload["error"]["message"], "timeout was not typed")

    code, payload, _stderr, _stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "metrics-off-host", "--json"]
    )
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host redirect was followed")

    code, payload, stderr, _stdout = invoke(["dashboard", "--fixture", "catalogue-ok", "--json"])
    require(code == 0 and stderr == "", stderr)
    dashboard = payload["results"][0]
    require(dashboard["population"] == 1000001, "fixture population changed")
    require(dashboard["operators"] == ["Example Operator"], "operators changed")
    scooter = next(item for item in dashboard["vehicles"] if item["vehicle"] == "scooter")
    require([item["key"] for item in scooter["periods"]] == ["all", "2026-Q3"], "catalogue order changed")
    require("policies" not in dashboard, "operator polygon was copied into the result")

    code, _payload, stderr, stdout = invoke(
        ["metrics", "--vehicle", "scooter", "--period", "2026-Q3", "--fixture", "catalogue-ok"]
    )
    require(code == 0 and "Ride Report" in stdout and "public.ridereport.com" in stdout, stdout)
    require("Traceback" not in stderr and stdout.strip()[0] != "{", "human output became JSON or a traceback")

    code, payload, stderr, _stdout = invoke(["--thecolab-invalid-option", "--json"])
    require(code == 2 and payload["error"]["code"] == 2 and stderr == "", stderr or payload)


def check_bounds() -> None:
    url = cli.metrics_url("scooter", "2026-Q3")
    require(url == f"https://{cli.EXPORT_HOST}/auckland/data-export/scooter/2026-Q3/trip_metrics.json", url)
    rejected = (
        "http://public.ridereport.com/auckland",
        "https://user:secret@public.ridereport.com/auckland",
        "https://evil.example/data",
        "https://public.ridereport.com/wellington",
        "https://api.ridereport.com/public/settings?slug=wellington&environment=production",
        f"https://{cli.EXPORT_HOST}/auckland/base-data/street_segments.geojson",
        f"https://{cli.EXPORT_HOST}/auckland/data-export/scooter/2026-Q3/route_aggregation.geojson",
        f"https://{cli.EXPORT_HOST}/auckland/data-export/scooter/../all/trip_metrics.json",
    )
    for candidate in rejected:
        try:
            cli.validate_outbound_url(candidate)
        except cli.UnsafeError:
            continue
        raise AssertionError(f"unsafe URL accepted: {candidate}")
    try:
        cli.metrics_url("../scooter", "2026-Q3")
    except cli.InputError:
        pass
    else:
        raise AssertionError("metrics_url accepted a traversal token")

    raw = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03"  # truncated gzip header-ish
    import gzip
    encoded = gzip.compress(b'{"totalTripCount": 1}')
    decoded = cli.decode_body(encoded, "gzip", 100)
    require(decoded == b'{"totalTripCount": 1}', "gzip metrics body was not decoded")
    try:
        cli.decode_body(encoded, "gzip", 4)
    except cli.UpstreamError:
        pass
    else:
        raise AssertionError("gzip expansion ignored the size cap")
    try:
        cli.decode_body(raw, "gzip", 100)
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("truncated gzip became a success")

    meta = provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03Z")
    require(meta["retrieved_at"] == "2026-10-01T01:02:03Z", "cached retrieval time changed")
    require("licence" not in provenance("https://example.invalid/data", "Fixture publisher"), "unknown licence invented")
    failure = error_envelope(4, "rate-limited", meta, retry_after="15")
    require(failure["error"]["type"] == "blocked" and failure["results"] == [], "error envelope changed")
    require(result_envelope([], meta)["results"] == [], "empty results dropped")


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_parser()
        check_bounds()
        result["checks"].extend(("parser_fixtures", "bounds"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
