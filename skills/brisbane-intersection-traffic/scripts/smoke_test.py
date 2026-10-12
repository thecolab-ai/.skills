#!/usr/bin/env python3
"""Fixture and bounded live checks for Brisbane intersection traffic."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = Path(__file__).with_name("cli.py")
FIXTURES = ROOT / "tests" / "fixtures"
RECORDED = "2026-10-11T18:09:00+00:00"


def run(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check(condition: bool, kind: str, message: str) -> None:
    if not condition:
        print(f"[FAIL] {kind} {message}")
        raise SystemExit(1)
    print(f"[PASS] {kind} {message}")


def payload_of(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def fixture(name: str) -> str:
    return str(FIXTURES / name)


def main() -> int:
    help_text = run(["--help"]).stdout
    check("volumes" in help_text and "signals" in help_text, "contract", "help lists volumes and signals")

    positive = run(["volumes", "--limit", "1", "--fixture", fixture("volumes-positive.json"), "--json"])
    body = payload_of(positive)
    row = body["results"][0]
    check(positive.returncode == 0 and row["tsc"] == "757" and row["lane"] == "SA-267", "fixture", "positive volume keeps tsc and lane")
    check(row["recorded"] == RECORDED and row["ds1"] == "3" and row["ds3"] is None, "fixture", "positive volume preserves timestamp, string flow and null slot")
    check(body["meta"]["licence"] == "CC BY 4.0" and body["meta"]["total_count"] == 2, "fixture", "positive volume reports CC BY 4.0 and source total")
    check(body["meta"]["latest_data"] == RECORDED, "fixture", "volume latest_data is the source recorded timestamp")

    empty = payload_of(run(["volumes", "--limit", "1", "--fixture", fixture("volumes-empty.json"), "--json"]))
    check(empty["results"] == [] and "latest_data" not in empty["meta"], "fixture", "empty volume result invents no rows")

    malformed = run(["volumes", "--limit", "1", "--fixture", fixture("malformed.json"), "--json"])
    check(malformed.returncode == 6 and payload_of(malformed)["error"]["type"] == "schema_failure", "fixture", "malformed payload is a schema failure")

    rejected = run(["volumes", "--limit", "99", "--fixture", fixture("missing-would-be-read.json"), "--json"])
    check(rejected.returncode == 2 and rejected.stderr == "", "fixture", "invalid limit is rejected before retrieval")

    rate = payload_of(run(["volumes", "--limit", "1", "--fixture", fixture("http-429.json"), "--json"]))
    check(rate["error"]["code"] == 4 and rate["error"]["retry_after"] == "30", "fixture", "HTTP 429 keeps Retry-After")

    unavailable = run(["signals", "--limit", "1", "--fixture", fixture("http-503.json"), "--json"])
    check(unavailable.returncode == 5 and "HTTP 503" in payload_of(unavailable)["error"]["message"], "fixture", "HTTP 503 is upstream unavailable")

    signal = payload_of(run(["signals", "--limit", "1", "--fixture", fixture("signals-positive.json"), "--format", "geojson"]))
    coordinates = signal["features"][0]["geometry"]["coordinates"]
    check(coordinates == [153.16, -27.44] and signal["meta"]["licence"] == "CC BY 4.0", "fixture", "signal GeoJSON uses published longitude and latitude")

    mismatch = run(["signals", "--limit", "1", "--fixture", fixture("signals-mismatch.json"), "--json"])
    check(mismatch.returncode == 6, "fixture", "disagreeing signal coordinates are a schema failure")

    outside = run(
        ["signals", "--limit", "1", "--bbox", "152,-28,152.1,-27.9", "--fixture", fixture("signals-positive.json"), "--json"]
    )
    check(outside.returncode == 6, "fixture", "signal outside the box is rejected")

    import cli

    check(
        cli.signal_where(None, (153.15, -27.45, 153.17, -27.43)) == "in_bbox(geo_point_2d,-27.45,153.15,-27.43,153.17)",
        "fixture",
        "signal bbox uses latitude then longitude for ODS",
    )
    try:
        cli.check_public_url("https://off-allowlist.invalid/api", redirect=True)
    except cli.SkillError as exc:
        redirected = exc.code == 4
    else:
        redirected = False
    check(redirected, "fixture", "off-host redirect is rejected")

    live_volumes = run(["volumes", "--limit", "1", "--timeout", "15", "--json"], timeout=25)
    if live_volumes.returncode != 0:
        message = live_volumes.stdout or live_volumes.stderr
        print(f"[FAIL] live volumes: {message.strip()}")
        return 1
    live_volume = payload_of(live_volumes)
    live_row = live_volume["results"][0]
    check(
        live_volume["meta"]["licence"] == "CC BY 4.0"
        and "traffic-data-at-intersection" in live_volume["meta"]["source_url"]
        and isinstance(live_row["tsc"], str)
        and live_row["tsc"] != ""
        and "T" in live_row["recorded"]
        and (live_row["ds1"] is None or isinstance(live_row["ds1"], str))
        and live_volume["meta"]["total_count"] >= 1,
        "live",
        "volumes returns a licensed SCATS row with recorded time and degree of saturation",
    )

    live_signals = run(["signals", "--limit", "1", "--timeout", "15", "--json"], timeout=25)
    if live_signals.returncode != 0:
        message = live_signals.stdout or live_signals.stderr
        print(f"[FAIL] live signals: {message.strip()}")
        return 1
    live_signal_body = payload_of(live_signals)
    live_signal = live_signal_body["results"][0]
    point = live_signal["geo_point_2d"]
    check(
        live_signal_body["meta"]["licence"] == "CC BY 4.0"
        and "traffic-management-signal-locations" in live_signal_body["meta"]["source_url"]
        and isinstance(live_signal["tsc"], str)
        and live_signal["tsc"] != ""
        and 152 <= float(point["lon"]) <= 154
        and -28 <= float(point["lat"]) <= -27,
        "live",
        "signals returns a separately licensed council signal point in the Brisbane range",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
