#!/usr/bin/env python3
"""Smoke tests for nz-angel-investment.

Network-backed checks skip cleanly when public source sites are unavailable.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def require_json(proc: subprocess.CompletedProcess[str]) -> dict:
    text = proc.stdout.strip() or proc.stderr.strip()
    return json.loads(text)


def main() -> int:
    help_proc = run(["--help"], timeout=20)
    expected_commands = ("ycf", "nzgcp-reports", "investors", "publications", "sources")
    if help_proc.returncode != 0 or any(cmd not in help_proc.stdout for cmd in expected_commands):
        print(help_proc.stdout)
        print(help_proc.stderr, file=sys.stderr)
        print("FAIL: --help did not expose expected commands", file=sys.stderr)
        return 1

    ycf_list = run(["ycf", "list", "--json"], timeout=20)
    if ycf_list.returncode != 0:
        print(ycf_list.stdout)
        print(ycf_list.stderr, file=sys.stderr)
        return 1
    data = json.loads(ycf_list.stdout)
    assert data["kind"] == "ycf_releases"
    assert data["count"] >= 1
    assert any(record["period"] == "2025" for record in data["records"])
    print(f"OK: ycf list returned {data['count']} curated releases")

    ycf_get = run(["ycf", "get", "2025", "--json"], timeout=20)
    if ycf_get.returncode != 0:
        print(ycf_get.stdout)
        print(ycf_get.stderr, file=sys.stderr)
        return 1
    data = json.loads(ycf_get.stdout)
    assert data["kind"] == "ycf_release"
    assert data["period"] == "2025"
    assert data["metrics"]["deal_count"] == 166
    assert data["metrics"]["investment_amount_nzd_millions"] == 754
    assert data["metrics"]["new_companies_funded"] == 47
    print("OK: ycf get returned curated 2025 metrics")

    sources = run(["sources", "--json"], timeout=20)
    if sources.returncode != 0:
        print(sources.stdout)
        print(sources.stderr, file=sys.stderr)
        return 1
    data = json.loads(sources.stdout)
    assert data["kind"] == "source_catalogue"
    assert any(source["name"] == "NZGCP Young Company Finance" for source in data["sources"])
    assert any(source["name"] == "Angel Association NZ members" for source in data["sources"])
    print(f"OK: sources returned {len(data['sources'])} source notes")

    bad_period = run(["ycf", "get", "not-a-period", "--json"], timeout=20)
    if bad_period.returncode == 0:
        print("FAIL: invalid YCF period unexpectedly succeeded", file=sys.stderr)
        return 1
    data = require_json(bad_period)
    assert data["error"] == "not_found"
    assert "not-a-period" in data["message"]
    print("OK: invalid YCF period returns a clear JSON error")

    investors = run(["investors", "--limit", "2", "--json"], timeout=90)
    if investors.returncode == 2:
        data = require_json(investors)
        if data.get("error") == "upstream_unavailable":
            print("SKIP: Angel Association members upstream unavailable: " + data.get("message", ""))
            return 0
        print(investors.stderr, file=sys.stderr)
        return 1
    if investors.returncode != 0:
        print(investors.stdout)
        print(investors.stderr, file=sys.stderr)
        return 1
    data = json.loads(investors.stdout)
    assert data["kind"] == "angel_investors"
    assert isinstance(data["records"], list)
    print(f"OK: investors returned {data['count']} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
