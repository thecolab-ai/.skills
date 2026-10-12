#!/usr/bin/env python3
"""Deterministic repository contract test for osm-notes."""
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

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = Path(__file__).with_name("cli.py")
BBOX = "174.76,-36.86,174.78,-36.84"
DATA_COMMAND = (
    "notes",
    "--bbox",
    BBOX,
    "--limit",
    "2",
    "--fixture",
    "tests/fixtures/notes-positive.json",
    "--json",
)
FORBIDDEN_KEYS = {"uid", "user", "user_url", "html", "comment_url", "close_url", "reopen_url", "url"}


def run_cli(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def keys_of(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        for item in value.values():
            found.update(keys_of(item))
    elif isinstance(value, list):
        for item in value:
            found.update(keys_of(item))
    return found


def check_provenance_contract() -> None:
    cases = (
        ((*DATA_COMMAND,), 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        completed = run_cli(arguments)
        assert completed.returncode == expected_code, completed.stderr or completed.stdout
        assert not completed.stderr, completed.stderr
        payload = json.loads(completed.stdout)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"] == "OpenStreetMap contributors"
        assert meta["licence"] == "Open Database License (ODbL) 1.0"
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
            assert payload["results"][0]["id"] == 102
            assert FORBIDDEN_KEYS.isdisjoint(keys_of(payload))
            assert "synthetic-account" not in completed.stdout
            assert payload["meta"]["latest_data"] == "2026-02-04 05:06:07 UTC"

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


def notes_command(fixture: str, *extra: str) -> tuple[str, ...]:
    return ("notes", "--bbox", BBOX, "--limit", "2", "--fixture", fixture, *extra, "--json")


def check_fixture_cases() -> None:
    positive = run_cli(DATA_COMMAND)
    assert positive.returncode == 0, positive.stdout
    payload = json.loads(positive.stdout)
    assert [note["id"] for note in payload["results"]] == [102, 101]
    assert payload["results"][1]["date_closed"] == "2026-01-03 03:04:05 UTC"
    assert payload["results"][0]["note_url"] == "https://www.openstreetmap.org/note/102"
    assert payload["results"][1]["comments"][0]["text"] == "Synthetic anonymous note."

    limited = run_cli(
        ("notes", "--bbox", BBOX, "--limit", "1", "--fixture", "tests/fixtures/notes-positive.json", "--json")
    )
    assert limited.returncode == 0, limited.stdout
    assert [note["id"] for note in json.loads(limited.stdout)["results"]] == [102]

    empty = run_cli(notes_command("tests/fixtures/notes-empty.json"))
    assert empty.returncode == 0, empty.stdout
    empty_payload = json.loads(empty.stdout)
    assert empty_payload["results"] == []
    assert "latest_data" not in empty_payload["meta"]
    assert "error" not in empty_payload

    malformed = run_cli(notes_command("tests/fixtures/notes-malformed.json"))
    assert malformed.returncode == 6, malformed.stdout
    malformed_payload = json.loads(malformed.stdout)
    assert malformed_payload["results"] == []
    assert malformed_payload["error"]["type"] == "schema_failure"

    outside = run_cli(notes_command("tests/fixtures/notes-outside.json"))
    assert outside.returncode == 6, outside.stdout
    assert json.loads(outside.stdout)["error"]["type"] == "schema_failure"

    limited_rate = run_cli(notes_command("tests/fixtures/notes-http-429.json"))
    assert limited_rate.returncode == 4, limited_rate.stdout
    rate_payload = json.loads(limited_rate.stdout)
    assert rate_payload["error"]["type"] == "blocked"
    assert rate_payload["error"]["retry_after"] == "30"
    assert "HTTP 429" in rate_payload["error"]["message"]

    unavailable = run_cli(notes_command("tests/fixtures/notes-http-503.json"))
    assert unavailable.returncode == 5, unavailable.stdout
    unavailable_payload = json.loads(unavailable.stdout)
    assert unavailable_payload["error"]["type"] == "upstream_unavailable"
    assert "network error: HTTP 503" in unavailable_payload["error"]["message"]

    wide = run_cli(
        (
            "notes",
            "--bbox",
            "174.70,-36.90,174.80,-36.80",
            "--limit",
            "2",
            "--fixture",
            "tests/fixtures/notes-positive.json",
            "--json",
        )
    )
    assert wide.returncode == 2, wide.stdout
    assert json.loads(wide.stdout)["error"]["type"] == "invalid_input"

    history = run_cli(
        (
            "notes",
            "--bbox",
            BBOX,
            "--limit",
            "2",
            "--closed-days",
            "8",
            "--fixture",
            "tests/fixtures/notes-positive.json",
            "--json",
        )
    )
    assert history.returncode == 2, history.stdout

    geojson = run_cli(
        (
            "notes",
            "--bbox",
            BBOX,
            "--limit",
            "2",
            "--fixture",
            "tests/fixtures/notes-positive.json",
            "--format",
            "geojson",
        )
    )
    assert geojson.returncode == 0, geojson.stdout
    collection = json.loads(geojson.stdout)
    assert collection["type"] == "FeatureCollection"
    assert collection["features"][0]["geometry"]["coordinates"] == [174.77, -36.85]
    assert collection["meta"]["licence"] == "Open Database License (ODbL) 1.0"
    assert FORBIDDEN_KEYS.isdisjoint(keys_of(collection))

    source = CLI.read_text(encoding="utf-8")
    for forbidden in ("/comment.json", "/close.json", "/reopen.json", 'method="POST"', "method='POST'"):
        assert forbidden not in source, forbidden


def main() -> int:
    result = audit_skill(SKILL_DIR)
    if result["ok"]:
        check_provenance_contract()
        check_fixture_cases()
        result["checks"].extend(
            (
                "provenance",
                "json_errors",
                "cached_metadata",
                "spatial_contract",
                "positive_fixture",
                "empty_fixture",
                "malformed_fixture",
                "rate_limit_fixture",
                "upstream_unavailable_fixture",
                "bounds",
            )
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
