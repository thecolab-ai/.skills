#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATE = (date.today() + timedelta(days=45)).isoformat()
cmd = ["node", str(ROOT / "skills/jetstar-flights/scripts/cli.mjs"), "search", "AKL", "WLG", DATE, "--days", "7", "--json"]
proc = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or proc.stdout)
payload = json.loads(proc.stdout)
flights = payload.get("flights") or []
assert flights, "expected at least one Jetstar flight"
first = flights[0]
assert first.get("origin") == "AKL", first
assert first.get("destination") == "WLG", first
assert first.get("price") is not None, first
assert first.get("currency") == "NZD", first
print(f"OK jetstar-flights smoke: {len(flights)} flights, first=flightId {first.get('flight_id')} ${first.get('price')} {first.get('currency')}")
