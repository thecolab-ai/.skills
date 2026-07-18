#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for baby-factory-nz."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


state_fixture = '<script>window.category = {"items":[{"productid":1,"style":"S1","description":"Fixture Seat","label":"Fixture","stylecolour":{"colour":"black","urlkey":"fixture-seat","variants":[{"barcode":"123","size":"One Size","currency":"NZD","baseunitprice":"199.00","unitprice":"149.00","saleprice":true}]}}],"totalitems":1,"totalpages":1};</script>'
state = cli.extract_category_state(state_fixture)
item = cli.normalize_search_item(state["items"][0])
check("fixture category state parses prices", item["name"] == "Fixture Seat" and item["price"] == 149.0 and item["on_sale"] is True)
try:
    cli.extract_category_state("<html></html>")
    missing_rejected = False
except cli.CliError:
    missing_rejected = True
check("missing state is not fabricated success", missing_rejected)
check("rejects non-storefront and non-HTTPS URLs", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://www.babyfactory.co.nz/x"))
help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("page and timeout are bounded", run("search", "seat", "--page", "51").returncode != 0 and run("--timeout", "61", "search", "seat").returncode != 0)

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
