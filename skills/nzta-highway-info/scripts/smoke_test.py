#!/usr/bin/env python3
"""Deterministic parser checks plus bounded, outage-aware live probes."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURES = SKILL_DIR / "tests" / "fixtures"

spec = importlib.util.spec_from_file_location("nzta_highway_info_smoke_cli", CLI)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

results: list[bool | None] = []


def report(kind: str, name: str, status: str, detail: str = "") -> bool | None:
    prefix = f"[{status}] {kind}" if status == "PASS" else f"[{status}]"
    print(f"{prefix} {name}")
    if detail:
        print(f"  {detail}")
    value: bool | None = True if status == "PASS" else None if status == "SKIP" else False
    results.append(value)
    return value


def fixture_check(name: str, check: Callable[[], None]) -> None:
    try:
        check()
    except Exception as exc:
        report("fixture", name, "FAIL", str(exc))
    else:
        report("fixture", name, "PASS")


source_fixture = json.loads((FIXTURES / "source-sample.json").read_text(encoding="utf-8"))
wadl_fixture = json.loads((FIXTURES / "wadl-resources.json").read_text(encoding="utf-8"))
responses = source_fixture["responses"]


def check_event() -> None:
    item = module.parse_response(responses["events"], "roadevent", module.normalise_event)[0]
    assert item["id"] == 9001 and item["highway"] == "SH1"
    assert item["last_updated_at"] == "2026-09-03T08:15:00+12:00"


def check_camera() -> None:
    item = module.parse_response(responses["cameras"], "camera", module.normalise_camera)[0]
    assert item["status"] == "maintenance"
    assert item["image_url"] == "https://trafficnz.info/camera/7001.jpg"


def check_vms() -> None:
    item = module.parse_response(responses["vms"], "vms", module.normalise_vms)[0]
    assert item["message_lines"] == ["ROAD WORKS", "EXPECT DELAYS", "THANK YOU"]
    assert item["last_message_update"] == "2026-09-03T08:20:00+12:00"


def check_tim() -> None:
    item = module.parse_response(responses["travel_times"], "tim", module.normalise_tim)[0]
    assert item["destinations"][0] == {"name": "CITY", "minutes": 12}
    assert item["congestion_status"] is None and item["source_provides_baseline"] is False
    assert item["last_updated_at"] == "2026-09-03T08:22:00+12:00"


def check_schema_failure() -> None:
    try:
        module.parse_response({"response": {}}, "camera", module.normalise_camera)
    except module.SchemaError:
        return
    raise AssertionError("missing source collection was accepted as an empty success")


def check_wadl_contract_fixture() -> None:
    expected = {"cameras/all", "events/all/{zoomlevel}", "regions/all/{zoomlevel}", "signs/tim/all", "signs/vms/all"}
    assert wadl_fixture["version"] == "4"
    assert set(wadl_fixture["required_get_resources"]) == expected


for fixture_name, check in (
    ("road-event parser and freshness", check_event),
    ("camera parser, state and image URL", check_camera),
    ("VMS message parser and freshness", check_vms),
    ("travel-time parser without congestion inference", check_tim),
    ("schema drift fails closed", check_schema_failure),
    ("WADL resource contract sentinel", check_wadl_contract_fixture),
):
    fixture_check(fixture_name, check)


def live_probe(command: str, extra: list[str]) -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI), command, "--limit", "1", "--json", *extra],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        report("live", f"{command} endpoint contract", "FAIL", (completed.stderr or completed.stdout)[:300])
        return
    if completed.returncode in {4, 5} and payload.get("error", {}).get("code") in {4, 5}:
        report("live", f"{command} endpoint contract", "SKIP", payload["error"]["message"])
        return
    if completed.returncode != 0:
        report("live", f"{command} endpoint contract", "FAIL", json.dumps(payload)[:300])
        return
    source = payload.get("source")
    valid = (
        payload.get("ok") is True
        and payload.get("kind") == command
        and isinstance(payload.get("data"), list)
        and isinstance(payload.get("source_count"), int)
        and payload["source_count"] > 0
        and isinstance(source, dict)
        and source.get("url", "").startswith(module.API_ROOT)
        and isinstance(source.get("retrieved_at"), str)
        and source["retrieved_at"].endswith("Z")
        and payload.get("complete") is False
        and len(payload.get("warnings", [])) >= 2
    )
    if not valid:
        report("live", f"{command} endpoint contract", "FAIL", json.dumps(payload)[:300])
        return
    report(
        "live",
        f"{command} endpoint contract",
        "PASS",
        f"source_count={payload['source_count']} retrieved_at={source['retrieved_at']}",
    )


for live_command, flags in (
    ("events", []),
    ("cameras", []),
    ("travel-times", []),
    ("vms", ["--active-only"]),
    ("regions", []),
):
    live_probe(live_command, flags)

failures = results.count(False)
passes = results.count(True)
skips = results.count(None)
if failures:
    print(f"{failures} test(s) failed, {passes} passed, {skips} skipped.")
    raise SystemExit(1)
print(f"All non-skipped tests passed ({passes} passed, {skips} skipped).")
