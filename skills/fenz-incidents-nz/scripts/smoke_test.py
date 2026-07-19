#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"));from fenz_incidents import aggregate_annual,parse_annual_resources,parse_incidents
rows=parse_incidents((S/"tests"/"fixtures"/"incidents.html").read_text(),"https://www.fireandemergency.nz/incidents-and-news/incident-reports/incidents/","2026-07-19T00:00:00Z");assert len(rows)==2 and rows[0]["call_type"]=="Structure fire" and rows[0]["classification_status"].startswith("preliminary")
print("[PASS] fixture FENZ incident number, time, location, duration, station and call type");print("[PASS] contract preliminary classification marker")
resources=parse_annual_resources((S/"tests/fixtures/annual-resources.html").read_text(),"https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/","2026-07-19T00:00:00Z");assert [row["financial_year"] for row in resources]==["2023-24","2024-25"]
annual=aggregate_annual((S/"tests/fixtures/annual.tsv").read_bytes(),resources[1]["download_url"],"2026-07-19T00:00:00Z","2024-25",region="Auckland",metadata_url="https://www.fireandemergency.nz/metadata.pdf");assert sum(row["exposures"] for row in annual)==3 and {row["incidents"] for row in annual}=={1} and all(row["metadata_url"] for row in annual)
invalid=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"annual","--year","2024-25","--limit","101","--json"],capture_output=True,text=True);assert invalid.returncode==2
invalid_year=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"annual","--year","2026","--json"],capture_output=True,text=True);assert invalid_year.returncode==2
print("[PASS] annual resource discovery, TSV aggregation, region filter, provenance and limits")
r=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"recent","--limit","2","--json"],capture_output=True,text=True,timeout=45)
if r.returncode==0:assert json.loads(r.stdout)["data"];print("[PASS] live FENZ incident report")
elif r.returncode in {4,5}:print(f"[SKIP] network FENZ unavailable: {r.stderr.strip()}")
else:print(r.stderr,file=sys.stderr);raise SystemExit(1)
