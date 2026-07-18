#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for animates-nz."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=45)


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
check("non-finite and negative prices fail closed", cli.as_number("nan") is None and cli.as_number(-0.01) is None)
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
        check("live search is non-empty and evidenced", bool(results and data.get("source_url") and data.get("retrieved_at")))
        if results:
            snap = run("price-snapshot", str(results[0]["source_url"]), "--json")
            check("live price snapshot exits zero", snap.returncode == 0, snap.stderr[:300])
            if snap.returncode == 0:
                snapshot = json.loads(snap.stdout)
                check("live snapshot has a real price", isinstance(snapshot.get("price"), (int, float)) and bool(snapshot.get("source_url")))

print(f"{FAILURES} failure(s), {SKIPS} outage skip(s)")
raise SystemExit(1 if FAILURES else 0)
