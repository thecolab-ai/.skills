#!/usr/bin/env python3
"""Smoke test: hit the live WCC API and assert a valid response."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

STREET_ID = "6317"
STREET_NAME = "Awa Road, Karaka Bays"
CLI = Path("skills/wellington-bin-schedule/scripts/cli.py").resolve()

spec = importlib.util.spec_from_file_location("wellington_bins_cli", CLI)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)
cli.fetch_text = lambda *_args, **_kwargs: '''
<h3>Awa Road, Karaka Bays</h3>
<div class="collection-date">Friday, 31 July</div>
out before <span>8:00am</span>
<i class="recycling-icon-rubbish"></i><i class="recycling-icon-glass"></i>
'''
fixture = cli.get_collection(STREET_ID, STREET_NAME)
assert fixture["collection_day"] == "Friday" and set(fixture["next_dates"]) == {"rubbish", "recycling"}
print("[PASS] fixture WCC collection HTML parsing")

result = subprocess.run(
    [sys.executable, str(CLI),
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

print(f"[PASS] live street={data['street_name']} next={data['next_dates']} day={data['collection_day']} time={data['put_out_time']}")
