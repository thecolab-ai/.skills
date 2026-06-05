#!/usr/bin/env python3
"""Smoke test: hit the live WCC API and assert a valid response."""
import json
import subprocess
import sys

STREET_ID = "6317"
STREET_NAME = "Awa Road, Karaka Bays"

result = subprocess.run(
    [sys.executable, "skills/wellington-bin-schedule/scripts/cli.py",
     "--street-id", STREET_ID, "--json"],
    capture_output=True, text=True
)

if result.returncode != 0:
    print("FAIL: non-zero exit")
    print(result.stderr)
    sys.exit(1)

data = json.loads(result.stdout)

assert data.get("street_id") == STREET_ID, f"wrong street_id: {data}"
assert data.get("next_dates"), f"no next_dates in response: {data}"
assert data.get("collection_day"), f"no collection_day: {data}"
assert data.get("put_out_time"), f"no put_out_time: {data}"
assert "rubbish" in data["next_dates"] or "recycling" in data["next_dates"], \
    f"expected at least one collection stream: {data}"

print(f"PASS  street={data['street_name']}  next={data['next_dates']}  day={data['collection_day']}  time={data['put_out_time']}")
