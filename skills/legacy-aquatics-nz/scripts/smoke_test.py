#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Legacy Aquatics NZ."""
import importlib.util, json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
OUTAGE_MARKERS=("network error","timed out","http 429","http 500","http 502","http 503","http 504")
spec=importlib.util.spec_from_file_location("legacy_aquatics_cli",CLI);assert spec and spec.loader
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
def run(*args):return subprocess.run([sys.executable,str(CLI),*args],capture_output=True,text=True,timeout=30)
def live(args):
 r=run(*args)
 if r.returncode:
  detail=(r.stderr+r.stdout).lower()
  if any(marker in detail for marker in OUTAGE_MARKERS):print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
  raise SystemExit(f"[FAIL] live command failed ({r.returncode}): {r.stderr[:300]}")
 try:return json.loads(r.stdout)
 except json.JSONDecodeError:print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode:raise SystemExit("[FAIL] help")
print("[PASS] help")
assert cli.allowed(cli.BASE+":443/test") and not cli.allowed("https://user@legacyaquatics.co.nz/test") and not cli.allowed(cli.BASE+":444/test")
try:cli.StorefrontRedirectHandler().redirect_request(None,None,302,"",{},"https://example.org/test");raise AssertionError("foreign redirect allowed")
except cli.CliError:pass
assert fetch_rejected("https://example.org/test") and fetch_rejected(cli.BASE+"/test")
print("[PASS] canonical origin, redirect, final URL and response-size boundaries")
assert run("category", "../../not-a-category", "--json").returncode != 0
print("[PASS] rejects an unsafe category slug")
assert run("search", " ", "--json").returncode != 0
assert run("product", "http://legacyaquatics.co.nz/product/nope/", "--json").returncode != 0
print("[PASS] rejects empty search and non-HTTPS product URL")
fixture='<a href="/product/example/"><img alt=""></a><h4><a href="/product/example/">Example Product</a></h4>'
assert cli.product_links(fixture,cli.BASE)==[{"title":"Example Product","url":cli.BASE+"/product/example/"}]
print("[PASS] duplicate product anchors retain the non-empty title")
data=live(["category","aquariums-and-equipment","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and data["results"] and all(row["title"] for row in data["results"]);print("[PASS] category JSON metadata and titles")
detail=live(["product","https://legacyaquatics.co.nz/product/fishheatpack40hour/","--json"])
if detail is not None:assert detail["product"]["url"] and detail["retrieved_at"];print("[PASS] detail JSON")
search=live(["search","filter","--limit","2","--json"])
if search is not None:assert search["source_url"] and isinstance(search["results"],list);print("[PASS] search JSON")
print("Smoke test complete.")
