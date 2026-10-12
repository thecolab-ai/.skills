#!/usr/bin/env python3
"""Fixture checks plus one bounded live row from each NTD resource."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from test_contract import fixture_checks

CLI = Path(__file__).resolve().with_name("cli.py")
MODE_CODE = re.compile(r"[A-Z]{1,4}")
DENIED = {
    "incident_description",
    "person_list",
    "approximate_address",
    "latitude",
    "longitude",
    "latlon",
    "other_event_type_description",
    "evacuation_comment",
}


def run_live(command: str, *extra: str) -> dict | None:
    try:
        completed = subprocess.run(
            [sys.executable, str(CLI), command, "--limit", "1", *extra, "--json"],
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"[FAIL] live network error: source request timed out during {command}")
        return None
    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        print(f"[FAIL] live {command} did not return JSON")
        return None
    message = ""
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        message = str(payload["error"].get("message") or "")
    if completed.returncode != 0:
        if "licence" in message:
            print(f"[FAIL] live {message}")
        else:
            print(f"[FAIL] live network error: {message or completed.stderr.strip() or completed.returncode}")
        return None
    if not isinstance(payload, dict) or not payload.get("results"):
        print(f"[FAIL] live {command} returned zero rows")
        return None
    return payload


def assert_common(payload: dict, resource_id: str, licence_id: str) -> dict:
    meta = payload["meta"]
    assert meta["publisher"] == "Federal Transit Administration"
    assert meta["geography"] == "United States"
    assert meta["licence"] == licence_id
    assert meta["licence_id"] == licence_id
    assert meta["resource_id"] == resource_id
    assert meta["retrieved_at"].endswith("Z")
    assert meta["count"] == 1 and len(payload["results"]) == 1
    assert resource_id in meta["source_url"]
    assert urlparse_host(meta["source_url"]) == "data.transportation.gov"
    for denied in DENIED:
        assert denied not in meta["source_url"]
        assert denied not in payload["results"][0]
    return payload["results"][0]


def urlparse_host(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).hostname


def main() -> int:
    try:
        fixture_checks()
    except (AssertionError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    try:
        events = run_live("events")
        if events is None:
            return 1
        event = assert_common(events, "9ivb-8ae9", "USGOV_WORKS")
        assert MODE_CODE.fullmatch(str(event.get("mode") or ""))
        assert isinstance(event.get("year"), int) and 1900 <= event["year"] <= 2099
        assert isinstance(event.get("event_type"), str) and event["event_type"]
        print("[PASS] live events coded fields, USGOV_WORKS licence and narrative suppression")
        # The newest month can omit service measures while validation is open.
        # A completed 2024 row still uses $limit=1 and carries the aggregates.
        modes = run_live("modes", "--year", "2024")
        if modes is None:
            return 1
        mode = assert_common(modes, "5ti2-5uiv", "PUBLIC_DOMAIN")
        assert MODE_CODE.fullmatch(str(mode.get("mode") or ""))
        assert mode.get("year") == 2024
        assert isinstance(mode.get("month"), str) and mode["month"]
        assert isinstance(mode.get("ridership"), int)
        assert isinstance(mode.get("total_events"), int)
        assert isinstance(mode.get("vehicle_revenue_miles"), int)
        assert modes["meta"]["units"]["ridership"] == "boardings"
        assert modes["meta"]["units"]["vehicle_revenue_miles"] == "miles"
        print("[PASS] live modes monthly aggregates and PUBLIC_DOMAIN licence")
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] live {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
