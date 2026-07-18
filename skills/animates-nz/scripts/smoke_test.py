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


fixture = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","@id":"https://www.animates.co.nz/test.html","name":"Fixture Dog Food","sku":"TEST-1","brand":{"@type":"Brand","name":"Fixture"},"offers":{"@type":"Offer","price":"19.95","priceCurrency":"NZD","availability":"https://schema.org/InStock"}}</script>'''
parsed = cli.parse_product(fixture, "https://www.animates.co.nz/test.html")
check("fixture Product JSON-LD parses", bool(parsed and parsed["name"] == "Fixture Dog Food" and parsed["price"] == 19.95 and parsed["in_stock"] is True))
entity_fixture = '<script type="application/ld+json">{"@type":"Product","name":"A &quot; B"}</script>'
check("JSON-LD script data is not HTML-unescaped", cli.json_ld_objects(entity_fixture)[0]["name"] == "A &quot; B")
check("rejects non-storefront and non-HTTPS URLs", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://www.animates.co.nz/x"))
check("empty HTML is not fabricated success", cli.parse_product("<html></html>", "https://example.invalid") is None)
help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("timeout is bounded", run("--timeout", "61", "search", "dog").returncode != 0)

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
