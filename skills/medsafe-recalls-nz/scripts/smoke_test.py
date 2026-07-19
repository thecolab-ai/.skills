#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(S.parents[1]/"lib")); from medsafe_recalls import parse_results,parse_detail
F=S/"tests"/"fixtures"; at="2026-07-19T00:00:00Z"; rows=parse_results((F/"recalls.html").read_text(),"https://www.medsafe.govt.nz/hot/Recalls/RecallSearch.asp",at); detail=parse_detail((F/"recall-detail.html").read_text(),rows[0]["source_url"],at)
assert rows[0]["id"]=="37032" and detail["type_of_product"]=="Device" and detail["affected"]=="Product code SMI-1002"
assert parse_results((F/"empty-results.html").read_text(),"https://www.medsafe.govt.nz/hot/Recalls/RecallSearch.asp",at)==[]
try:
    parse_results((F/"malformed-results.html").read_text(),"https://www.medsafe.govt.nz/hot/Recalls/RecallSearch.asp",at)
except ValueError as exc:
    assert "malformed recall row" in str(exc)
else:
    raise AssertionError("malformed Medsafe result row was accepted as an empty success")
assert "smi-1002" in json.dumps(detail).lower()
print("[PASS] fixture Medsafe recall list and batch/detail parsing"); print("[PASS] contract parsed labelled source fields")
r=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"latest","--limit","2","--json"],capture_output=True,text=True,timeout=60)
if r.returncode==0: assert json.loads(r.stdout)["data"]; print("[PASS] live Medsafe recall results")
elif r.returncode in {4,5}: print(f"[SKIP] network Medsafe unavailable: {r.stderr.strip()}")
else: print(r.stderr,file=sys.stderr); raise SystemExit(1)
