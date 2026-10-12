#!/usr/bin/env python3
"""Deterministic command, parser, bounds, and outage checks."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import cli

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))
from contract_test import audit_skill  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CLI = Path(__file__).resolve().with_name("cli.py")


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def expect_error(body: bytes, code: int) -> None:
    try:
        cli.parse_types(body, cli.SERVICE_ROOT)
    except cli.SkillError as exc:
        assert exc.code == code, exc
        return
    raise AssertionError("parser accepted a document that must fail")


def check_fixtures() -> None:
    types, attribution = cli.parse_types(load("capabilities.xml"), cli.capabilities_url())
    assert attribution == cli.ATTRIBUTION
    names = [row["type_name"] for row in types]
    assert names == [
        "ua_srgk:ca_fliessgeschwindigkeit_aussergewoehnlich",
        "ua_srgk:da_fliessgeschwindigkeit_extrem",
        "ua_srgk:ba_fliessgeschwindigkeit_selten",
        "ua_srgk:a_modellgebiete",
    ]
    assert types[-1]["query"] == "areas"
    assert all(row["query"] == "none" for row in types[:-1])
    assert all(row["default_crs"] == "EPSG:25833" for row in types)

    areas, counts = cli.parse_areas(load("area-neukoelln.xml"), cli.areas_url(1), 1)
    assert counts == {"number_matched": 8, "number_returned": 1, "truncated": True}
    assert areas[0]["name"] == "Neukölln"
    assert areas[0]["id"] == "1"
    assert areas[0]["gml_id"] == "a_modellgebiete.1"
    assert areas[0]["crs"] == "EPSG:25833"
    assert areas[0]["envelope"]["lower_easting"] == "387468.9392"
    assert areas[0]["envelope"]["unit"] == "metre"
    encoded = json.dumps(areas)
    assert "posList" not in encoded and "0 0 1 1" not in encoded

    empty, empty_counts = cli.parse_areas(load("empty-collection.xml"), cli.areas_url(1), 1)
    assert empty == [] and empty_counts["number_matched"] == 0
    assert cli.parse_hits(load("hits.xml"), cli.hits_url()) == 8

    expect_error(b"", 6)
    expect_error(b"<wfs:FeatureCollection>", 6)
    expect_error(b"<!DOCTYPE html><html></html>", 4)
    expect_error(load("exception-report.xml"), 6)
    try:
        cli.parse_areas(load("hits.xml"), cli.areas_url(1), 1)
    except cli.SkillError as exc:
        assert exc.code == 6
    else:
        raise AssertionError("hits document was treated as an empty area page")
    try:
        cli.parse_areas(load("area-neukoelln.xml"), cli.areas_url(1), 0)
    except cli.SkillError as exc:
        assert exc.code == 2
    else:
        raise AssertionError("count 0 was accepted")


def check_bounds_and_outage() -> None:
    areas = cli.areas_url(1)
    query = parse_qs(urlsplit(areas).query)
    assert query["typeNames"] == ["ua_srgk:a_modellgebiete"]
    assert query["count"] == ["1"]
    assert "resultType" not in query
    assert "fliessgeschwindigkeit" not in areas
    assert urlsplit(cli.hits_url()).hostname == "gdi.berlin.de"
    assert "resultType=hits" in cli.hits_url() or parse_qs(urlsplit(cli.hits_url()).query)["resultType"] == ["hits"]

    for count in (0, 9, -1):
        completed = run_cli("areas", "--count", str(count), "--json")
        assert completed.returncode == 2, completed.stdout
        assert not completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["results"] == []
        assert payload["error"]["code"] == 2
        assert payload["error"]["type"] == "invalid_input"

    invalid = run_cli("--thecolab-invalid-option", "--json")
    assert invalid.returncode == 2 and not invalid.stderr
    invalid_payload = json.loads(invalid.stdout)
    assert invalid_payload["error"]["type"] == "invalid_input"
    assert invalid_payload["meta"]["retrieved_at"].endswith("Z")

    def refuse(*_args, **_kwargs):
        raise AssertionError("bounds check must not call the network")

    with patch.object(cli.nzfetch, "fetch_bytes", side_effect=refuse):
        try:
            cli.command_areas(9)
        except cli.SkillError as exc:
            assert exc.code == 2
        else:
            raise AssertionError("count 9 reached the network")

    with patch.object(cli.nzfetch, "fetch_bytes", side_effect=cli.nzfetch.FetchError("timed out")):
        try:
            cli.command_types()
        except cli.SkillError as exc:
            assert exc.code == 5 and str(exc).startswith("network error:")
        else:
            raise AssertionError("outage was treated as success")

    with patch.object(
        cli.nzfetch,
        "fetch_bytes",
        side_effect=cli.nzfetch.RateLimited("slow down", retry_after="30"),
    ):
        try:
            cli.command_areas(1)
        except cli.SkillError as exc:
            envelope = cli.error_envelope(exc.code, str(exc), cli.provenance(exc.source_url, cli.PUBLISHER), retry_after=exc.retry_after)
            assert envelope["error"]["code"] == 4
            assert envelope["error"]["retry_after"] == "30"
            assert envelope["results"] == []
        else:
            raise AssertionError("rate limit was treated as success")

    with patch.object(cli.nzfetch, "fetch_bytes", side_effect=cli.nzfetch.ResponseTooLarge("too big")):
        try:
            cli.command_areas(8)
        except cli.SkillError as exc:
            assert exc.code == 7 and "network error" not in str(exc)
        else:
            raise AssertionError("oversized response was treated as success")


def check_provenance() -> None:
    meta = cli.provenance("https://example.invalid/data", "Fixture publisher")
    assert "licence" not in meta and "latest_data" not in meta
    cached = cli.provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    assert cached["retrieved_at"] == "2026-10-01T01:02:03Z"
    normalised = cli.provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    assert normalised["retrieved_at"] == "2026-10-01T01:02:03Z"
    try:
        cli.provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    retrieved = datetime.fromisoformat(cached["retrieved_at"].replace("Z", "+00:00"))
    assert retrieved.utcoffset() == timedelta(0)


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["ok"]:
        return 1
    check_fixtures()
    check_bounds_and_outage()
    check_provenance()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
