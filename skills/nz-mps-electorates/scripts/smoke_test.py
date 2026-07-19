#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"))
from parliament_members import parse_members,parse_profile
source="https://www3.parliament.nz/en/mps-and-electorates/members-of-parliament/"
rows=parse_members((S/"tests/fixtures/members.html").read_text(),source,"2026-07-19T00:00:00Z")
assert rows[0]["party"]=="NZ First Party" and rows[0]["member_type"]=="list" and rows[1]["electorate"]=="Waitaki"
profile=parse_profile((S/"tests/fixtures/profile.html").read_text(),rows[0]["source_url"],"2026-07-19T00:00:00Z")
assert profile["current_roles"][0]["subject"]=="Rural Communities" and profile["official_parliament_emails"]==["Mark.Patterson@parliament.govt.nz"]
assert {role["kind"] for role in profile["current_roles"]}=={"Portfolio","Select Committee"} and profile["record_status"]=="current"
print("[PASS] fixture MP directory, current roles and official contact")
r=subprocess.run([sys.executable,str(S/"scripts/cli.py"),"list","--limit","2","--json"],capture_output=True,text=True,timeout=45)
if r.returncode==0:
 payload=json.loads(r.stdout);assert payload["data"] and all(x["party"] for x in payload["data"]);print("[PASS] live Parliament MP directory")
elif r.returncode in {4,5}:print(f"[SKIP] Parliament source unavailable: {r.stderr.strip()}")
else:print(r.stderr,file=sys.stderr);raise SystemExit(1)
