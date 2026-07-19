#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"))
from jobs_online import parse_jobs_csv  # noqa: E402
rows=parse_jobs_csv((S/"tests/fixtures/jobs.csv").read_text(),"https://www.mbie.govt.nz/assets/jobs.csv","2026-07-19T00:00:00Z")
assert len(rows)==3 and rows[0]["period"]=="2026-03-01" and rows[0]["avi"]==112.5 and rows[0]["seasonal_adjustment"]=="unadjusted"
assert [row["dimension"] for row in rows]==["industry","occupation","skill_level"]
print("[PASS] fixture Jobs Online period, geography, series, index and adjustment")
for invalid in (("trend","--from","bad","--to","2026-03-01"),("trend","--from","2026-06-01","--to","2026-03-01")):
 run=subprocess.run([sys.executable,str(S/"scripts/cli.py"),*invalid,"--json"],capture_output=True,text=True,timeout=10)
 assert run.returncode==2
print("[PASS] Jobs Online trend dates fail before source retrieval")
run=subprocess.run([sys.executable,str(S/"scripts/cli.py"),"region","Auckland","--limit","2","--json"],capture_output=True,text=True,timeout=90)
if run.returncode==0:
 p=json.loads(run.stdout);assert p["data"] and all("Auckland" in r["geography"] for r in p["data"]);print("[PASS] live official MBIE consolidated Jobs Online CSV")
elif run.returncode in {4,5}:print(f"[SKIP] MBIE blocked/unavailable: {run.stderr.strip()}")
else:print(run.stderr,file=sys.stderr);raise SystemExit(1)
