#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATE = (date.today() + timedelta(days=45)).isoformat()
MODULE = ROOT / "skills/jetstar-flights/scripts/cli.mjs"
fixture_script = f"""
import {{ flatten }} from {json.dumps(MODULE.as_uri())};
const raw = [{{currencyCode:'NZD',routes:{{aklwlg:{{flights:{{20260801:[{{flightId:'JQ1',departureTime:'2026-08-01T08:00:00',arrivalTime:'2026-08-01T09:00:00',price:59,soldOut:false,member:false,stopCount:0,fareClasses:['Starter']}}]}}}}}}}}];
const out = flatten(raw, {{origin:'AKL',destination:'WLG',date:'2026-08-01',days:1}});
if (out.flights.length !== 1 || out.flights[0].price !== 59 || out.flights[0].currency !== 'NZD') process.exit(1);
"""
fixture = subprocess.run(["node", "--input-type=module", "-e", fixture_script], text=True, capture_output=True, timeout=20)
if fixture.returncode != 0:
    raise SystemExit(fixture.stderr or "Jetstar fixture parser failed")
print("[PASS] fixture Jetstar fare-cache response normalization")

cmd = ["node", str(MODULE), "search", "AKL", "WLG", DATE, "--days", "7", "--json"]
proc = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
if proc.returncode != 0:
    detail = (proc.stderr or proc.stdout).strip()
    if "fetch failed" in detail.lower() or "network" in detail.lower() or "timed out" in detail.lower():
        print(f"[SKIP] Jetstar live assertion: upstream unavailable ({detail[:160]})")
        raise SystemExit(0)
    raise SystemExit(proc.stderr or proc.stdout)
payload = json.loads(proc.stdout)
flights = payload.get("flights") or []
assert flights, "expected at least one Jetstar flight"
first = flights[0]
assert first.get("origin") == "AKL", first
assert first.get("destination") == "WLG", first
assert first.get("price") is not None, first
assert first.get("currency") == "NZD", first
print(f"[PASS] live jetstar-flights: {len(flights)} flights, first=flightId {first.get('flight_id')} ${first.get('price')} {first.get('currency')}")
