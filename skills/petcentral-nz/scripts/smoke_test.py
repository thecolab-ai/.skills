#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Pet Central NZ."""
import importlib.util, json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
OUTAGE_MARKERS=("network error","timed out","http 429","http 500","http 502","http 503","http 504")
FAILURE_MARKERS=("traceback","jsondecodeerror","malformed json","parser error","response shape","deterministic failure")
def is_outage(detail):
 detail=detail.lower()
 return not any(marker in detail for marker in FAILURE_MARKERS) and any(marker in detail for marker in OUTAGE_MARKERS)
assert is_outage("HTTP 503: service unavailable")
for failure in FAILURE_MARKERS:assert not is_outage(f"HTTP 500 followed by {failure}")
spec=importlib.util.spec_from_file_location("petcentral_cli",CLI);assert spec and spec.loader
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
class FakeResponse:
 def __init__(self,url):self.url=url
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,size):return b"x"*size
class FakeOpener:
 def __init__(self,url):self.url=url
 def open(self,request,timeout):return FakeResponse(self.url)
def fetch_rejected(final_url):
 original=cli.urllib.request.build_opener;cli.urllib.request.build_opener=lambda *handlers:FakeOpener(final_url)
 try:cli.get(cli.BASE+"/test",1)
 except cli.CliError:return True
 finally:cli.urllib.request.build_opener=original
 return False
def run(*args): return subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=30)
def live(args):
 r=run(*args)
 if r.returncode:
  detail=(r.stderr+r.stdout).lower()
  if is_outage(detail):print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
  raise SystemExit(f"[FAIL] live command failed ({r.returncode}): {r.stderr[:300]}")
 try:return json.loads(r.stdout)
 except json.JSONDecodeError: print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode: raise SystemExit("[FAIL] help")
print("[PASS] contract help")
assert cli.allowed(cli.BASE+":443/test") and not cli.allowed("https://user@petcentral.co.nz/test") and not cli.allowed(cli.BASE+":444/test")
try:cli.StorefrontRedirectHandler().redirect_request(None,None,302,"",{},"https://example.org/test");raise AssertionError("foreign redirect allowed")
except cli.CliError:pass
assert fetch_rejected("https://example.org/test") and fetch_rejected(cli.BASE+"/test")
print("[PASS] contract canonical origin, redirect, final URL and response-size boundaries")
assert run("search", "dog", "--limit", "51", "--json").returncode != 0
print("[PASS] contract rejects an over-limit request")
assert run("search", " ", "--json").returncode != 0
assert run("product", "https://example.org/products/nope", "--json").returncode != 0
print("[PASS] contract rejects empty search and cross-site product URL")
priced=cli.product({"id":1,"title":"Priced","handle":"priced","variants":[{"id":11,"price":649},{"id":12,"price":7799}]})
assert priced["price_min_nzd"]==6.49 and priced["price_max_nzd"]==77.99
assert [variant["price_nzd"] for variant in priced["variants"]]==[6.49,77.99]
decimal=cli.product({"id":2,"title":"Decimal","handle":"decimal","variants":[{"id":21,"price":"6.49"}]})
assert decimal["price_min_nzd"]==6.49
try:cli.product({});raise AssertionError("malformed product accepted")
except cli.CliError:pass
try:cli.product({"id":3,"title":"Overflow","handle":"overflow","variants":[{"id":31,"price":10**10000}]});raise AssertionError("overflowing product price accepted")
except cli.CliError:pass
print("[PASS] fixture Shopify price units and malformed or overflowing product fail-closed behavior")
data=live(["search","dog","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and isinstance(data["results"],list)
 print("[PASS] live search JSON metadata")
 if data["results"]:
  item=live(["product",data["results"][0]["handle"],"--json"])
  if item is not None: assert item["product"]["url"] and item["retrieved_at"];print("[PASS] live product JSON")
print("Smoke test complete.")
