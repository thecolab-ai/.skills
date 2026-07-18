#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for baby-factory-nz."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
spec = importlib.util.spec_from_file_location("baby_factory_cli", CLI)
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
        cli.fetch_text(cli.BASE + "/test")
    except cli.CliError:
        return True
    finally:
        cli.urllib.request.build_opener = original
    return False


state_fixture = '<script>window.category = {"items":[{"productid":1,"style":"S1","description":"Fixture Seat","label":"Fixture","stylecolour":{"colour":"black","urlkey":"fixture-seat","variants":[{"barcode":"123","size":"One Size","currency":"NZD","baseunitprice":"199.00","unitprice":"149.00","saleprice":true}]}}],"totalitems":1,"totalpages":1,"currentpage":1};</script>'
state = cli.extract_category_state(state_fixture)
item = cli.normalize_search_item(state["items"][0])
check("fixture category state parses prices", item["name"] == "Fixture Seat" and item["price"] == 149.0 and item["on_sale"] is True)
check("non-finite and negative prices fail closed", cli.number("nan") is None and cli.number(-0.01) is None)
entity_fixture = '<script type="application/ld+json">{"@type":"Product","name":"A &quot; B"}</script>'
check("JSON-LD script data is not HTML-unescaped", cli.json_ld_objects(entity_fixture)[0]["name"] == "A &quot; B")
try:
    cli.extract_category_state("<html></html>")
    missing_rejected = False
except cli.CliError:
    missing_rejected = True
check("missing state is not fabricated success", missing_rejected)
try:
    cli.extract_category_state('<script>window.category = {};</script>')
    malformed_rejected = False
except cli.CliError:
    malformed_rejected = True
check("malformed present state is not fabricated no-match", malformed_rejected)
check("rejects non-canonical storefront origins", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://www.babyfactory.co.nz/x") and not cli.is_allowed_url("https://user@www.babyfactory.co.nz/x") and not cli.is_allowed_url("https://www.babyfactory.co.nz:444/x") and cli.is_allowed_url("https://www.babyfactory.co.nz:443/x"))
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
check("page and timeout are bounded", run("search", "seat", "--page", "51").returncode != 0 and run("--timeout", "61", "search", "seat").returncode != 0)
check("empty search query is rejected", run("search", " ", "--json").returncode != 0)
captured_url = ""
original_fetch_text = cli.fetch_text
def fake_search_page(url: str, timeout: int = 10):
    global captured_url
    captured_url = url
    return '<script>window.category = {"items":[],"totalitems":0,"totalpages":0,"currentpage":2};</script>', url
setattr(cli, "fetch_text", fake_search_page)
try:
    empty = cli.search("no match", 1, 2, 1)
finally:
    setattr(cli, "fetch_text", original_fetch_text)
check("search uses the retailer p parameter", urllib.parse.parse_qs(urllib.parse.urlparse(captured_url).query).get("p") == ["2"])
check("legitimate no-match is empty success", empty["results"] == [] and empty["count"] == 0)
no_match_markup = '<p class="category__search-subheading">Sorry, we couldn&apos;t find any products to match your search.</p>'
setattr(cli, "fetch_text", lambda url, timeout=10: (no_match_markup, url))
try:
    decoded_empty = cli.search("no match", 1, 1, 1)
finally:
    setattr(cli, "fetch_text", original_fetch_text)
check("HTML-encoded no-match message is recognized", decoded_empty["results"] == [] and decoded_empty["count"] == 0)

live = run("search", "car seat", "--limit", "1", "--json")
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
                check("live snapshot has offers and price", isinstance(snapshot.get("price"), (int, float)) and bool(snapshot.get("offers")))

print(f"{FAILURES} failure(s), {SKIPS} outage skip(s)")
raise SystemExit(1 if FAILURES else 0)
