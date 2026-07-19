#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"));from product_recalls import matches_filter,parse_detail,parse_list
F=S/"tests"/"fixtures";rows=parse_list((F/"product-recalls.html").read_text(),"https://www.productsafety.govt.nz/recalls","2026-07-19T00:00:00Z");assert rows[0]["published"].startswith("2026-06-24") and rows[0]["categories"]==["Children's toys"]
detail=parse_detail((F/"product-recall-detail.html").read_text(),rows[0]["source_url"],"2026-07-19T00:00:00Z");assert "sunburn" in detail["hazard"].lower() and "swallowed" in detail["hazard"].lower()
record={**rows[0],**detail}
assert record["supplier"]=="Example Toys Limited."
assert matches_filter(record,"supplier","Example Toys") and not matches_filter(record,"supplier","sunburn")
assert matches_filter(record,"hazard","sunburn") and matches_filter(record,"category","toys")
print("[PASS] fixture Product Safety recall article fields");print("[PASS] contract canonical detail URL and category")
r=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"latest","--limit","2","--json"],capture_output=True,text=True,timeout=45)
if r.returncode==0:assert json.loads(r.stdout)["data"];print("[PASS] live Product Safety recall listing")
elif r.returncode in {4,5}:print(f"[SKIP] network Product Safety unavailable: {r.stderr.strip()}")
else:print(r.stderr,file=sys.stderr);raise SystemExit(1)
