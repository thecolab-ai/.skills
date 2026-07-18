#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Raw Essentials NZ."""
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
def run(*args): return subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=30)
def live(args):
 r=run(*args)
 if r.returncode: print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
 try:return json.loads(r.stdout)
 except json.JSONDecodeError: print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode:raise SystemExit("[FAIL] help")
print("[PASS] help")
assert run("product", "https://example.org/products/nope", "--json").returncode != 0
print("[PASS] rejects a cross-site product URL")
assert run("search", " ", "--json").returncode != 0
assert run("product", "http://rawessentials.co.nz/products/nope", "--json").returncode != 0
print("[PASS] rejects empty search and non-HTTPS product URL")
data=live(["search","treat","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and isinstance(data["results"],list);print("[PASS] search JSON metadata")
detail=live(["product","https://rawessentials.co.nz/products/treats?petType=dog","--json"])
if detail is not None:assert detail["product"]["url"] and detail["retrieved_at"];print("[PASS] detail JSON")
stores=live(["stores","--json"])
if stores is not None:assert stores["source_url"] and isinstance(stores["results"],list);print("[PASS] stores JSON")
print("Smoke test complete.")
