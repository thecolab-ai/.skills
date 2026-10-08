#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"));from fenz_incidents import aggregate_annual,parse_annual_resources,parse_incidents
from test_contract import test_source_fixtures, test_request_contract, test_http_400_is_a_failure, test_incomplete_records, test_error_envelopes, test_published_slices_and_nz_day
test_source_fixtures()
test_request_contract()
test_http_400_is_a_failure()
test_incomplete_records()
test_error_envelopes()
test_published_slices_and_nz_day()
rows=parse_incidents((S/"tests"/"fixtures"/"incidents.html").read_text(),"https://www.fireandemergency.nz/incidents-and-news/incident-reports/incidents/","2026-07-19T00:00:00Z");assert len(rows)==2 and rows[0]["call_type"]=="Structure fire" and rows[0]["classification_status"].startswith("preliminary")
print("[PASS] fixture FENZ incident number, time, location, duration, station and call type");print("[PASS] contract preliminary classification marker")
resources=parse_annual_resources((S/"tests/fixtures/annual-resources.html").read_text(),"https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/","2026-07-19T00:00:00Z");assert [row["financial_year"] for row in resources]==["2023-24","2024-25"]
annual=aggregate_annual((S/"tests/fixtures/annual.tsv").read_bytes(),resources[1]["download_url"],"2026-07-19T00:00:00Z","2024-25",region="Auckland",metadata_url="https://www.fireandemergency.nz/metadata.pdf");assert sum(row["exposures"] for row in annual)==3 and {row["incidents"] for row in annual}=={1} and all(row["metadata_url"] for row in annual)
invalid=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"annual","--year","2024-25","--limit","101","--json"],capture_output=True,text=True);assert invalid.returncode==2
invalid_year=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"annual","--year","2026","--json"],capture_output=True,text=True);assert invalid_year.returncode==2
print("[PASS] fixture annual resource discovery, TSV aggregation, region filter, provenance and limits")
try:
 r=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"region","Auckland","--report-region","north","--limit","2","--json"],capture_output=True,text=True,timeout=20)
except subprocess.TimeoutExpired as exc:
 print(f"[SKIP] network FENZ query timed out after {exc.timeout}s")
 raise SystemExit(0)
if r.returncode==0:
 payload=json.loads(r.stdout);assert payload["results"]
 assert all("auckland" in row["location"].casefold() for row in payload["results"])
 assert payload["meta"]["report_regions"]==["north"] and payload["meta"]["report_day"]
 assert all(payload["meta"].get(key) for key in ("source_url","publisher","licence","retrieved_at","latest_data"))
 print(f"[PASS] live FENZ Auckland query: {len(payload['results'])} results; {payload['results'][0]['incident_number']}")
elif r.returncode in {4,5}:print(f"[SKIP] network FENZ unavailable: {(r.stdout or r.stderr).strip()}")
else:print(r.stdout or r.stderr,file=sys.stderr);raise SystemExit(1)
