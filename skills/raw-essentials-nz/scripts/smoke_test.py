#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Raw Essentials NZ."""
import importlib.util, json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
spec=importlib.util.spec_from_file_location("raw_essentials_cli",CLI);assert spec and spec.loader
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
 if r.returncode: print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
 try:return json.loads(r.stdout)
 except json.JSONDecodeError: print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode:raise SystemExit("[FAIL] help")
print("[PASS] help")
assert cli.allowed(cli.BASE+":443/test") and not cli.allowed("https://user@rawessentials.co.nz/test") and not cli.allowed(cli.BASE+":444/test")
try:cli.StorefrontRedirectHandler().redirect_request(None,None,302,"",{},"https://example.org/test");raise AssertionError("foreign redirect allowed")
except cli.CliError:pass
assert fetch_rejected("https://example.org/test") and fetch_rejected(cli.BASE+"/test")
print("[PASS] canonical origin, redirect, final URL and response-size boundaries")
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
