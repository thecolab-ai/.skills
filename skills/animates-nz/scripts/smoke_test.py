#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for animates-nz."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

CLI = Path(__file__).with_name("cli.py")
spec = importlib.util.spec_from_file_location("animates_cli", CLI)
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
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=45, check=False)


def outage(result: subprocess.CompletedProcess[str]) -> bool:
    text = result.stderr.lower()
    return any(marker in text for marker in ("network error", "timed out", "http 429", "http 500", "http 502", "http 503", "http 504"))


class FakeResponse:
    def __init__(self, final_url: str):
        self.final_url = final_url
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


fixture = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","@id":"https://www.animates.co.nz/test.html","name":"Fixture Dog Food","sku":"TEST-1","brand":{"@type":"Brand","name":"Fixture"},"offers":{"@type":"Offer","price":"19.95","priceCurrency":"NZD","availability":"https://schema.org/InStock"}}</script>'''
parsed = cli.parse_product(fixture, "https://www.animates.co.nz/test.html")
check("fixture Product JSON-LD parses", bool(parsed and parsed["name"] == "Fixture Dog Food" and parsed["price"] == 19.95 and parsed["in_stock"] is True))
check("boolean, non-finite and negative prices fail closed", cli.as_number(True) is None and cli.as_number("nan") is None and cli.as_number(-0.01) is None)
boolean_price_fixture = '''<script type="application/ld+json">{"@type":"Product","name":"Invalid Price","offers":{"price":true}}</script>'''
boolean_price_product = cli.parse_product(boolean_price_fixture, "https://www.animates.co.nz/invalid.html")
check("boolean JSON-LD price remains incomplete", bool(boolean_price_product and boolean_price_product["price"] is None))
aggregate_offer_fixture = '''<script type="application/ld+json">{"@type":"Product","@id":"https://www.animates.co.nz/bundle.html","name":"Bundle Example","offers":{"@type":"AggregateOffer","lowPrice":"60.27","highPrice":"60.27","priceCurrency":"NZD","offers":[{"@type":"Offer","url":"https://www.animates.co.nz/bundle.html","price":"60.27","priceCurrency":"NZD","availability":"http://schema.org/OutOfStock"}]}}</script>'''
aggregate_offer_product = cli.parse_product(aggregate_offer_fixture, "https://www.animates.co.nz/bundle.html")
check("aggregate JSON-LD offers parse", bool(aggregate_offer_product and aggregate_offer_product["price"] == 60.27 and aggregate_offer_product["availability"] == "OutOfStock" and aggregate_offer_product["source_url"].endswith("bundle.html")))
original_fetch_text = cli.fetch_text
cli_any = cast(Any, cli)
cli_any.fetch_text = lambda url, timeout=10, max_bytes=cli.MAX_PAGE_BYTES: (aggregate_offer_fixture, url)
try:
    bundle_product, _ = cli.get_product("https://www.animates.co.nz/bundle.html", 10)
    aggregate_offer_rejected = not (bundle_product.get("price") == 60.27 and bundle_product.get("availability") == "OutOfStock")
except cli.CliError:
    aggregate_offer_rejected = True
finally:
    cli_any.fetch_text = original_fetch_text
check("complete-product validation accepts aggregate offers", not aggregate_offer_rejected)
original_fetch_text = cli.fetch_text
cli_any.fetch_text = lambda url, timeout=10, max_bytes=cli.MAX_PAGE_BYTES: (boolean_price_fixture, url)
try:
    cli.get_product("https://www.animates.co.nz/invalid.html", 10)
    boolean_price_rejected = False
except cli.CliError:
    boolean_price_rejected = True
finally:
    cli_any.fetch_text = original_fetch_text
