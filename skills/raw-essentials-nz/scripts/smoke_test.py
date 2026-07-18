#!/usr/bin/env python3
"""Live, outage-tolerant smoke tests for Raw Essentials NZ."""
import importlib.util, json, subprocess, sys
from pathlib import Path
CLI=Path(__file__).with_name("cli.py")
OUTAGE_MARKERS=("network error","timed out","http 429","http 500","http 502","http 503","http 504")
FAILURE_MARKERS=("traceback","jsondecodeerror","malformed json","parser error","response shape","deterministic failure")
def is_outage(detail):
 detail=detail.lower()
 return not any(marker in detail for marker in FAILURE_MARKERS) and any(marker in detail for marker in OUTAGE_MARKERS)
assert is_outage("timed out while opening storefront")
for failure in FAILURE_MARKERS:assert not is_outage(f"HTTP 500 followed by {failure}")
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
 if r.returncode:
  detail=(r.stderr+r.stdout).lower()
  if is_outage(detail):print("[SKIP] live endpoint unavailable:",r.stderr.strip()[:180]);return None
  raise SystemExit(f"[FAIL] live command failed ({r.returncode}): {r.stderr[:300]}")
 try:return json.loads(r.stdout)
 except json.JSONDecodeError: print("[FAIL] invalid JSON:",r.stdout[:180]);raise SystemExit(1)
if run("--help").returncode:raise SystemExit("[FAIL] help")
print("[PASS] help")
assert cli.allowed(cli.BASE+":443/test") and not cli.allowed("https://user@rawessentials.co.nz/test") and not cli.allowed(cli.BASE+":444/test")
try:cli.StorefrontRedirectHandler().redirect_request(None,None,302,"",{},"https://example.org/test");raise AssertionError("foreign redirect allowed")
except cli.CliError:pass
assert fetch_rejected("https://example.org/test") and fetch_rejected(cli.BASE+"/test")
print("[PASS] canonical origin, redirect, final URL and response-size boundaries")
assert run("product", "https://example.org/product/nope", "--json").returncode != 0
print("[PASS] rejects a cross-site product URL")
assert run("search", " ", "--json").returncode != 0
assert run("product", "http://rawessentials.co.nz/product/nope", "--json").returncode != 0
print("[PASS] rejects empty search and non-HTTPS product URL")
fixture='<a href="/products/p2">2</a><a href="/product/example"><img alt=""></a><h4><a href="/product/example">Example Product</a></h4>'
assert cli.links(fixture,cli.BASE)==[{"title":"Example Product","url":cli.BASE+"/product/example"}]
print("[PASS] catalogue parser excludes pagination and retains product titles")
assert cli.catalogue_url("chicken", "dog", 2).startswith(cli.BASE+"/products/p2?")
store_fixture='<a href="/p/raw-essentials-grey-lynn">Grey Lynn</a><a href="/stores">Stores</a>'
assert cli.store_links(store_fixture,cli.BASE)==[{"name":"Grey Lynn","url":cli.BASE+"/p/raw-essentials-grey-lynn"}]
print("[PASS] catalogue pagination path and store-location links are parsed")
price_fixture='''<script type="application/ld+json">{"@type":"Product","offers":{"@type":"Offer","price":"9.69","priceCurrency":"NZD"}}</script>'''
assert cli.product_price(price_fixture)==(9.69,"NZ$9.69")
assert cli.product_price(price_fixture.replace('"priceCurrency":"NZD"',''))==(None,None)
assert cli.amount("1,234.56")==1234.56 and cli.amount("1,2,3") is None
assert cli.amount("١٢٣.٤٥") is None
huge_price=10**10000
assert cli.amount(huge_price) is None
fallback_fixture='''<meta property="product:price:amount" content="7.25"><meta property="product:price:currency" content="NZD">'''
hostile_json="["*(sys.getrecursionlimit()+10)+"0"+"]"*(sys.getrecursionlimit()+10)
assert cli.product_price(f'<script type="application/ld+json">{hostile_json}</script>'+fallback_fixture)==(7.25,"NZ$7.25")
original_json_loads=cli.json.loads
try:
 cli.json.loads=lambda raw:{"@type":"Product","offers":{"price":huge_price,"priceCurrency":"NZD"}}
 assert cli.product_price('<script type="application/ld+json">{}</script>')==(None,None)
 cli.json.loads=lambda raw:(_ for _ in ()).throw(ValueError("decoder rejected structure"))
 assert cli.product_price('<script type="application/ld+json">{}</script>'+fallback_fixture)==(7.25,"NZ$7.25")
finally:cli.json.loads=original_json_loads
print("[PASS] Product JSON-LD yields price only with explicit NZD evidence")
data=live(["search","chicken","--limit","2","--json"])
if data is not None:
 assert data["source_url"] and data["retrieved_at"] and data["results"] and all("/product/" in row["url"] for row in data["results"]);print("[PASS] search JSON metadata and product links")
detail=live(["product","https://rawessentials.co.nz/product/raw-essentials-chicken-venison-mix","--json"])
if detail is not None:
 assert detail["product"]["url"] and detail["retrieved_at"]
 assert isinstance(detail["product"]["price_nzd"],(int,float)) and detail["product"]["price_nzd"]>0
 assert detail["product"]["price_text"] not in (None,"$",[])
 print("[PASS] detail JSON with evidenced NZD price")
stores=live(["stores","--json"])
if stores is not None:assert stores["source_url"] and isinstance(stores["results"],list);print("[PASS] stores JSON")
print("Smoke test complete.")
