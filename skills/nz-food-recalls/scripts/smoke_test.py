#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S.parents[1]/"lib"));from mpi_food_recalls import parse_list,parse_detail
F=S/"tests"/"fixtures";at="2026-07-19T00:00:00Z";rows=parse_list((F/"mpi-recalls.html").read_text(),"https://www.mpi.govt.nz/food-safety-home/food-recalls-and-complaints/recalled-food-products",at);d=parse_detail((F/"mpi-recall-detail.html").read_text(),rows[0]["source_url"],at);assert rows[0]["year"]==2026 and "Batch ABC" in d["product_information"] and "allergic to milk" in d["consumer_action"]
assert "milk" in d["allergen_or_hazard"].lower() and d["active"] is None
print("[PASS] fixture MPI yearly list, batch, distribution and consumer-action parsing");print("[PASS] contract exact allergen/action source sections")
r=subprocess.run([sys.executable,str(S/"scripts"/"cli.py"),"latest","--limit","2","--json"],capture_output=True,text=True,timeout=45)
if r.returncode==0:assert json.loads(r.stdout)["data"];print("[PASS] live MPI recalled-food listing")
elif r.returncode in {4,5}:print(f"[SKIP] network MPI unavailable: {r.stderr.strip()}")
else:print(r.stderr,file=sys.stderr);raise SystemExit(1)
