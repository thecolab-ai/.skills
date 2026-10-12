#!/usr/bin/env python3
"""Fixture assertions plus one bounded GNS WFS live probe."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]
BOX = "174.76,-36.86,174.78,-36.84"
SOUTH_BOX = "174.9,-37.05,174.98,-36.98"
SOUTH_BOUNDS = (174.9, -37.05, 174.98, -36.98)
BBOX_SLACK_DEGREES = 0.002
BBOX = ["units", "--bbox", BOX, "--limit", "1"]
LIVE = ["units", "--bbox", BOX, "--limit", "5"]
LIVE_SOUTH = ["units", "--bbox", SOUTH_BOX, "--limit", "5"]
LAYER_MIN_LON, LAYER_MAX_LON = 174.39, 175.32
LAYER_MIN_LAT, LAYER_MAX_LAT = -37.33, -36.69
NETWORK_MARKERS = (
    "network error",
    "upstream unavailable",
    "timed out",
    "rate_limited",
    "http 429",
    "http 503",
    "name or service not known",
    "temporary failure",
)


def run(arguments: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_checks() -> None:
    code, stdout, stderr = run([*BBOX, "--fixture", "units-positive", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr)
    record = payload["results"][0]
    require(record["unit_code"] == "FIX" and record["area"] == 1000.0, record)
    require(record["descriptio"].startswith("Synthetic"), "source description was rewritten")
    require("latest_data" not in payload["meta"], payload["meta"])
    require(payload["page"]["matched"] == 3 and payload["page"]["returned"] == 1, payload["page"])
    print("[PASS] fixture positive unit keeps source fields and omits latest_data")

    code, stdout, stderr = run([*BBOX, "--fixture", "units-empty", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and stderr == "" and payload["results"] == [], stdout)
    require("error" not in payload, "empty intersection was an error")
    print("[PASS] fixture empty intersection is an empty result")

    code, stdout, _stderr = run([*BBOX, "--fixture", "units-malformed", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", payload)
    print("[PASS] fixture malformed GeoJSON is schema_failure")

    code, stdout, _stderr = run([*BBOX, "--fixture", "transport-429", "--json"])
    payload = json.loads(stdout)
    require(code == 4 and payload["error"]["retry_after"] == "30", payload)
    require(payload["results"] == [], "rate limit returned rows")
    print("[PASS] fixture rate limit keeps retry_after and returns no rows")

    code, stdout, _stderr = run([*BBOX, "--fixture", "transport-503", "--json"])
    payload = json.loads(stdout)
    require(code == 5 and "http 503" in payload["error"]["message"], payload)
    print("[PASS] fixture service unavailable is an upstream failure")

    code, stdout, _stderr = run([*BBOX, "--fixture", "transport-off-host", "--json"])
    payload = json.loads(stdout)
    require(code == 7 and payload["results"] == [], payload)
    require("off-host.invalid" not in stdout, stdout)
    print("[PASS] fixture off-host redirect is refused")

    code, stdout, _stderr = run([*BBOX, "--fixture", "units-nztm", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and "1750000" not in stdout, payload)
    print("[PASS] fixture NZTM coordinates are rejected")

    code, stdout, stderr = run(
        ["units", "--bbox", BOX, "--limit", "2", "--fixture", "units-published-codes", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr or stdout[:400])
    codes = [row["unit_code"] for row in payload["results"]]
    require(codes == ["tl~", "Qval+tl~"], codes)
    require("strat_unit" not in payload["results"][0], payload["results"][0])
    require(payload["results"][1]["strat_unit"] == "Fixture combined unit", payload["results"][1])
    print("[PASS] fixture published unit codes tl~ and Qval+tl~ are accepted")

    code, stdout, _stderr = run([*BBOX, "--fixture", "units-bad-code", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", payload)
    require("map-unit code" in payload["error"]["message"], payload["error"])
    print("[PASS] fixture malformed unit code is schema_failure")

    code, stdout, _stderr = run(["units", "--bbox", BOX, "--limit", "6", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["results"] == [], payload)
    print("[PASS] fixture limit above 5 is rejected before a request")

    code, stdout, stderr = run(
        ["units", "--bbox", BOX, "--limit", "3", "--fixture", "units-near-miss", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr or stdout[:400])
    codes = [row["unit_code"] for row in payload["results"]]
    require(codes == ["Q1l", "Mwe"], codes)
    require("Qvat" not in stdout, stdout)
    require(payload["page"]["dropped_outside_bbox"] == 1, payload["page"])
    require(payload["page"]["returned"] == 2, payload["page"])
    print("[PASS] fixture near-miss geometry keeps overlapping units")

    code, stdout, stderr = run(
        ["units", "--bbox", BOX, "--limit", "1", "--fixture", "units-uncertain-code", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr or stdout[:400])
    record = payload["results"][0]
    require(record["unit_code"] == "?Pks~" and record["uncertain"] is True, record)
    require(record["strat_unit"] == "Kawaa Formation", record)
    print("[PASS] fixture uncertain unit code ?Pks~ is accepted")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def first_position(geometry: dict) -> list[float] | None:
    coordinates = geometry.get("coordinates")

    def walk(value: object) -> list[float] | None:
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            return [float(value[0]), float(value[1])]
        if isinstance(value, list):
            for item in value:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(coordinates)


def live_checks() -> int:
    try:
        code, stdout, stderr = run([*LIVE, "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] live probe skipped: network error: source request timed out")
        return 0
    if transport_failure(code, stdout, stderr):
        print("[SKIP] live probe skipped: upstream unavailable or rate limited")
        return 0
    try:
        payload = json.loads(stdout)
        require(code == 0 and stderr == "", stderr or stdout[:400])
        results = payload["results"]
        require(len(results) >= 5, results)
        codes = []
        named = []
        for record in results:
            require(isinstance(record.get("unit_code"), str) and record["unit_code"], record)
            require(record["uncertain"] is record["unit_code"].startswith("?"), record)
            require(" " not in record["unit_code"] and "<" not in record["unit_code"], record["unit_code"])
            codes.append(record["unit_code"])
            if isinstance(record.get("strat_unit"), str) and record["strat_unit"]:
                named.append(record["strat_unit"])
            require(str(record["feature_id"]).startswith("NZL-Urban_Auckland_geological_units."), record)
            position = first_position(record["geometry"])
            require(position is not None, record["geometry"])
            lon, lat = position
            require(LAYER_MIN_LON <= lon <= LAYER_MAX_LON and LAYER_MIN_LAT <= lat <= LAYER_MAX_LAT, position)
        require("tl~" in codes, codes)
        require(named, "live rows omitted every stratigraphic name")
        require(payload["page"]["returned"] >= 5 and payload["page"]["matched"] >= 5, payload["page"])
        require(payload["page"]["dropped_outside_bbox"] >= 0, payload["page"])
        require(payload["page"]["limit"] == 5, payload["page"])
        require(payload["meta"]["publisher"] == "GNS Science", payload["meta"])
        require("Creative Commons Attribution 3.0 New Zealand" in payload["meta"].get("licence", ""), payload["meta"])
        require("latest_data" not in payload["meta"], "live response time was stored as latest_data")
        require("typeNames=gns%3ANZL-Urban_Auckland_geological_units" in payload["meta"]["source_url"], payload["meta"])
        require("count=5" in payload["meta"]["source_url"], payload["meta"]["source_url"])
        print(
            f"[PASS] live Auckland box returned {len(results)} units including "
            f"{', '.join(codes)} ({named[0]}) inside the published layer extent"
        )
    except (AssertionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"[FAIL] live Auckland geological unit probe: {exc}")
        return 1
    return 0


def geometry_bounds(geometry: dict) -> list[float]:
    bounds = [math.inf, math.inf, -math.inf, -math.inf]

    def walk(value: object) -> None:
        if (
            isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], (int, float))
            and not isinstance(value[0], bool)
            and isinstance(value[1], (int, float))
            and not isinstance(value[1], bool)
        ):
            bounds[0] = min(bounds[0], float(value[0]))
            bounds[1] = min(bounds[1], float(value[1]))
            bounds[2] = max(bounds[2], float(value[0]))
            bounds[3] = max(bounds[3], float(value[1]))
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates"))
    return bounds


def outside_slack(bounds: list[float], box: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = box
    slack = BBOX_SLACK_DEGREES
    return (
        bounds[2] < min_lon - slack
        or bounds[0] > max_lon + slack
        or bounds[3] < min_lat - slack
        or bounds[1] > max_lat + slack
    )


def overlaps_box(bounds: list[float], box: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = box
    return not (
        bounds[2] < min_lon
        or bounds[0] > max_lon
        or bounds[3] < min_lat
        or bounds[1] > max_lat
    )


def live_south_checks() -> int:
    """South Auckland box that returns a polygon a few tens of metres outside."""
    try:
        code, stdout, stderr = run([*LIVE_SOUTH, "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] south Auckland live probe skipped: network error: source request timed out")
        return 0
    if transport_failure(code, stdout, stderr):
        print("[SKIP] south Auckland live probe skipped: upstream unavailable or rate limited")
        return 0
    try:
        payload = json.loads(stdout)
        require(code == 0 and stderr == "", stderr or stdout[:400])
        results = payload["results"]
        require(len(results) == 5, results)
        overlaps = 0
        for record in results:
            require(isinstance(record.get("unit_code"), str) and record["unit_code"], record)
            require(record["uncertain"] is record["unit_code"].startswith("?"), record)
            require(" " not in record["unit_code"] and "<" not in record["unit_code"], record["unit_code"])
            bounds = geometry_bounds(record["geometry"])
            require(not outside_slack(bounds, SOUTH_BOUNDS), bounds)
            if overlaps_box(bounds, SOUTH_BOUNDS):
                overlaps += 1
        require(overlaps >= 1, "south box dropped every overlapping unit")
        require(payload["page"]["limit"] == 5, payload["page"])
        require(payload["page"]["returned"] == 5, payload["page"])
        require(payload["page"]["dropped_outside_bbox"] == 0, payload["page"])
        require(payload["page"]["matched"] >= 5, payload["page"])
        require("error" not in payload, payload)
        require(payload["meta"]["publisher"] == "GNS Science", payload["meta"])
        require("Creative Commons Attribution 3.0 New Zealand" in payload["meta"].get("licence", ""), payload["meta"])
        print(
            f"[PASS] live south Auckland box returned {len(results)} units "
            f"including {overlaps} that overlap the box"
        )
    except (AssertionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"[FAIL] live south Auckland geological unit probe: {exc}")
        return 1
    return 0


def main() -> int:
    try:
        fixture_checks()
    except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    if live_checks():
        return 1
    return live_south_checks()


if __name__ == "__main__":
    raise SystemExit(main())
