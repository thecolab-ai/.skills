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
AUSTRALIA_SLUG = "australia"
AUSTRALIA_NAME = "Australia"
AUSTRALIA_URL = "https://www.safetravel.govt.nz/destinations/australia"
SITEMAP_URL = "https://www.safetravel.govt.nz/sitemap.xml"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", *args],
        cwd=str(SKILL_DIR),
        text=True,
        capture_output=True,
        timeout=35,
        check=False,
    )


def check_live_advice() -> bool:
    try:
        advice = run([str(CLI), "advice", "australia", "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] live advice unavailable: network timed out")
        return True
    if advice.returncode in {4, 5}:
        print(
            "[SKIP] live advice unavailable: "
            + (advice.stderr.strip() or "upstream unavailable")
        )
        return True
    if advice.returncode != 0:
        print("[FAIL] live advice command")
        print((advice.stdout + advice.stderr).strip())
        return False
    try:
        payload = json.loads(advice.stdout)
        assert payload["schema_version"] == "1"
        assert payload["ok"] is True
        assert payload["source"]["url"] == AUSTRALIA_URL
        assert payload["source"]["retrieved_at"].endswith("Z")
        assert payload["source"]["page_updated"]
        assert payload["query"]["command"] == "advice"
        assert payload["query"]["destination"] == AUSTRALIA_SLUG
        assert payload["data"]["kind"] == "destination_advice"
        assert payload["data"]["destination"]["name"] == AUSTRALIA_NAME
        assert payload["data"]["destination"]["slug"] == AUSTRALIA_SLUG
        assert payload["data"]["destination"]["url"] == AUSTRALIA_URL
        assert payload["data"]["advice_level"]["number"] in {1, 2, 3, 4}
        assert payload["data"]["advice_level"]["title"]
        assert any(
            "advice can change" in warning.casefold() for warning in payload["warnings"]
        )
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] live advice schema assertion: {exc}")
        return False
    print(
        "[PASS] live Australia advice includes source, timestamps, level, and warning"
    )
    return True


def check_live_search() -> bool:
    try:
        search = run([str(CLI), "search", "australia", "--limit", "5", "--json"])
    except subprocess.TimeoutExpired:
        print("[SKIP] live search unavailable: network timed out")
        return True
    if search.returncode in {4, 5}:
        print(
            "[SKIP] live search unavailable: "
            + (search.stderr.strip() or "upstream unavailable")
        )
        return True
    if search.returncode != 0:
        print("[FAIL] live search command")
        print((search.stdout + search.stderr).strip())
        return False
    try:
        search_payload = json.loads(search.stdout)
        assert search_payload["source"]["url"] == SITEMAP_URL
        assert search_payload["source"]["retrieved_at"].endswith("Z")
        assert search_payload["query"]["command"] == "search"
        assert search_payload["query"]["text"] == AUSTRALIA_SLUG
        assert search_payload["query"]["limit"] == 5
        assert search_payload["data"]["kind"] == "destination_search"
        assert search_payload["data"]["sitemap_url"] == SITEMAP_URL
        assert any(
            item["name"] == AUSTRALIA_NAME
            and item["slug"] == AUSTRALIA_SLUG
            and item["url"] == AUSTRALIA_URL
            for item in search_payload["data"]["destinations"]
        )
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] live search schema assertion: {exc}")
        return False
    print("[PASS] live search returns the official Australia destination")
    return True


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

    advice_ok = check_live_advice()
    search_ok = check_live_search()
    return 0 if advice_ok and search_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
