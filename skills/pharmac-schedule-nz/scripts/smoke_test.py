#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
SKILL = Path(__file__).resolve().parents[1]; ROOT = SKILL.parents[1]; sys.path.insert(0, str(ROOT / "lib"))
from pharmac_schedule import diff_records, parse_schedule
body = (SKILL / "tests" / "fixtures" / "schedule.xml").read_bytes(); metadata, rows = parse_schedule(body, "https://schedule.pharmac.govt.nz/test.xml", "2026-07-19T00:00:00Z")
assert metadata["edition"] == "July 2026" and rows[0]["chemical"] == "Example medicine" and rows[0]["subsidy"] == "5.00"
assert rows[0]["special_authority_codes"] == ["SA1234"] and rows[0]["special_authorities"][0]["criteria"]
new_body = body.replace(b"5.00", b"6.00"); new_meta, new_rows = parse_schedule(new_body, "https://schedule.pharmac.govt.nz/new.xml", "2026-07-19T01:00:00Z")
changes = diff_records(metadata, rows, new_meta, new_rows, "2026-06", "2026-07")
assert changes[0]["field_changes"]["subsidy"] == {"before": "5.00", "after": "6.00"}
assert changes[0]["from_source"]["url"].endswith("test.xml") and changes[0]["to_source"]["url"].endswith("new.xml")
print("[PASS] fixture Pharmac XML pack, subsidy and Special Authority parsing")
r = subprocess.run([sys.executable, str(SKILL / "scripts" / "cli.py"), "--help"], capture_output=True, text=True, timeout=10); assert r.returncode == 0
print("[PASS] contract CLI help is executable")
r = subprocess.run([sys.executable, str(SKILL / "scripts" / "cli.py"), "schedule-version", "--json"], capture_output=True, text=True, timeout=60)
if r.returncode == 0:
    payload = json.loads(r.stdout); assert payload["data"][0]["edition"]; print("[PASS] live Pharmac production XML version and records")
elif r.returncode in {4, 5}: print(f"[SKIP] network Pharmac source unavailable: {r.stderr.strip()}")
else: print(r.stderr, file=sys.stderr); raise SystemExit(1)
