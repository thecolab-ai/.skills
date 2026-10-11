#!/usr/bin/env python3
"""Deterministic repository and parser contract for Auckland geological units."""
from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
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

DATA_COMMAND = (
    "units",
    "--bbox",
    "174.76,-36.86,174.78,-36.84",
    "--limit",
    "1",
    "--fixture",
    "units-positive",
    "--json",
)
BBOX = ["units", "--bbox", "174.76,-36.86,174.78,-36.84", "--limit", "1"]


def forbid_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("contract test attempted a network fetch")


def invoke(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def payload_of(stdout: str) -> dict:
    return json.loads(stdout)


def check_provenance_contract() -> None:
    code, stdout, stderr = invoke(list(DATA_COMMAND))
    payload = payload_of(stdout)
    require(code == 0 and stderr == "", stderr)
    meta = payload["meta"]
    require(meta["source_url"].startswith("https://data.gns.cri.nz/webmaps/gns/wfs?"), meta["source_url"])
    require("typeNames=gns%3ANZL-Urban_Auckland_geological_units" in meta["source_url"], meta["source_url"])
    require("Blenheim" not in meta["source_url"] and "Christchurch" not in meta["source_url"], meta["source_url"])
    require("count=1" in meta["source_url"] and "srsName=urn%3Aogc%3Adef%3Acrs%3AOGC%3A1.3%3ACRS84" in meta["source_url"], meta["source_url"])
    require(meta["publisher"] == "GNS Science", meta["publisher"])
    require(meta["licence"] == "Creative Commons Attribution 3.0 New Zealand (CC-BY 3.0)", meta.get("licence"))
    require("latest_data" not in meta, "response timeStamp was treated as a map revision")
    require(meta["retrieved_at"].endswith("Z"), meta["retrieved_at"])
    retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
    require(retrieved.utcoffset() == timedelta(0), "retrieved_at was not UTC")
    require(isinstance(payload["results"], list) and payload["results"], "positive fixture was empty")
    require("error" not in payload, "success payload contained error")

    code, stdout, stderr = invoke(["--thecolab-invalid-option", "--json"])
    payload = payload_of(stdout)
    require(code == 2 and stderr == "", stderr)
    require(payload["results"] == [] and payload["error"]["type"] == "invalid_input", payload)
    require(payload["error"]["code"] == 2, payload["error"])

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
    require(normalised["retrieved_at"] == "2026-10-01T01:02:03Z", "offset was not normalised to Z")
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
    for invalid in (
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
    ):
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
    code, stdout, stderr = invoke(list(DATA_COMMAND))
    payload = payload_of(stdout)
    require(code == 0 and stderr == "", stderr)
    record = payload["results"][0]
    require(record["unit_code"] == "FIX", record["unit_code"])
    require(record["strat_unit"] == "Fixture Conglomerate", record["strat_unit"])
    require(record["descriptio"] == "Synthetic pebble description for the parser.", "source field was renamed")
    require(record["area"] == 1000.0 and record["perimeter"] == 400.0, "area or perimeter was converted")
    require(record["scale"] == 50000 and record["strat_age"] == "Mi", record)
    require(record["geometry"]["type"] == "MultiPolygon", record["geometry"])
    require(record["geometry"]["coordinates"][0][0][0] == [174.77, -36.85], "geojson axis order changed")
    require(payload["page"] == {"matched": 3, "returned": 1, "limit": 1, "truncated": True}, payload["page"])
    require(any(item.startswith("fixture: units-positive") for item in payload["warnings"]), payload["warnings"])
    require(any("does not page" in item for item in payload["warnings"]), payload["warnings"])
    require("latest_data" not in payload["meta"], payload["meta"])

    code, stdout, stderr = invoke(
        ["units", "--bbox=-180,-90,180,90", "--limit", "1", "--fixture", "units-positive", "--format", "geojson"]
    )
    payload = payload_of(stdout)
    require(code == 0 and stderr == "", stderr)
    require(payload["type"] == "FeatureCollection" and payload["features"], payload.get("type"))
    require(payload["features"][0]["geometry"]["coordinates"][0][0][0] == [174.77, -36.85], "geojson was not longitude, latitude")
    require(payload["meta"]["licence"].startswith("Creative Commons Attribution 3.0 New Zealand"), payload["meta"])
    require("error" not in payload, payload)

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-positive"])
    require(code == 0 and stderr == "", stderr)
    require("FIX | Fixture Conglomerate | age Mi | scale 50000" in stdout, stdout)
    require("174.77" not in stdout, "human output dumped coordinates")
    require("Attribute GNS Science" in stdout, stdout)

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-empty", "--json"])
    payload = payload_of(stdout)
    require(code == 0 and stderr == "", stderr)
    require(payload["results"] == [] and payload["page"]["matched"] == 0, payload)
    require("error" not in payload, "empty intersection was reported as an error")
    require(any("fixture: units-empty" in item for item in payload["warnings"]), payload["warnings"])

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-malformed", "--json"])
    payload = payload_of(stdout)
    require(code == 6 and stderr == "", stderr)
    require(payload["error"]["type"] == "schema_failure" and payload["results"] == [], payload)
    require("malformed JSON" in payload["error"]["message"], payload["error"]["message"])

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-nztm", "--json"])
    payload = payload_of(stdout)
    require(code == 6 and stderr == "", stderr)
    require("WGS84" in payload["error"]["message"], payload["error"]["message"])
    require("1750000" not in stdout, "projected coordinates were emitted")

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-over-limit", "--json"])
    payload = payload_of(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", payload)
    require("more features than the requested count" in payload["error"]["message"], payload["error"])
    require(payload["results"] == [], payload["results"])

    code, stdout, stderr = invoke([*BBOX, "--fixture", "units-exception", "--json"])
    payload = payload_of(stdout)
    require(code == 6 and stderr == "", stderr)
    require("InvalidParameterValue" in payload["error"]["message"], payload["error"]["message"])
    require("Traceback" not in stdout and "Traceback" not in stderr, stderr)

    code, stdout, stderr = invoke([*BBOX, "--fixture", "transport-429", "--json"])
    payload = payload_of(stdout)
    require(code == 4 and stderr == "", stderr)
    require(payload["error"]["type"] == "blocked" and payload["error"]["retry_after"] == "30", payload["error"])
    require("http 429" in payload["error"]["message"], payload["error"]["message"])
    require(payload["results"] == [], payload["results"])

    code, stdout, stderr = invoke([*BBOX, "--fixture", "transport-503", "--json"])
    payload = payload_of(stdout)
    require(code == 5 and payload["error"]["type"] == "upstream_unavailable", payload)
    require("http 503" in payload["error"]["message"], payload["error"]["message"])
    require(payload["results"] == [], payload["results"])

    code, stdout, stderr = invoke([*BBOX, "--fixture", "transport-off-host", "--json"])
    payload = payload_of(stdout)
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", payload)
    require(payload["results"] == [], "off-host redirect returned features")
    require("off-host.invalid" not in stdout, stdout)

    code, stdout, stderr = invoke([*BBOX, "--fixture", "transport-truncated", "--json"])
    payload = payload_of(stdout)
    require(code == 5 and "524288" in payload["error"]["message"], payload)
    require("FeatureCollection" not in stdout, "truncated JSON was parsed as a map")

    code, stdout, stderr = invoke([*BBOX, "--fixture", "transport-timeout", "--json"])
    payload = payload_of(stdout)
    require(code == 5 and stderr == "", stderr)
    require("timed out" in payload["error"]["message"], payload["error"]["message"])

    code, stdout, stderr = invoke(["units", "--bbox", "10,10,12,11", "--limit", "6", "--json"])
    payload = payload_of(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", payload)
    require("--limit" in payload["error"]["message"], payload["error"]["message"])

    code, stdout, stderr = invoke(["units", "--bbox", "175,-37,174,-36", "--limit", "1", "--fixture", "missing-fixture", "--json"])
    payload = payload_of(stdout)
    require(code == 2 and "minLon,minLat,maxLon,maxLat" in payload["error"]["message"], payload["error"])
    require("missing-fixture" not in payload["error"]["message"], "invalid bbox reached fixture loading")

    code, stdout, _stderr = invoke([*BBOX, "--fixture", "does-not-exist", "--json"])
    payload = payload_of(stdout)
    require(code == 2 and payload["error"]["message"] == "unknown fixture: does-not-exist", payload["error"])

    separated = ["units", "--bbox", "174.10,-37.20,174.20,-37.10", "--limit", "1", "--fixture", "units-positive", "--json"]
    code, stdout, _stderr = invoke(separated)
    payload = payload_of(stdout)
    require(code == 6 and "does not intersect" in payload["error"]["message"], payload["error"])


def main() -> int:
    cli.live_fetch = forbid_network
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_parser_contracts()
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
