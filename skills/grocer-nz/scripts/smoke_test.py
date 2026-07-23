#!/usr/bin/env python3
"""Live smoke test for the grocer-nz skill."""
from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("grocer_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def main() -> None:
    cli = load_cli()
    assert cli.validate_select("select * from products") == "select * from products"
    try:
        cli.validate_select("drop table products")
    except SystemExit:
        pass
    else:
        raise AssertionError("non-SELECT SQL fixture was accepted")
    assert cli.bounded_limit(999) == cli.MAX_LIMIT and cli.bounded_offset(-1) == 0
    assert cli.normalize_gtin("94152210") == "00000094152210"
    assert cli.normalize_gtin("00 0000 9415 2210") == "00000094152210"
    assert cli.retailer_barcode("00000094152210") == "94152210"
    print("[PASS] fixture query guard, bounds, and GTIN normalisation")

    try:
        stores = json.loads(run("stores", "--query", "Papakura", "--json"))
    except AssertionError as exc:
        detail = str(exc).lower()
        if "failed to fetch" in detail or "dns error" in detail or "network error" in detail:
            print("[SKIP] grocer live assertions: dependency or upstream unavailable")
            return
        raise
    names = {store["name"] for store in stores}
    assert "Woolworths Papakura" in names
    assert "PAK'nSAVE Papakura" in names
    assert "New World Papakura" in names

    search = json.loads(run("search", "milk", "--store-query", "Papakura", "--limit", "2", "--json"))
    assert search["hits"]
    assert any(hit.get("barcodes") for hit in search["hits"])
    assert any(hit.get("retailer_search_terms") for hit in search["hits"])
    price_rows = [price for hit in search["hits"] for price in hit.get("prices", [])]
    assert any(
        price.get("store_name") in {"PAK'nSAVE Papakura", "New World Papakura"}
        for price in price_rows
    )

    barcode = json.loads(run("barcode", "94152210", "--json"))
    assert barcode["gtin"] == "00000094152210"
    assert barcode["matches"][0]["product_id"] == 5452
    assert "94152210" in barcode["matches"][0]["retailer_search_terms"]

    prices = run("prices", "5461", "--store-query", "Papakura", "--limit", "10")
    assert "PAK'nSAVE Papakura" in prices
    assert "$" in prices

    history = run("history", "5461", "--store-query", "Papakura", "--limit", "5")
    assert "$" in history
    assert "Papakura" in history

    # Guarded read-only query: a priced join returns rows.
    q = json.loads(run(
        "query",
        "select s.name, p.original_price_cent from prices p "
        "join stores s on s.id=p.store_id where p.product_id=5461 order by 2",
        "--store-query", "Papakura", "--json",
    ))
    assert q["row_count"] >= 1
    assert "prices" in q["available_relations"]
    assert "barcodes" in q["available_relations"]

    # Query guard: a non-SELECT statement must be rejected (non-zero exit).
    rejected = subprocess.run(
        [sys.executable, str(CLI), "query", "drop table products", "--json"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    assert rejected.returncode != 0, "expected non-SELECT query to be rejected"

    print("grocer-nz smoke ok")


if __name__ == "__main__":
    main()
