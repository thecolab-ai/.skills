#!/usr/bin/env python3
"""Deterministic repository and parser contract for LINZ tide gauges."""
import argparse
import io
import json
import subprocess
import sys
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nzfetch  # noqa: E402
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

DATA_COMMAND = (
    "readings",
    "--gauge",
    "AUCT",
    "--date",
    "2026-01-01",
    "--sensor",
    "40",
    "--fixture",
    "daily-excerpt.csv",
    "--limit",
    "2",
    "--json",
)


def invoke(arguments: list[str]) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    text = stdout.getvalue()
    payload = json.loads(text) if "--json" in arguments else {}
    return code, payload, stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_parser_contracts() -> None:
    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "" and "error" not in payload, "fixture readings failed")
    require(payload["meta"]["retrieval_kind"] == "fixture", "fixture run was marked live")
    require(payload["meta"]["observation_time"] == "UTC", "readings clock was not UTC")
    require(payload["meta"]["latest_data"] == "2026-01-01T00:03:00Z", "latest_data followed the page instead of the file")
    require(payload["meta"]["matched_count"] == 4 and payload["meta"]["truncated"] is True, "page bounds were wrong")
    require(payload["results"][0]["observed_at"] == "2026-01-01T00:00:00Z", "midnight UTC was shifted")
    require(payload["results"][0]["height_m"] == "5.002", "source height precision changed")
    require("New Zealand local" not in json.dumps(payload), "UTC readings were described as local time")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "utc-midday.csv", "--json"]
    )
    require(code == 0 and payload["results"] == [
        {"gauge": "AUCT", "sensor": "40", "observed_at": "2026-01-01T11:00:00Z", "height_m": "4.594"}
    ], "11:00 UTC was converted as if it were New Zealand local time")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-02", "--sensor", "40", "--fixture", "daily-excerpt.csv", "--json"]
    )
    require(code == 6 and payload["error"]["type"] == "schema_failure" and payload["results"] == [], "wrong UTC date was accepted")

    for arguments, expected in (
        (["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "duplicate-daily.csv", "--json"], "duplicate"),
        (["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "malformed-daily.csv", "--json"], "timestamp"),
        (["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "malformed-files.json", "--json"], "file name"),
    ):
        code, payload, _stderr = invoke(arguments)
        require(code == 6 and expected in payload["error"]["message"] and payload["results"] == [], expected)

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "bom-daily.csv", "--json"]
    )
    require(code == 0 and payload["results"][0]["height_m"] == "5.002", "UTF-8 BOM CSV failed")

    code, payload, _stderr = invoke(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--fixture", "daily-excerpt.zip", "--json"]
    )
    require(code == 0 and payload["meta"]["matched_count"] == 4, "zip fixture failed")

    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "list-files.json", "--limit", "1", "--offset", "1", "--json"]
    )
    require(
        code == 0
        and payload["results"][0]["name"] == "AUCT_40_2026002.zip"
        and payload["results"][0]["utc_date"] == "2026-01-02"
        and payload["meta"]["matched_count"] == 3
        and payload["meta"]["truncated"] is True
        and payload["meta"]["latest_data"] == "2026-01-05"
        and "not an observation time" in payload["meta"]["latest_data_meaning"],
        "file page or modified-date meaning was wrong",
    )
    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "list-files.json", "--offset", "3", "--json"]
    )
    require(code == 0 and payload["results"] == [] and payload["meta"]["query_status"] == "ok" and payload["meta"]["matched_count"] == 3, "empty page looked like no match")

    code, payload, _stderr = invoke(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--fixture", "empty-files.json", "--json"]
    )
    require(code == 0 and payload["results"] == [] and payload["meta"]["query_status"] == "ok" and "error" not in payload, "empty file list looked like an outage")

    code, payload, _stderr = invoke(
        ["datasets", "--gauge", "AUCT", "--fixture", "gauge-datasets.json", "--json"]
    )
    require(code == 0 and payload["meta"]["latest_data"] == "2026" and {row["sensor"] for row in payload["results"]} == {"40", "41"}, "dataset fixture failed")

    code, payload, _stderr = invoke(["gauges", "--fixture", "list-gauges.json", "--json"])
    require(code == 0 and "AUCT" in {row["gauge"] for row in payload["results"]} and "latest_data" not in payload["meta"], "gauge fixture failed")

    def gauges_only(url: str, *, expect_json: bool, timeout: int) -> bytes:
        require(timeout == 10 and expect_json is True, "gauge lookup was unbounded")
        if url.endswith("/api/listGauges"):
            return b'{"gauges":["AUCT"]}'
        raise AssertionError(url)

    original = cli.http_get
    cli.http_get = gauges_only
    try:
        code, payload, _stderr = invoke(["datasets", "--gauge", "ZZZZ", "--json"])
    finally:
        cli.http_get = original
    require(code == 0 and payload["meta"]["query_status"] == "no_match" and payload["results"] == [] and "error" not in payload, "unknown gauge looked like an outage")

    def fail_network(url: str, *, expect_json: bool, timeout: int) -> bytes:
        raise nzfetch.FetchError("timed out")

    cli.http_get = fail_network
    try:
        code, payload, stderr = invoke(["gauges", "--json"])
    finally:
        cli.http_get = original
    require(code == 5 and payload["results"] == [] and payload["error"]["type"] == "upstream_unavailable" and payload["error"]["message"].startswith("network error:") and stderr == "", "network failure looked like an empty result")

    def blocked(url: str, *, expect_json: bool, timeout: int) -> bytes:
        raise nzfetch.Blocked("challenge")

    cli.http_get = blocked
    try:
        code, payload, _stderr = invoke(["gauges", "--json"])
    finally:
        cli.http_get = original
    require(code == 4 and payload["error"]["type"] == "blocked" and "network error:" in payload["error"]["message"], "block was not explicit")

    def redirect(url: str, **kwargs) -> tuple[bytes, str, str]:
        require(kwargs.get("timeout") == 10, "redirect probe had no timeout")
        require(kwargs.get("allowed_hosts") == cli.ALLOWED_HOSTS, "redirect probe dropped the host allowlist")
        return b'{"gauges":["AUCT"]}', "application/json", "https://evil.example/api/listGauges"

    original_fetch = cli.nzfetch.fetch_bytes
    cli.nzfetch.fetch_bytes = redirect
    try:
        code, payload, _stderr = invoke(["gauges", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original_fetch
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "cross-host redirect was followed")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../AUCT_40_2026001.csv", "AUCT,2026-01-01 00:00,5.002\n")
    try:
        cli.parse_daily_zip(archive.getvalue(), "AUCT", "2026-01-01", "40", "2026")
    except cli.UnsafeError:
        pass
    else:
        raise AssertionError("zip path escape was accepted")

    rejected = (
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--limit", "999999999999", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--offset", "100001", "--json"],
        ["files", "--gauge", "AUCT", "--year", "9999999999", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-02-31", "--json"],
        ["readings", "--gauge", "auct", "--date", "2026-01-01", "--json"],
        ["readings", "--gauge", "../AU", "--date", "2026-01-01", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "100", "--json"],
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "00", "--json"],
        ["gauges", "--url", "https://evil.example/api/listGauges", "--json"],
        ["gauges", "--fixture", "/etc/passwd", "--json"],
        ["gauges", "--fixture", "../cli.py", "--json"],
    )
    for arguments in rejected:
        code, payload, stderr = invoke(arguments)
        require(code == 2 and payload["error"]["type"] == "invalid_input" and payload["results"] == [] and stderr == "", " ".join(arguments))


def check_provenance_contract() -> None:
    cli_path = Path(__file__).with_name("cli.py")
    cases = (
        ((*DATA_COMMAND,), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = subprocess.run(
            [sys.executable, str(cli_path), *arguments],
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
        "174,-37,175", "a,b,c,d", "nan,-37,175,-36", "174,-37,inf,-36",
        "175,-37,174,-36", "174,-36,175,-37", "-181,-37,175,-36",
        "174,-91,175,-36", "174,-37,181,-36", "174,-37,175,91", "174,-37,174,-36",
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


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        try:
            check_provenance_contract()
            run_parser_contracts()
        except (AssertionError, json.JSONDecodeError, KeyError) as exc:
            result["ok"] = False
            result["errors"].append(str(exc))
        else:
            result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "parser_fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
