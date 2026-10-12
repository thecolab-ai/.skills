#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
import argparse
import json
import os
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

import smoke_test  # noqa: E402

DATA_COMMAND = ("table", "122777", "--json")


def run_checked(arguments: tuple[str, ...], *, fixture: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("STATSNZ_GEOGRAPHIC_TABLES_FIXTURE", None)
    if fixture:
        env["STATSNZ_GEOGRAPHIC_TABLES_FIXTURE"] = fixture
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("cli.py")), *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
    )


def check_provenance_contract() -> None:
    cases = (
        (DATA_COMMAND, 0, "positive"),
        (("--thecolab-invalid-option", "--json"), 2, None),
    )
    for arguments, expected_code, fixture in cases:
        completed = run_checked(arguments, fixture=fixture)
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
            assert payload["meta"]["licence"] == "Creative Commons Attribution 4.0 International"
            assert payload["meta"]["latest_data"] == "2026-03-29T20:36:31.056278Z"
            assert "created_by" not in completed.stdout

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


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        try:
            check_provenance_contract()
            smoke_test.run_fixture_checks()
        except SystemExit as exc:
            result["ok"] = False
            result["errors"].append(f"fixture checks failed with exit {exc.code}")
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(str(exc))
        else:
            result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "fixtures_http"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
