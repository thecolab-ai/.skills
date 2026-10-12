#!/usr/bin/env python3
"""Fixture checks plus one bounded live observation-day read."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_contract import fixture_checks


def live_probe() -> int:
    script = Path(__file__).with_name("cli.py")
    completed = subprocess.run(
        [sys.executable, str(script), "day", "--latest", "--limit", "5", "--json"],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if "Traceback (most recent call last)" in completed.stderr:
        print("[FAIL] live traceback")
        return 1
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print("[FAIL] live network error: response was not JSON")
        return 5
    if completed.returncode != 0:
        error = payload.get("error") if isinstance(payload, dict) else {}
        message = str(error.get("message") or "") if isinstance(error, dict) else ""
        error_type = str(error.get("type") or "") if isinstance(error, dict) else ""
        if "licence" in message.lower():
            print("[FAIL] live licence was not CC BY 4.0")
            return 1
        if error_type == "schema_failure" or completed.returncode == 6:
            print(f"[FAIL] live schema {message}")
            return 1
        if error_type in {"upstream_unavailable", "blocked"} or completed.returncode in {4, 5}:
            print(f"[FAIL] live network error: {message or 'upstream unavailable'}")
            return 5
        print(f"[FAIL] live {message or 'command failed'}")
        return 1
    meta = payload.get("meta") if isinstance(payload, dict) else None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(meta, dict) or not isinstance(results, list):
        print("[FAIL] live envelope was not meta and results")
        return 1
    licence = str(meta.get("licence") or "")
    if "CC BY 4.0" not in licence or "Auckland Transport" not in licence:
        print("[FAIL] live licence was not CC BY 4.0")
        return 1
    print("[PASS] live index licence is CC BY 4.0 with Auckland Transport attribution")
    source_url = str(meta.get("source_url") or "")
    latest = str(meta.get("latest_data") or "")
    expected_url = "https://data.aklontrack.com/open/v1/observations/" + latest.replace("-", "/") + ".json"
    if source_url != expected_url:
        print("[FAIL] live source URL was not the indexed observation file")
        return 1
    print("[PASS] live source URL is the indexed observation day")
    if not results:
        print("[FAIL] live empty observation day")
        return 1
    timed = None
    for row in results:
        if row.get("service_date") != latest or type(row.get("state")) is not int:
            print("[FAIL] live observation fields were missing or the wrong type")
            return 1
        if not isinstance(row.get("stop_id"), str) or not row.get("stop_id"):
            print("[FAIL] live observation fields were missing or the wrong type")
            return 1
        for seconds_key, clock_key in (("arrival", "arrival_time"), ("departure", "departure_time")):
            seconds = row.get(seconds_key)
            clock = row.get(clock_key)
            if seconds is None and clock is not None:
                print("[FAIL] live observation invented a clock time")
                return 1
            if type(seconds) is int and not str(clock or "").startswith(latest + "T"):
                print("[FAIL] live observation clock time did not use the service date")
                return 1
        if timed is None and type(row.get("departure_delay")) is int and type(row.get("arrival")) is int:
            timed = row
    if timed is None:
        print("[FAIL] live observation had no reported delay")
        return 1
    print("[PASS] live observation has a station id, integer delay seconds and Auckland time")
    if len(results) > 5:
        print("[FAIL] live result exceeded the requested limit")
        return 1
    print("[PASS] live result stayed within the requested limit")
    return 0


def main() -> int:
    failures = fixture_checks()
    if failures:
        return 1
    return live_probe()


if __name__ == "__main__":
    raise SystemExit(main())
