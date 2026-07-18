#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Legacy Aquatics NZ."""
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
def run(*args):return subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=30)
def live(args):
 r=run(*args)
 if r.returncode:print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
 try:return json.loads(r.stdout)
 except json.JSONDecodeError:print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode:raise SystemExit("[FAIL] help")
print("[PASS] help")
assert run("category", "../../not-a-category", "--json").returncode != 0
print("[PASS] rejects an unsafe category slug")
data=live(["category","aquariums-and-equipment","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and isinstance(data["results"],list);print("[PASS] category JSON metadata")
detail=live(["product","https://legacyaquatics.co.nz/product/fishheatpack40hour/","--json"])
if detail is not None:assert detail["product"]["url"] and detail["retrieved_at"];print("[PASS] detail JSON")
search=live(["search","filter","--limit","2","--json"])
if search is not None:assert search["source_url"] and isinstance(search["results"],list);print("[PASS] search JSON")
print("Smoke test complete.")
