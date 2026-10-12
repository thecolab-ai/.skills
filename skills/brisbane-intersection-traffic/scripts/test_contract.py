#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
import argparse
import json
import subprocess
import sys
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

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DATA_COMMAND = ("volumes", "--limit", "1", "--fixture", str(FIXTURES / "volumes-positive.json"))


def check_provenance_contract() -> None:
    cli = Path(__file__).with_name("cli.py")
    cases = (
        ((*DATA_COMMAND, "--json"), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = subprocess.run(
            [sys.executable, str(cli), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert completed.returncode == expected_code, completed.stderr
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

    # Synthetic metadata tests do not claim a live source or a verified licence.
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


def run_cli(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("cli.py")), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def check_source_fixtures() -> None:
    import cli

    positive = run_cli((*DATA_COMMAND, "--json"))
    assert positive.returncode == 0, positive.stderr
    payload = json.loads(positive.stdout)
    row = payload["results"][0]
    assert row["tsc"] == "757" and row["lane"] == "SA-267"
    assert row["ds1"] == "3" and row["ds3"] is None
    assert payload["meta"]["licence"] == "CC BY 4.0"
    assert payload["meta"]["latest_data"] == "2026-10-11T18:09:00+00:00"
    assert payload["meta"]["total_count"] == 2

    empty = run_cli(("volumes", "--limit", "1", "--fixture", str(FIXTURES / "volumes-empty.json"), "--json"))
    empty_payload = json.loads(empty.stdout)
    assert empty.returncode == 0 and empty_payload["results"] == []
    assert "latest_data" not in empty_payload["meta"]
    assert empty_payload["meta"]["total_count"] == 0

    malformed = run_cli(("volumes", "--limit", "1", "--fixture", str(FIXTURES / "malformed.json"), "--json"))
    assert malformed.returncode == 6 and json.loads(malformed.stdout)["error"]["type"] == "schema_failure"

    limited = run_cli(("volumes", "--limit", "0", "--fixture", str(FIXTURES / "missing.json"), "--json"))
    assert limited.returncode == 2 and limited.stderr == ""
    assert json.loads(limited.stdout)["error"]["type"] == "invalid_input"

    rate = run_cli(("signals", "--limit", "1", "--fixture", str(FIXTURES / "http-429.json"), "--json"))
    rate_payload = json.loads(rate.stdout)
    assert rate.returncode == 4 and rate_payload["error"]["retry_after"] == "30"
    assert "traffic-management-signal-locations" in rate_payload["meta"]["source_url"]

    unavailable = run_cli(("volumes", "--limit", "1", "--fixture", str(FIXTURES / "http-503.json"), "--json"))
    assert unavailable.returncode == 5 and json.loads(unavailable.stdout)["error"]["type"] == "upstream_unavailable"

    signal = run_cli(("signals", "--limit", "1", "--fixture", str(FIXTURES / "signals-positive.json"), "--format", "geojson"))
    collection = json.loads(signal.stdout)
    assert signal.returncode == 0 and collection["features"][0]["geometry"]["coordinates"] == [153.16, -27.44]
    mismatch = run_cli(("signals", "--limit", "1", "--fixture", str(FIXTURES / "signals-mismatch.json"), "--json"))
    assert mismatch.returncode == 6

    assert cli.volume_where("757", "SA-267") == 'tsc="757" and lane="SA-267"'
    assert cli.signal_where(None, (153.15, -27.45, 153.17, -27.43)) == "in_bbox(geo_point_2d,-27.45,153.15,-27.43,153.17)"
    try:
        cli.check_public_url("https://off-allowlist.invalid/records", redirect=True)
    except cli.SkillError as exc:
        assert exc.code == 4
    else:
        raise AssertionError("off-host redirect accepted")
    cli.check_public_url(
        "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/traffic-data-at-intersection/records?limit=1",
        redirect=False,
    )


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_source_fixtures()
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "source_fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
