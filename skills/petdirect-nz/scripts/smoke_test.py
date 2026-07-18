#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for petdirect-nz."""
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
spec = importlib.util.spec_from_file_location("petdirect_cli", CLI)
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
FAILURES = 0
SKIPS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global FAILURES
    if condition:
        print(f"[PASS] {name}")
    else:
        FAILURES += 1
        print(f"[FAIL] {name}: {detail}")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=45)


def outage(result: subprocess.CompletedProcess[str]) -> bool:
    text = result.stderr.lower()
    return any(marker in text for marker in ("network error", "timed out", "http 429", "http 500", "http 502", "http 503", "http 504"))


class FakeResponse:
    def __init__(self, final_url: str): self.final_url = final_url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.final_url
    def read(self, size: int): return b"x" * size


class FakeOpener:
    def __init__(self, final_url: str): self.final_url = final_url
    def open(self, request, timeout): return FakeResponse(self.final_url)


def fetch_rejected(final_url: str) -> bool:
    original = cli.urllib.request.build_opener
    cli.urllib.request.build_opener = lambda *handlers: FakeOpener(final_url)
    try:
        cli.fetch_text(cli.BASE + "/test", max_bytes=8)
    except cli.CliError:
        return True
    finally:
        cli.urllib.request.build_opener = original
    return False


state_fixture = '<script>window.__SERVER_STATE__ = {"initialResults":{"idx":{"results":[{"hits":[{"objectID":"1","name":"Fixture Food","bcCustomUrl":"/p/fixture/","cheapestVariant":{"discountedUnitPrice":1299,"rrpPrice":1499,"isInStock":true},"variants":[]}],"nbHits":1,"nbPages":1}]}}}; window.__LOCATION__ = "x";</script>'
result_set = cli.search_result(cli.extract_server_state(state_fixture))
item = cli.normalize_hit(result_set["hits"][0])
check("fixture search state parses cents", item["name"] == "Fixture Food" and item["price"] == 12.99 and item["in_stock"] is True)
entity_fixture = '<script type="application/ld+json">{"@type":"Product","name":"A &quot; B"}</script>'
check("JSON-LD script data is not HTML-unescaped", cli.json_ld_objects(entity_fixture)[0]["name"] == "A &quot; B")
try:
    cli.extract_server_state("<html></html>")
    missing_rejected = False
except cli.CliError:
    missing_rejected = True
check("missing state is not fabricated success", missing_rejected)
check("rejects non-canonical storefront origins", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://petdirect.co.nz/x") and not cli.is_allowed_url("https://user@petdirect.co.nz/x") and not cli.is_allowed_url("https://petdirect.co.nz:444/x") and cli.is_allowed_url("https://petdirect.co.nz:443/x"))
try:
    cli.StorefrontRedirectHandler().redirect_request(None, None, 302, "", {}, "https://example.org/x")
    redirect_rejected = False
except cli.CliError:
    redirect_rejected = True
check("redirect interception rejects foreign origins", redirect_rejected)
check("final URL rejection is enforced", fetch_rejected("https://example.org/x"))
check("oversized responses are rejected", fetch_rejected(cli.BASE + "/test"))
help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("page and timeout are bounded", run("search", "food", "--page", "51").returncode != 0 and run("--timeout", "61", "search", "food").returncode != 0)
check("empty search query is rejected", run("search", " ", "--json").returncode != 0)
product_state_fixture = '<script>window.__PRODUCT__ = {"variants":[{"sku":"MEMBER-1","discountedUnitPrice":5099,"rrpPrice":5999,"isMemberPrice":true,"isInStock":true}]};</script>'
ld_fixture = {"@type":"ProductGroup","name":"Fixture Food","hasVariant":[{"@type":"Product","sku":"MEMBER-1","name":"3kg","offers":{"price":"40.00","priceCurrency":"NZD","availability":"https://schema.org/InStock"}}]}
normalized = cli.normalize_ld_product(ld_fixture, cli.BASE+"/p/fixture/")
cli.apply_product_state(normalized, cli.extract_product_state(product_state_fixture))
check("member state overrides mismatched JSON-LD price", normalized["variants"][0]["price"] == 50.99 and normalized["variants"][0]["rrp"] == 59.99 and normalized["variants"][0]["member_price"] is True)
plain = io.StringIO()
with contextlib.redirect_stdout(plain):
    cli.emit({"command":"price-snapshot","name":"Fixture Food","price":50.99,"rrp":59.99,"member_price":True,"currency":"NZD","source_url":"https://petdirect.co.nz/p/fixture/"}, False)
check("plain output labels member price and RRP", "Pet Perks member price" in plain.getvalue() and "RRP $59.99" in plain.getvalue())

live = run("search", "dog food", "--limit", "1", "--json")
if live.returncode and outage(live):
    SKIPS += 1
    print(f"[SKIP] live search: upstream unavailable ({live.stderr.strip()[:180]})")
else:
    check("live search exits zero", live.returncode == 0, live.stderr[:300])
    if live.returncode == 0:
        data = json.loads(live.stdout)
        results = data.get("results")
        check("live search is non-empty and evidenced", bool(results and data.get("source_url") and data.get("retrieved_at")))
        if results:
            snap = run("price-snapshot", str(results[0]["source_url"]), "--json")
            check("live price snapshot exits zero", snap.returncode == 0, snap.stderr[:300])
            if snap.returncode == 0:
                snapshot = json.loads(snap.stdout)
                check("live snapshot has variants and price", isinstance(snapshot.get("price"), (int, float)) and bool(snapshot.get("variants")))

print(f"{FAILURES} failure(s), {SKIPS} outage skip(s)")
raise SystemExit(1 if FAILURES else 0)
