#!/usr/bin/env python3
"""Bounded, outage-aware smoke checks for the SafeTravel NZ skill."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
PARSER_TEST = SKILL_DIR / "tests" / "test_parser.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", *args],
        cwd=str(SKILL_DIR),
        text=True,
        capture_output=True,
        timeout=35,
        check=False,
    )


def main() -> int:
    fixture = run([str(PARSER_TEST)])
    if fixture.returncode != 0:
        print("[FAIL] fixture parser assertions")
        print((fixture.stdout + fixture.stderr).strip())
        return 1
    print(fixture.stdout.strip())

    help_result = run([str(CLI), "--help"])
    if help_result.returncode != 0 or "{search,advice}" not in help_result.stdout:
        print("[FAIL] contract CLI help surface")
        print((help_result.stdout + help_result.stderr).strip())
        return 1
    print("[PASS] contract CLI help declares search and advice")

    try:
        advice = run([str(CLI), "advice", "australia", "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] live advice unavailable: network timed out")
        return 0
    if advice.returncode in {4, 5}:
        print("[SKIP] live advice unavailable: " + (advice.stderr.strip() or "upstream unavailable"))
        return 0
    if advice.returncode != 0:
        print("[FAIL] live advice command")
        print((advice.stdout + advice.stderr).strip())
        return 1
    try:
        payload = json.loads(advice.stdout)
        assert payload["schema_version"] == "1"
        assert payload["ok"] is True
        assert payload["source"]["url"].startswith("https://www.safetravel.govt.nz/destinations/australia")
        assert payload["source"]["retrieved_at"].endswith("Z")
        assert payload["source"]["page_updated"]
        assert payload["data"]["advice_level"]["number"] in {1, 2, 3, 4}
        assert payload["data"]["advice_level"]["title"]
        assert any("advice can change" in warning.casefold() for warning in payload["warnings"])
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] live advice schema assertion: {exc}")
        return 1
    print("[PASS] live Australia advice includes source, timestamps, level, and warning")

    try:
        search = run([str(CLI), "search", "australia", "--limit", "5", "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] live search unavailable: network timed out")
        return 0
    if search.returncode in {4, 5}:
        print("[SKIP] live search unavailable: " + (search.stderr.strip() or "upstream unavailable"))
        return 0
    if search.returncode != 0:
        print("[FAIL] live search command")
        print((search.stdout + search.stderr).strip())
        return 1
    try:
        search_payload = json.loads(search.stdout)
        assert search_payload["data"]["kind"] == "destination_search"
        assert any(item["slug"] == "australia" for item in search_payload["data"]["destinations"])
        assert search_payload["source"]["retrieved_at"].endswith("Z")
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] live search schema assertion: {exc}")
        return 1
    print("[PASS] live search returns the official Australia destination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
