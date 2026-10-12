#!/usr/bin/env python3
"""Fixture parser checks and one bounded live probe of the Berlin WFS."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cli

CLI = Path(__file__).resolve().with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
EXPECTED_TYPES = {
    "ua_srgk:ca_fliessgeschwindigkeit_aussergewoehnlich",
    "ua_srgk:da_fliessgeschwindigkeit_extrem",
    "ua_srgk:ba_fliessgeschwindigkeit_selten",
    "ua_srgk:a_modellgebiete",
}


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def check_fixtures() -> None:
    areas, _counts = cli.parse_areas((FIXTURES / "area-neukoelln.xml").read_bytes(), cli.areas_url(1), 1)
    assert areas[0]["name"] == "Neukölln" and areas[0]["id"] == "1"
    assert "posList" not in json.dumps(areas)
    print("[PASS] fixture areas: Neukölln id 1 without velocity or polygon coordinates")
    types, attribution = cli.parse_types((FIXTURES / "capabilities.xml").read_bytes(), cli.capabilities_url())
    assert {row["type_name"] for row in types} == EXPECTED_TYPES
    assert attribution == cli.ATTRIBUTION
    print("[PASS] fixture types: four feature types and the CC BY 4.0 attribution")
    try:
        cli.parse_xml(b"", cli.SERVICE_ROOT)
    except cli.SkillError as exc:
        assert exc.code == 6
    else:
        raise AssertionError("empty body was accepted")
    print("[PASS] fixture malformed: empty body is a schema failure")
    empty, counts = cli.parse_areas((FIXTURES / "empty-collection.xml").read_bytes(), cli.areas_url(1), 1)
    assert empty == [] and counts["number_matched"] == 0
    print("[PASS] fixture empty: explicit zero match is not an outage")


def raise_completed(completed: subprocess.CompletedProcess[str], source_url: str) -> None:
    message = completed.stdout or completed.stderr or "command failed"
    code = completed.returncode or 6
    try:
        payload = json.loads(completed.stdout)
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            if isinstance(error.get("code"), int):
                code = error["code"]
    except json.JSONDecodeError:
        pass
    raise cli.SkillError(message, code, source_url)


def check_live() -> None:
    types_run = run_cli("types", "--json")
    if types_run.returncode != 0:
        raise_completed(types_run, cli.capabilities_url())
    types_payload = json.loads(types_run.stdout)
    names = {row["type_name"] for row in types_payload["results"]}
    if not EXPECTED_TYPES.issubset(names):
        raise cli.SkillError("live capabilities are missing a confirmed feature type", 6, cli.capabilities_url())
    model = next(row for row in types_payload["results"] if row["type_name"] == "ua_srgk:a_modellgebiete")
    if model["query"] != "areas" or model["default_crs"] != "EPSG:25833":
        raise cli.SkillError("model-area type is not queryable in EPSG:25833", 6, cli.capabilities_url())
    if any(row["query"] != "none" for row in types_payload["results"] if row["type_name"] in cli.VELOCITY_TYPES):
        raise cli.SkillError("velocity feature types were marked for download", 6, cli.capabilities_url())
    if types_payload["meta"].get("licence") != cli.LICENCE or types_payload["meta"].get("attribution") != cli.ATTRIBUTION:
        raise cli.SkillError("live licence or attribution does not match the confirmed statement", 4, cli.capabilities_url())
    print("[PASS] live types: four feature types, model areas only, CC BY 4.0 attribution")

    matched = cli.command_hits()
    if not isinstance(matched, int) or matched < 1:
        raise cli.SkillError("hits numberMatched is not a positive integer", 6, cli.hits_url())
    print(f"[PASS] live hits: numberMatched={matched}")

    areas_run = run_cli("areas", "--count", "1", "--json")
    if areas_run.returncode != 0:
        raise_completed(areas_run, cli.areas_url(1))
    areas_payload = json.loads(areas_run.stdout)
    if len(areas_payload["results"]) != 1:
        raise cli.SkillError("count=1 did not return one model area", 6, cli.areas_url(1))
    area = areas_payload["results"][0]
    if not str(area.get("name", "")).strip() or not str(area.get("id", "")).strip():
        raise cli.SkillError("model area name or id is empty", 6, cli.areas_url(1))
    if area.get("crs") != "EPSG:25833":
        raise cli.SkillError("model area CRS is not EPSG:25833", 6, cli.areas_url(1))
    if areas_payload["meta"].get("number_matched", 0) < 1:
        raise cli.SkillError("model-area number_matched is not positive", 6, cli.areas_url(1))
    if "posList" in areas_run.stdout or "fliessgeschwindigkeit" in areas_run.stdout:
        raise cli.SkillError("area response included geometry or a velocity layer", 6, cli.areas_url(1))
    print(f"[PASS] live areas: id {area['id']} name {area['name']}")


def main() -> int:
    try:
        check_fixtures()
    except (AssertionError, cli.SkillError, OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] fixture parser: {exc}")
        return 1
    try:
        check_live()
    except cli.SkillError as exc:
        if exc.code in (4, 5) and str(exc).startswith("network error"):
            print(f"[SKIP] live probe: {exc}")
            return 0
        print(f"[FAIL] live probe: {exc}")
        return 1
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] live probe: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
