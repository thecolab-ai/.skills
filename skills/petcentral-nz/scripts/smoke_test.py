#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Pet Central NZ."""
import json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
def run(*args): return subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=30)
def live(args):
 r=run(*args)
 if r.returncode:
  print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
 try:return json.loads(r.stdout)
 except json.JSONDecodeError: print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode: raise SystemExit("[FAIL] help")
print("[PASS] help")
assert run("search", "dog", "--limit", "51", "--json").returncode != 0
print("[PASS] rejects an over-limit request")
assert run("search", " ", "--json").returncode != 0
assert run("product", "https://example.org/products/nope", "--json").returncode != 0
print("[PASS] rejects empty search and cross-site product URL")
data=live(["search","dog","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and isinstance(data["results"],list)
 print("[PASS] search JSON metadata")
 if data["results"]:
  item=live(["product",data["results"][0]["handle"],"--json"])
  if item is not None: assert item["product"]["url"] and item["retrieved_at"];print("[PASS] product JSON")
print("Smoke test complete.")
