#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DATE="$(python3 - <<'PY'
from datetime import date, timedelta
print((date.today() + timedelta(days=7)).isoformat())
PY
)"
OUT="$(python3 "$ROOT/skills/airnz-flights/scripts/cli.py" AKL WLG "$DATE" --limit 3 --json)"
JSON_PAYLOAD="$OUT" python3 - <<'PY'
import json, os
payload = json.loads(os.environ['JSON_PAYLOAD'])
flights = payload.get('flights') or []
assert flights, 'expected at least one Air NZ flight row'
first = flights[0]
segments = first.get('flights') or []
assert segments, first
assert segments[0].get('flight_number'), first
assert 'booking_search_url' in payload, payload
if payload.get('fare_search_blocked'):
    assert first.get('lowest_fare') is None, first
else:
    assert first.get('lowest_fare', {}).get('price') is not None, first
price = first.get('lowest_fare', {}).get('adult_price') if first.get('lowest_fare') else 'fare-blocked'
print(
    f"OK airnz-flights smoke ({payload.get('source')}): {len(flights)} flights, "
    f"first={segments[0].get('flight_number')} {first.get('departure')}->{first.get('arrival')} price={price}"
)
PY
