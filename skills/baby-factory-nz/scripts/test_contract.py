#!/usr/bin/env python3
"""Deterministic repository contract test and product JSON-LD fixture checks for this skill."""
import importlib.util
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402

spec = importlib.util.spec_from_file_location("baby_factory_cli", Path(__file__).with_name("cli.py"))
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def fixture_checks() -> None:
    markup = (SKILL / "tests" / "fixtures" / "product-group.html").read_text(encoding="utf-8")
    url = cli.BASE + "/fixture-dome-car-seat-9000001-jet"
    original = cli.fetch_text
    cli.fetch_text = lambda value, timeout=10: (markup, url)
    try:
        product, source_url = cli.get_product(url, 10)
    finally:
        cli.fetch_text = original
    assert source_url == url and product["source_url"] == url
    assert product["name"] == "Fixture Dome Car Seat" and product["brand"] == "Fixture Brand"
    assert product["sku"] == "9000001" and product["description"] == "Fixture & seat"
    assert product["image"] == "https://www.babyfactory.co.nz/content/products/fixture-jet.png"
    assert [offer["sku"] for offer in product["offers"]] == ["9000001|jet", "9000001|slate"]
    assert product["price"] == 249.5 and product["availability"] == "OutOfStock"
    print("[PASS] fixture ProductGroup JSON-LD flattens variant offers")

    empty_group = '<script type="application/ld+json">{"@type": "ProductGroup", "name": "No offers", "hasVariant": []}</script>'
    cli.fetch_text = lambda value, timeout=10: (empty_group, url)
    try:
        cli.get_product(url, 10)
    except cli.CliError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("ProductGroup without priced variants was accepted")
    finally:
        cli.fetch_text = original
    print("[PASS] ProductGroup without priced variants fails closed")


if __name__ == "__main__":
    fixture_checks()
    raise SystemExit(run_contract_test(SKILL))
