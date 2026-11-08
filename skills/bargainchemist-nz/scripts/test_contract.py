#!/usr/bin/env python3
"""Deterministic repository contract test and product fallback checks for this skill."""
import importlib.util
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402

spec = importlib.util.spec_from_file_location("bargainchemist_contract_cli", Path(__file__).with_name("cli.py"))
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)


def fixture_checks() -> None:
    handle = "fixture-tablets"
    boost_item = {"handle": handle, "title": "Fixture Tablets", "variants": [{"id": 1, "price": "12.99", "available": True}]}

    def blocked_shopify(url, params=None, timeout=25):
        if url.endswith(".js"):
            raise cli.ApiError(f"network error calling {url}: blocked (HTTP 429)")
        return {"products": [boost_item], "total_product": 1}, "https://example.org/search"

    original = cli.request_json
    cli.request_json = blocked_shopify
    try:
        result = cli.product_detail(handle)
    finally:
        cli.request_json = original
    assert result["source"] == "boost-commerce-search" and result["product"]["handle"] == handle
    assert "HTTP 429" in result["fallback_reason"] and result["fallback"]
    print("[PASS] Boost fallback keeps the Shopify product JSON error")


if __name__ == "__main__":
    fixture_checks()
    raise SystemExit(run_contract_test(SKILL))
