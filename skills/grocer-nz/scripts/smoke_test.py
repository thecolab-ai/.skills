#!/usr/bin/env python3
"""Live smoke test for the grocer-nz skill."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


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
    stores = json.loads(run("stores", "--query", "Papakura", "--json"))
    names = {store["name"] for store in stores}
    assert "Woolworths Papakura" in names
    assert "PAK'nSAVE Papakura" in names
    assert "New World Papakura" in names

    search = run("search", "milk", "--store-query", "Papakura", "--limit", "2")
    assert "Anchor" in search
    assert "PAK'nSAVE Papakura" in search or "New World Papakura" in search

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

    # Query guard: a non-SELECT statement must be rejected (non-zero exit).
    rejected = subprocess.run(
        [sys.executable, str(CLI), "query", "drop table products", "--json"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    assert rejected.returncode != 0, "expected non-SELECT query to be rejected"

    print("grocer-nz smoke ok")


if __name__ == "__main__":
    main()
