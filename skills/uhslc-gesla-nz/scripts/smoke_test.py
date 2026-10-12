#!/usr/bin/env python3
"""Fixture contracts plus one bounded live UHSLC GESLA request."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import cli
from test_contract import fixture_checks

ENTRY = Path(__file__).with_name("cli.py")
STATION = "auckland-auct-nzl-ttw"
START = "2024-01-01T00:00:00Z"
END = "2024-01-01T02:00:00Z"


def main() -> int:
    try:
        fixture_checks()
    except Exception as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    print("[PASS] fixture positive series keeps metres, quality flags, duplicate times and the missing-value token")
    print("[PASS] fixture empty CSV and empty upstream responses stay empty")
    print("[PASS] fixture malformed, truncated, wrong-unit and non-CSV payloads fail closed")
    print("[PASS] fixture rate limit, unavailable, timeout, byte cap and off-host redirect are rejected")
    print("[PASS] fixture malformed station and over-long window make no network call")

    completed = subprocess.run(
        [
            sys.executable,
            str(ENTRY),
            "series",
            "--station",
            STATION,
            "--from",
            START,
            "--to",
            END,
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode in {4, 5}:
        detail = completed.stdout.strip() or completed.stderr.strip()
        print(f"[FAIL] live {detail}")
        return completed.returncode
    if completed.returncode != 0:
        print(f"[FAIL] live exit {completed.returncode}: {completed.stdout.strip() or completed.stderr.strip()}")
        return 1
    try:
        payload = json.loads(completed.stdout)
        start = datetime.fromisoformat(START.replace("Z", "+00:00"))
        end = datetime.fromisoformat(END.replace("Z", "+00:00"))
        rows = payload["results"]
        meta = payload["meta"]
        assert "error" not in payload
        assert meta["publisher"] == "University of Hawaii Sea Level Center"
        assert meta["retrieved_at"].endswith("Z")
        assert "not intended for legal use" in meta["licence"]
        assert meta["source_url"].startswith(f"https://{cli.ALLOWED_HOST}/erddap/tabledap/")
        assert f"record_id=%22{STATION}%22" in meta["source_url"]
        assert "time%3E=" in meta["source_url"] and "time%3C" in meta["source_url"]
        assert 1 <= len(rows) <= cli.MAX_ROWS
        midnight = [row for row in rows if row["time"] == START]
        assert midnight, "expected the verified 2024-01-01T00:00:00Z observation"
        assert all(
            row["sea_level"] == "5.871"
            and row["sea_level_unit"] == "m"
            and row["sea_level_missing"] is False
            and row["flag1"] == 3
            and row["flag1_meaning"] == "doubtful_value"
            and row["flag2"] == 0
            and row["flag2_meaning"] == "do_not_use"
            and row["record_id"] == STATION
            for row in midnight
        )
        for row in rows:
            observed = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
            assert observed.tzinfo is not None and observed.utcoffset() == timezone.utc.utcoffset(observed)
            assert start <= observed < end
            assert row["sea_level_unit"] == "m"
            assert row["record_id"] == STATION
            assert row["sea_level"] != "-99.9999"
            assert row["flag1_meaning"] == cli.FLAG1_MEANINGS[row["flag1"]]
            assert row["flag2_meaning"] == cli.FLAG2_MEANINGS[row["flag2"]]
        print(
            f"[PASS] live Auckland GESLA series: {len(rows)} rows, metres, "
            f"flag1 {midnight[0]['flag1']} {midnight[0]['flag1_meaning']}, "
            f"flag2 {midnight[0]['flag2']} {midnight[0]['flag2_meaning']}"
        )
    except (AssertionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] live {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
