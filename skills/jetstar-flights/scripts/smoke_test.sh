#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DATE="$(python3 - <<'PY'
from datetime import date, timedelta
print((date.today() + timedelta(days=45)).isoformat())
PY
)"
OUT="$(node "$ROOT/skills/jetstar-flights/scripts/cli.mjs" search AKL WLG "$DATE" --days 7 --json)"
JSON_PAYLOAD="$OUT" python3 - <<'PY'
import json, os
payload = json.loads(os.environ['JSON_PAYLOAD'])
flights = payload.get('flights') or []
assert flights, 'expected at least one Jetstar flight'
first = flights[0]
assert first.get('origin') == 'AKL', first
assert first.get('destination') == 'WLG', first
assert first.get('price') is not None, first
assert first.get('currency') == 'NZD', first
print(f"OK jetstar-flights smoke: {len(flights)} flights, first=flightId {first.get('flight_id')} ${first.get('price')} {first.get('currency')}")
PY
