#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cli

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

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DATA_COMMAND = ("layers", "--fixture", str(FIXTURES / "capabilities-layers.xml"))


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("cli.py")), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def check_provenance_contract() -> None:
    cases = (
        ((*DATA_COMMAND, "--json"), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = run_cli(list(arguments))
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
            assert meta["licence"].startswith("Datenlizenz Deutschland")
            assert meta["crs_axis_order"] == "latitude,longitude"
            assert [row["name"] for row in payload["results"]] == [
                "geschwindigkeit_agw",
                "ni_geschw_agw",
                "hh_geschw_agw",
            ]

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    assert "licence" not in meta and "latest_data" not in meta
    cached = provenance(
        "https://example.invalid/data", "Fixture publisher",
        licence="Fixture terms", latest_data="2026-09", retrieved_at="2026-10-01T01:02:03Z",
    )
    assert cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09"
    assert cached["retrieved_at"] == "2026-10-01T01:02:03Z"
    normalised = provenance(
        "https://example.invalid/data", "Fixture publisher",
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


def velocity_fixture(name: str, lat: str = "52", lon: str = "10") -> dict:
    completed = run_cli([
        "velocity", "--lat", lat, "--lon", lon,
        "--fixture", str(FIXTURES / name), "--json",
    ])
    assert not completed.stderr, completed.stderr
    return {"code": completed.returncode, "payload": json.loads(completed.stdout)}


def check_velocity_contract() -> None:
    parameter = cli.bbox_parameter(cli.point_bbox(52, 10))
    assert parameter == "51.9995,9.9995,52.0005,10.0005"
    assert parameter.split(",")[0] == "51.9995"
    assert parameter != "9.9995,51.9995,10.0005,52.0005"

    zero = velocity_fixture("featureinfo-zero.txt")
    assert zero["code"] == 0
    record = zero["payload"]["results"][0]
    assert record["state"] == "value"
    assert record["feature_type"] == "ni_geschw_agw"
    assert record["geschwindigkeit"] == 0
    assert record["geschwindigkeit_text"] == "0.0"
    assert record["no_data_reason"] is None
    assert record["crs_axis_order"] == "latitude,longitude"
    assert record["bbox"]["min_latitude"] == 51.9995
    assert record["width"] == 101 and record["height"] == 101
    assert record["i"] == 50 and record["j"] == 50

    positive = velocity_fixture("featureinfo-positive.txt", "50.110", "8.682")
    assert positive["code"] == 0
    measured = positive["payload"]["results"][0]
    assert measured["state"] == "value"
    assert measured["feature_type"] == "he_geschw_agw"
    assert measured["geschwindigkeit"] == 0.6899999976158142
    assert measured["geschwindigkeit_text"] == "0.6899999976158142"
    assert measured["geschwindigkeit"] != 0

    missing = velocity_fixture("featureinfo-no-feature.txt", "47.5", "10")
    assert missing["code"] == 0
    absent = missing["payload"]["results"][0]
    assert absent["state"] == "no_data"
    assert absent["no_data_reason"] == "no_feature"
    assert absent["geschwindigkeit"] is None
    assert absent["feature_type"] is None
    assert absent["geschwindigkeit"] != 0

    sentinel = velocity_fixture("featureinfo-sentinel.txt", "50.937", "6.960")
    assert sentinel["code"] == 0
    masked = sentinel["payload"]["results"][0]
    assert masked["state"] == "no_data"
    assert masked["no_data_reason"] == "sentinel"
    assert masked["feature_type"] == "nw_geschw_agw"
    assert masked["geschwindigkeit"] is None
    assert masked["source_token"] == "-9999.0"
    assert masked["geschwindigkeit"] != -9999

    for name in ("featureinfo-empty.txt", "featureinfo-malformed.txt"):
        failed = velocity_fixture(name)
        assert failed["code"] == 6, name
        assert failed["payload"]["results"] == []
        assert failed["payload"]["error"]["type"] == "schema_failure"

    rejected = run_cli(["velocity", "--lat", "91", "--lon", "10", "--json"])
    assert rejected.returncode == 2 and not rejected.stderr
    assert json.loads(rejected.stdout)["error"]["type"] == "invalid_input"
    non_numeric = run_cli(["velocity", "--lat", "nan", "--lon", "10", "--json"])
    assert non_numeric.returncode == 2
    assert json.loads(non_numeric.stdout)["error"]["type"] == "invalid_input"

    swapped = (FIXTURES / "capabilities-layers.xml").read_text(encoding="utf-8").replace(
        'CRS="EPSG:4326" minx="48.76108728003403" miny="5.379125554394207"',
        'CRS="EPSG:4326" minx="5.379125554394207" miny="48.76108728003403"',
    )
    try:
        cli.parse_capabilities(swapped.encode("utf-8"))
    except cli.SkillError as exc:
        assert exc.code == 6
        assert "longitude-first" in str(exc)
    else:
        raise AssertionError("longitude-first EPSG:4326 box was accepted")

    extra = "".join(
        f'<Layer queryable="1"><Name>layer_{index}</Name><Title>t</Title></Layer>'
        for index in range(cli.MAX_NAMED_LAYERS)
    )
    overflow = (FIXTURES / "capabilities-layers.xml").read_text(encoding="utf-8").replace(
        "</Capability>", extra + "</Capability>", 1
    )
    try:
        cli.parse_capabilities(overflow.encode("utf-8"))
    except cli.SkillError as exc:
        assert exc.code == 7
    else:
        raise AssertionError("layer bound was not enforced")


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_velocity_contract()
        result["checks"].extend((
            "provenance", "json_errors", "cached_metadata", "spatial_contract",
            "axis_order", "zero_versus_no_data", "bounds",
        ))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
