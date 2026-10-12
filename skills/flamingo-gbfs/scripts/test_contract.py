#!/usr/bin/env python3
"""Deterministic repository and parser contract for Flamingo GBFS."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
import sys

sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

DATA_COMMAND = ("discovery", "--fixture", "discovery-ok", "--json")


def invoke(arguments: list[str]) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    text = stdout.getvalue()
    payload = json.loads(text) if text and ("--json" in arguments or "geojson" in arguments) else {}
    return code, payload, stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_provenance_contract() -> None:
    cases = (
        (DATA_COMMAND, 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        code, payload, stderr = invoke(list(arguments))
        require(code == expected_code, f"{arguments} exited {code}: {stderr}")
        require(stderr == "", stderr)
        meta = payload["meta"]
        require(bool(meta["source_url"]) and meta["publisher"] == "Flamingo", "provenance missing")
        require(meta["retrieved_at"].endswith("Z"), "retrieved_at was not UTC")
        retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
        require(retrieved.utcoffset() == timedelta(0), "retrieved_at was not UTC")
        require(isinstance(payload["results"], list), "results was not a list")
        if expected_code:
            require(payload["results"] == [], "error result was not empty")
            require(payload["error"]["code"] == expected_code, "error code mismatch")
            require(payload["error"]["type"] == "invalid_input", "error type mismatch")
        else:
            require("error" not in payload, "success payload contained error")

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    require("licence" not in meta and "latest_data" not in meta, "unknown licence was invented")
    cached = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    require(cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09", "cached facts changed")
    require(cached["retrieved_at"] == "2026-10-01T01:02:03Z", "cached retrieval time changed")
    normalised = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    require(normalised["retrieved_at"] == cached["retrieved_at"], "offset was not normalised to Z")
    try:
        provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    require(result_envelope([], cached)["results"] == [], "empty envelope dropped results")
    failure = error_envelope(4, "rate-limited", meta, retry_after="60")
    require(failure["error"]["type"] == "blocked" and failure["error"]["retry_after"] == "60", "retry_after dropped")

    require(parse_bbox("174,-37,175,-36") == (174.0, -37.0, 175.0, -36.0), "bbox parser changed")
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
    require(args.bbox == (174.0, -37.0, 175.0, -36.0) and args.format == "geojson", "spatial args changed")
    require(parser.parse_args(["--bbox=-180,-90,180,90"]).bbox == (-180.0, -90.0, 180.0, 90.0), "negative bbox split")
    collection = geojson_envelope([], meta)
    require(collection == {"type": "FeatureCollection", "features": [], "meta": meta}, "geojson envelope changed")


def check_parser_contracts() -> None:
    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "", stderr)
    names = [record["name"] for record in payload["results"]]
    require(names == ["system_information", "vehicle_status"], names)
    require(payload["results"][1]["url"] == cli.VEHICLE_URL, "vehicle feed URL drifted")
    require(all(record["url"].startswith("https://data.rideflamingo.com/gbfs/3/auckland/") for record in payload["results"]), "off-host feed was kept")
    require("licence" not in payload["meta"], "discovery invented a licence")
    require(payload["meta"]["latest_data"] == "2025-02-15T10:17:01+00:00", "discovery timestamp was rewritten")
    require(any("refused feed elsewhere" in item for item in payload["warnings"]), "off-host feed was not refused")
    require(any("refused feed other_city" in item for item in payload["warnings"]), "other city feed was accepted")
    require("fixture: discovery-ok" in payload["warnings"][0], "fixture was presented as live")

    code, payload, _stderr = invoke(["discovery", "--fixture", "discovery-empty", "--json"])
    require(code == 0 and payload["results"] == [], "empty feed list was not an empty success")
    require("error" not in payload, "empty feed list was an error")

    code, payload, _stderr = invoke(["system", "--fixture", "system-ok", "--json"])
    require(code == 0 and payload["results"][0]["license_id"] == "CC-BY-4.0", "license_id dropped")
    require(payload["meta"]["licence"] == "CC BY 4.0", "licence was not the stated token")
    require(payload["results"][0]["name"] == "Flamingo", "localised name was dropped")
    require(payload["results"][0]["timezone"] == "Etc/UTC", "timezone was relabelled")
    require(payload["meta"]["latest_data"] == "2026-10-11T18:12:33+00:00", "system timestamp changed")

    code, payload, stderr = invoke(["system", "--fixture", "system-no-licence", "--json"])
    require(code == 6 and stderr == "" and payload["error"]["type"] == "schema_failure", "missing licence was a success")
    require("license_id" in payload["error"]["message"], payload["error"]["message"])

    code, payload, _stderr = invoke(["vehicles", "--fixture", "vehicles-ok", "--limit", "1", "--json"])
    require(code == 0 and len(payload["results"]) == 1, "limit was ignored")
    record = payload["results"][0]
    require(record["vehicle_id"] == "scooter-a", record["vehicle_id"])
    require(record["current_range_meters"] == 12000, "range changed units")
    require("rental_uris" not in record and "route" not in record, "trajectory or deep link was emitted")
    require(payload["meta"]["latest_data"] == "2026-10-11T18:12:34+00:00", "vehicle snapshot time changed")
    require("licence" not in payload["meta"], "vehicle file invented a licence")
    require(any("source vehicle_count: 3" in item for item in payload["warnings"]), payload["warnings"])
    require(any("suppressed 1 duplicate" in item for item in payload["warnings"]), "duplicate became a track")
    require(any("not return trajectories" in item for item in payload["warnings"]), "trajectory warning missing")

    code, payload, _stderr = invoke(
        ["vehicles", "--fixture", "vehicles-ok", "--bbox", "174.6,-37.0,174.9,-36.7", "--json"]
    )
    kept = [item["vehicle_id"] for item in payload["results"]]
    require(code == 0 and kept == ["scooter-a", "scooter-c"], kept)
    scooter_c = payload["results"][1]
    require("current_range_meters" not in scooter_c, "negative range was coerced")
    require("last_reported" not in scooter_c, "naive timestamp was labelled as UTC")
    require(all("outside WGS84" not in item for item in payload["warnings"]), payload["warnings"])

    code, payload, _stderr = invoke(["vehicles", "--fixture", "vehicles-empty", "--json"])
    require(code == 0 and payload["results"] == [], "empty fleet was not an empty success")
    require(any("source vehicle_count: 0" in item for item in payload["warnings"]), "empty count was invented")
    require("error" not in payload, "empty fleet was an outage")

    code, payload, _stderr = invoke(["vehicles", "--fixture", "vehicles-version-2", "--json"])
    require(code == 6 and "3.0" in payload["error"]["message"], "version 2 was accepted")

    code, payload, stderr = invoke(["vehicles", "--fixture", "transport-malformed", "--json"])
    require(code == 6 and stderr == "" and payload["error"]["type"] == "schema_failure", "malformed JSON was not typed")
    require("Traceback" not in payload["error"]["message"], "malformed JSON traced")

    code, payload, _stderr = invoke(["vehicles", "--fixture", "transport-nan", "--json"])
    require(code == 6 and payload["error"]["type"] == "schema_failure", "NaN coordinates were accepted")

    code, payload, _stderr = invoke(["vehicles", "--fixture", "transport-deep", "--json"])
    require(code == 6 and "nesting depth" in payload["error"]["message"], "deep JSON was not typed")

    code, payload, _stderr = invoke(["vehicles", "--fixture", "transport-rate-limit", "--json"])
    require(code == 4 and payload["results"] == [], "rate limit looked empty")
    require(payload["error"]["type"] == "blocked" and payload["error"]["retry_after"] == "30", payload["error"])

    code, payload, _stderr = invoke(["vehicles", "--fixture", "transport-unavailable", "--json"])
    require(code == 5 and "503" in payload["error"]["message"], "503 was not unavailable")

    code, payload, _stderr = invoke(["discovery", "--fixture", "transport-timeout", "--json"])
    require(code == 5 and "timed out" in payload["error"]["message"], "timeout was not unavailable")

    code, payload, _stderr = invoke(["system", "--fixture", "transport-off-host", "--json"])
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host redirect was followed")

    code, payload, _stderr = invoke(["vehicles", "--limit", "0", "--json"])
    require(code == 2 and payload["error"]["type"] == "invalid_input", "limit 0 was accepted")
    code, payload, _stderr = invoke(["vehicles", "--limit", "101", "--json"])
    require(code == 2 and payload["error"]["type"] == "invalid_input", "limit 101 was accepted")
    code, payload, _stderr = invoke(["vehicles", "--vehicle-id", "../secret", "--json"])
    require(code == 2, "unsafe vehicle id was accepted")
    code, _payload, stderr = invoke(["vehicles", "--bbox", "175,-36,174,-37", "--json"])
    require(code == 2 and "Traceback" not in stderr, "reversed bbox traced")

    code, payload, _stderr = invoke(["vehicles", "--fixture", "vehicles-ok", "--format", "geojson", "--limit", "1"])
    require(code == 0 and payload["type"] == "FeatureCollection", "geojson type changed")
    require(payload["features"][0]["geometry"]["coordinates"] == [174.76, -36.85], "geojson axis order changed")
    require("route" not in payload["features"][0]["properties"], "geojson kept a route")
    require(payload["meta"]["publisher"] == "Flamingo", "geojson provenance missing")

    try:
        cli.parse_vehicles({"vehicles": [{}] * (cli.MAX_VEHICLES + 1)}, 60, limit=1, bbox=None, vehicle_id=None)
    except cli.SchemaError as exc:
        require(str(cli.MAX_VEHICLES) in str(exc), str(exc))
    else:
        raise AssertionError("oversized vehicle list was accepted")
    try:
        cli.gbfs_document({"version": "3.0", "ttl": True, "data": {}})
    except cli.SchemaError:
        pass
    else:
        raise AssertionError("boolean ttl was accepted")


def check_ttl_cache() -> None:
    fixture = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "discovery-ok.json").read_text(encoding="utf-8"))
    raw = json.dumps(fixture["body"]).encode("utf-8")
    calls = {"n": 0}

    def fake(url: str, **kwargs: object) -> tuple[bytes, str, str]:
        calls["n"] += 1
        require(kwargs.get("timeout") == 10, "timeout was not 10 seconds")
        require(kwargs.get("allowed_hosts") == cli.ALLOWED_HOSTS, "host allowlist widened")
        require(kwargs.get("max_bytes") == cli.MAX_RESPONSE_BYTES, "byte cap changed")
        require(kwargs.get("browser_headers") is False, "browser header set was enabled")
        headers = kwargs.get("headers")
        require(isinstance(headers, dict) and headers.get("User-Agent") == cli.USER_AGENT, "User-Agent changed")
        require(url == cli.GBFS_URL, url)
        return raw, "application/json", url

    original = cli.nzfetch.fetch_bytes
    cli.nzfetch.fetch_bytes = fake
    previous_cache = cli.CACHE_DIR
    temporary = tempfile.TemporaryDirectory()
    cli.CACHE_DIR = Path(temporary.name)
    try:
        code, payload, stderr = invoke(["discovery", "--json"])
        require(code == 0 and stderr == "" and calls["n"] == 1, stderr or str(code))
        code, again, _stderr = invoke(["discovery", "--json"])
        require(code == 0 and calls["n"] == 1, "ttl cache refetched the same feed")
        require(again["meta"]["retrieved_at"] == payload["meta"]["retrieved_at"], "cache minted a new retrieval time")
        require(any("cached within feed ttl" in item for item in again["warnings"]), "cache hit was unmarked")

        cli.store_cache(cli.GBFS_URL, fixture["body"] and json.dumps(fixture["body"]), "2020-01-01T00:00:00Z", 60)
        code, _payload, _stderr = invoke(["discovery", "--json"])
        require(code == 0 and calls["n"] == 2, "stale ttl cache suppressed a refresh")

        zero = json.loads(json.dumps(fixture["body"]))
        zero["ttl"] = 0
        raw_box = {"raw": json.dumps(zero).encode("utf-8")}

        def fake_zero(url: str, **kwargs: object) -> tuple[bytes, str, str]:
            calls["n"] += 1
            return raw_box["raw"], "application/json", url

        cli.cache_path(cli.GBFS_URL).unlink(missing_ok=True)
        cli.nzfetch.fetch_bytes = fake_zero
        code, _payload, _stderr = invoke(["discovery", "--json"])
        code, _payload, _stderr = invoke(["discovery", "--json"])
        require(calls["n"] == 4, "ttl 0 was cached and polled less than once per call")
    finally:
        cli.nzfetch.fetch_bytes = original
        cli.CACHE_DIR = previous_cache
        temporary.cleanup()


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_parser_contracts()
        check_ttl_cache()
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "gbfs_fixtures", "ttl_cache"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
