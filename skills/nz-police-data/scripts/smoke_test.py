#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"))
from police_data_catalog import parse_catalog,parse_tableau  # noqa: E402
source="https://www.police.govt.nz/about-us/publications-statistics/data-and-statistics/policedatanz";stamp="2026-07-19T00:00:00Z"
rows=parse_catalog((S/"tests/fixtures/catalog.html").read_text(),source,stamp);assert len(rows)==2 and {r["measure"] for r in rows}=={"victimisations","proceedings"}
t=parse_tableau((S/"tests/fixtures/report.html").read_text(),rows[0]["report_url"],stamp);assert t["workbook"]=="Victimisations" and t["view"]=="Summary" and t["row_retrieval_supported"] is False
print("[PASS] fixture Police report catalogue and official Tableau workbook reference")
unsupported=subprocess.run([sys.executable,str(S/"scripts/cli.py"),"trend","--offence","burglary","--json"],capture_output=True,text=True);assert unsupported.returncode==7 and "cannot be applied honestly" in unsupported.stderr
print("[PASS] unsupported statistical filters cannot return unrelated catalogue success")
run=subprocess.run([sys.executable,str(S/"scripts/cli.py"),"definitions","--json"],capture_output=True,text=True,timeout=45)
if run.returncode==0:
 p=json.loads(run.stdout);assert p["data"]["RCVS"] and p["data"]["update_cadence"];print("[PASS] live official Police catalogue and definitions")
elif run.returncode in {4,5}:print(f"[SKIP] Police source blocked/unavailable: {run.stderr.strip()}")
else:print(run.stderr,file=sys.stderr);raise SystemExit(1)
