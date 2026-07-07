#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATE = (date.today() + timedelta(days=7)).isoformat()
browser_required = os.getenv("COLAB_SMOKE_USE_BROWSER") == "1"
use_browser = browser_required or find_spec("cloakbrowser") is not None
cmd = [sys.executable, str(ROOT / "skills/airnz-flights/scripts/cli.py"), "AKL", "WLG", DATE, "--limit", "3", "--json"]
if use_browser:
    cmd.append("--browser")
proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
if proc.returncode != 0:
    if use_browser and not browser_required:
        try:
            error_payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            error_payload = {}
        if error_payload.get("error") == "cloakbrowser_not_installed":
            fallback_cmd = [
                sys.executable,
                str(ROOT / "skills/airnz-flights/scripts/cli.py"),
                "AKL",
                "WLG",
                DATE,
                "--limit",
                "3",
                "--json",
            ]
            proc = subprocess.run(fallback_cmd, text=True, capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)
payload = json.loads(proc.stdout)
flights = payload.get("flights") or []
assert flights, "expected at least one Air NZ flight row"
first = flights[0]
segments = first.get("flights") or []
assert segments, first
assert segments[0].get("flight_number"), first
if payload.get("fare_search_blocked"):
    assert first.get("lowest_fare") is None, first
else:
    assert first.get("lowest_fare", {}).get("price") is not None, first
assert "booking_search_url" in payload, payload
price = first.get("lowest_fare", {}).get("adult_price") if first.get("lowest_fare") else "fare-blocked"
print(
    f"OK airnz-flights smoke ({payload.get('source')}): {len(flights)} flights, "
    f"first={segments[0].get('flight_number')} {first.get('departure')}->{first.get('arrival')} price={price}"
)