check("complete-product validation rejects boolean JSON-LD price", boolean_price_rejected)
entity_fixture = '<script type="application/ld+json">{"@type":"Product","name":"A &quot; B"}</script>'
check("JSON-LD script data is not HTML-unescaped", cli.json_ld_objects(entity_fixture)[0]["name"] == "A &quot; B")
check("rejects non-canonical storefront origins", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://www.animates.co.nz/x") and not cli.is_allowed_url("https://user@www.animates.co.nz/x") and not cli.is_allowed_url("https://www.animates.co.nz:444/x") and cli.is_allowed_url("https://www.animates.co.nz:443/x"))
try:
    cli.StorefrontRedirectHandler().redirect_request(None, None, 302, "", {}, "https://example.org/x")
    redirect_rejected = False
except cli.CliError:
    redirect_rejected = True
check("redirect interception rejects foreign origins", redirect_rejected)
check("final URL rejection is enforced", fetch_rejected("https://example.org/x"))
check("oversized responses are rejected", fetch_rejected(cli.BASE + "/test"))
check("empty HTML is not fabricated success", cli.parse_product("<html></html>", "https://example.invalid") is None)


# Sitemap fallback: since 30 Oct 2026 Magento quick search returns total_count 0 for
# every query, so search falls back to the public product sitemap (robots-allowed).
import gzip as _gzip
import io as _io

SITEMAP_INDEX_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?><sitemapindex>
<sitemap><loc>https://www.animates.co.nz/media/sitemapcategory.xml</loc></sitemap>
<sitemap><loc>https://www.animates.co.nz/media/sitemapproduct.xml</loc></sitemap></sitemapindex>"""
SITEMAP_PRODUCTS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?><urlset>
<url><loc>https://www.animates.co.nz/flukers-freeze-dried-crickets-457g.html</loc><image:image><image:title>Fluker&#039;s Freeze Dried Crickets 34g</image:title></image:image></url>
<url><loc>https://example.org/royal-canin-dog-food.html</loc></url>
<url><loc>https://www.animates.co.nz/royal-canin-beagle-adult-dog-food-3kg.html</loc><image:image><image:title>Royal Canin Beagle Adult Dog Food 3kg</image:title></image:image></url>
<url><loc>https://www.animates.co.nz/hills-adult-cat-food-2kg.html</loc></url>
<url><loc>https://www.animates.co.nz/k9-natural-lamb-1kg.html</loc><image:image><image:title>K9 Natural Lamb Dog Food 1kg</image:title></image:image></url>
</urlset>"""
PRODUCT_PAGE_FIXTURE = '<script type="application/ld+json">{"@type":"Product","name":"Royal Canin Beagle Adult Dog Food 3kg","sku":"RC-1","offers":{"@type":"Offer","price":"54.99","priceCurrency":"NZD","availability":"https://schema.org/InStock"}}</script>'


class FixtureStream:
    def __init__(self, url: str, body: bytes, encoding: str = ""):
        self.url, self.body, self.headers = url, _io.BytesIO(body), {"Content-Encoding": encoding}
        self.reads = 0
    def geturl(self): return self.url
    def read(self, size: int = -1):
        self.reads += 1
        return self.body.read(size)
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): return False


class FixtureSite:
    """Fake opener serving the storefront fixture; records every requested URL."""
    def __init__(self, search_payload: dict, gzip_sitemap: bool = True):
        self.search_payload, self.gzip_sitemap, self.requested = search_payload, gzip_sitemap, []
    def open(self, request, timeout):
        url = request.full_url
        self.requested.append(url)
        if url.startswith(cli.SEARCH_API):
            return FixtureStream(url, json.dumps(self.search_payload).encode())
        if url == cli.SITEMAP_INDEX:
            return FixtureStream(url, SITEMAP_INDEX_FIXTURE.encode())
        if url.endswith("/media/sitemapproduct.xml"):
            raw = SITEMAP_PRODUCTS_FIXTURE.encode()
            if self.gzip_sitemap and request.get_header("Accept-encoding") == "gzip":
                return FixtureStream(url, _gzip.compress(raw), "gzip")
            return FixtureStream(url, raw)
        if url.endswith(".html") or "/catalog/product/view/id/" in url:
            return FixtureStream(url, PRODUCT_PAGE_FIXTURE.encode())
        raise AssertionError(f"unexpected fixture request {url}")


def with_site(site: FixtureSite, fn):
    original = cli.urllib.request.build_opener
    cli.urllib.request.build_opener = lambda *handlers: site
    try:
        return fn()
    finally:
        cli.urllib.request.build_opener = original


for gz in (True, False):
    site = FixtureSite({"items": [], "total_count": 0}, gzip_sitemap=gz)
    data = with_site(site, lambda: cli.search("Dog Foods", 2, 10))
    urls = [item["source_url"] for item in data["results"]]
    check(
        f"fixture zero Magento matches fall back to the product sitemap ({'gzip' if gz else 'plain'})",
        data["search_source"] == "sitemap_fallback" and data["total"] == 0 and data["count"] == 2
        and urls == ["https://www.animates.co.nz/royal-canin-beagle-adult-dog-food-3kg.html", "https://www.animates.co.nz/k9-natural-lamb-1kg.html"]
        and any("not relevance ranked" in w for w in data["warnings"])
        and data["source_urls"][0].startswith(cli.SEARCH_API) and data["source_url"].endswith("/media/sitemapproduct.xml")
        and not any("catalogsearch" in u or "example.org" in u for u in site.requested),
        json.dumps({"urls": urls, "data": {k: data.get(k) for k in ("search_source", "total", "count", "warnings")}, "requested": site.requested})[:600],
    )

site = FixtureSite({"items": [{"id": 42}], "total_count": 1})
data = with_site(site, lambda: cli.search("dog food", 1, 10))
check("fixture Magento matches do not touch the sitemap", data["search_source"] == "magento_search" and data["count"] == 1 and data["results"][0]["product_id"] == "42" and not any("sitemap" in u for u in site.requested), json.dumps(site.requested))

site = FixtureSite({"items": [], "total_count": 0})
data = with_site(site, lambda: cli.search("unicorn saddle", 3, 10))
check("fixture fallback with no sitemap match stays an empty result", data["count"] == 0 and data["search_source"] == "sitemap_fallback" and any("matched 0" in w for w in data["warnings"]), json.dumps(data["warnings"]))

bomb = FixtureSite({"items": [], "total_count": 0})
original_limit = cli.MAX_SITEMAP_XML_BYTES
cli.MAX_SITEMAP_XML_BYTES = 200
try:
    with_site(bomb, lambda: cli.search("no such product words", 3, 10))
    sitemap_capped = False
except cli.CliError as exc:
    sitemap_capped = "safety limit" in str(exc)
finally:
    cli.MAX_SITEMAP_XML_BYTES = original_limit
check("fixture sitemap decompression is capped", sitemap_capped)
check("fixture sitemap matching needs every query word", cli._url_block_match("<loc>https://www.animates.co.nz/hills-adult-cat-food-2kg.html</loc>", cli.query_tokens("dog food")) is None
      and cli._url_block_match("<loc>https://www.animates.co.nz/hills-adult-cat-food-2kg.html</loc>", cli.query_tokens("cat foods")) is not None)

help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("timeout is bounded", run("--timeout", "61", "search", "dog").returncode != 0)
check("empty search query is rejected", run("search", " ", "--json").returncode != 0)

live = run("search", "dog food", "--limit", "1", "--json")
if live.returncode and outage(live):
    SKIPS += 1
    print(f"[SKIP] live search: upstream unavailable ({live.stderr.strip()[:180]})")
else:
    check("live search exits zero", live.returncode == 0, live.stderr[:300])
    if live.returncode == 0:
        data = json.loads(live.stdout)
        results = data.get("results")
        evidence = {key: data.get(key) for key in ("count", "total", "warnings", "source_url", "retrieved_at")}
        check(
            "live search is non-empty and evidenced",
            bool(results and data.get("source_url") and data.get("retrieved_at")),
            "expected at least one parsed product with source_url and retrieved_at; got "
            + json.dumps(evidence, ensure_ascii=False)[:600],
        )
        print(f"  evidence: search_source={data.get('search_source')} total={data.get('total')} count={data.get('count')} warnings={json.dumps(data.get('warnings'), ensure_ascii=False)[:300]}")
        if results:
            snap = run("price-snapshot", str(results[0]["source_url"]), "--json")
            check("live price snapshot exits zero", snap.returncode == 0, snap.stderr[:300])
            if snap.returncode == 0:
                snapshot = json.loads(snap.stdout)
                check("live snapshot has a real price", isinstance(snapshot.get("price"), (int, float)) and bool(snapshot.get("source_url")))

print(f"{FAILURES} failure(s), {SKIPS} outage skip(s)")
raise SystemExit(1 if FAILURES else 0)
