#!/usr/bin/env python3
"""Fixture and outage-tolerant live checks for petdirect-nz."""
from __future__ import annotations

import importlib.util
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


state_fixture = '<script>window.__SERVER_STATE__ = {"initialResults":{"idx":{"results":[{"hits":[{"objectID":"1","name":"Fixture Food","bcCustomUrl":"/p/fixture/","cheapestVariant":{"discountedUnitPrice":1299,"rrpPrice":1499,"isInStock":true},"variants":[]}],"nbHits":1,"nbPages":1}]}}}; window.__LOCATION__ = "x";</script>'
result_set = cli.search_result(cli.extract_server_state(state_fixture))
item = cli.normalize_hit(result_set["hits"][0])
check("fixture search state parses cents", item["name"] == "Fixture Food" and item["price"] == 12.99 and item["in_stock"] is True)
try:
    cli.extract_server_state("<html></html>")
    missing_rejected = False
except cli.CliError:
    missing_rejected = True
check("missing state is not fabricated success", missing_rejected)
check("rejects non-storefront and non-HTTPS URLs", not cli.is_allowed_url("https://example.org/x") and not cli.is_allowed_url("http://petdirect.co.nz/x"))
help_result = run("--help")
check("--help exits zero", help_result.returncode == 0, help_result.stderr[:200])
check("page and timeout are bounded", run("search", "food", "--page", "51").returncode != 0 and run("--timeout", "61", "search", "food").returncode != 0)

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
