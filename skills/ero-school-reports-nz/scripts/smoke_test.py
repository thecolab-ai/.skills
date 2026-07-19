#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"))
from ero_reports import parse_page,report_sections,require_report  # noqa: E402
p=parse_page((S/"tests/fixtures/institution.html").read_text(),"https://www.ero.govt.nz/institution/54/auckland-grammar-school","2026-07-19T00:00:00Z");reports=report_sections(p)
assert reports and reports[0]["report_type"]=="School Evaluation Report" and reports[0]["section"]["provenance"]["section_heading"]=="School Evaluation Report"
assert reports[0]["id"].startswith("54/2026-05-14:") and all("999" not in row["source_url"] for row in p["institutions"])
assert {section["heading"] for section in reports[0]["sections"]}>={"Findings","Next steps for improvement","Expected outcomes"}
actions=[s for s in require_report(reports,reports[0]["id"])["sections"] if "next steps" in s["heading"].casefold()];assert actions and "equity" in actions[0]["text"]
try:require_report(reports,"54/1900-01-01:not-a-report")
except ValueError:pass
else:raise AssertionError("nonexistent ERO report ID must be rejected")
search=parse_page((S/"tests/fixtures/search.html").read_text(),"https://www.ero.govt.nz/review-reports?search=Kawakawa","2026-07-19T00:00:00Z")
assert [row["title"] for row in search["institutions"]]==["Kawakawa Primary School","Te Kōhanga Reo o Kawakawa"]
assert all("999" not in row["source_url"] for row in search["institutions"])
print("[PASS] fixture ERO institution titles, strict report IDs, findings/actions text and section provenance")
run=subprocess.run([sys.executable,str(S/"scripts/cli.py"),"latest","54","--json"],capture_output=True,text=True,timeout=45)
if run.returncode==0:
 out=json.loads(run.stdout);assert "/institution/54/" in out["source"]["url"] and out["data"];print("[PASS] live official ERO institution report")
elif run.returncode in {4,5}:print(f"[SKIP] ERO blocked/unavailable: {run.stderr.strip()}")
else:print(run.stderr,file=sys.stderr);raise SystemExit(1)
