#!/usr/bin/env python3
"""Smoke tests for find-experts-nz (OpenAlex + ORCID, stdlib only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def is_network_skip(result: subprocess.CompletedProcess[str]) -> bool:
    text = (result.stdout + result.stderr).lower()
    return result.returncode == 2 and (
        "network error" in text or "blocked" in text or "upstream" in text
    )


def test(name: str, fn) -> object:
    try:
        outcome = fn()
        if outcome == "skip":
            print(f"[SKIP] {name}")
            return "skip"
        status = "PASS" if outcome else "FAIL"
        print(f"[{status}] {name}")
        return bool(outcome)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


def test_help():
    result = run(["--help"], timeout=20)
    return (
        result.returncode == 0
        and "search" in result.stdout
        and "topics" in result.stdout
        and "institutions" in result.stdout
        and "orcid" in result.stdout
    )


def test_search_requires_topic():
    result = run(["search"], timeout=20)
    return result.returncode != 0  # argparse error, no network


def test_topics():
    result = run(["topics", "aged care", "--limit", "3", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "topics" and data.get("count", 0) > 0


def test_search():
    result = run(["search", "honey bee varroa", "--limit", "5", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return (
        data.get("kind") == "expert-search"
        and data.get("country") == "NZ"
        and isinstance(data.get("experts"), list)
    )


def test_search_wikidata():
    # WDQS rate-limits hard; the source soft-fails, so accept an empty list too.
    result = run(["search", "gerontology", "--source", "wikidata", "--limit", "4", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("sources_used") == ["wikidata"] and isinstance(data.get("experts"), list)


def test_search_crossref():
    result = run(["search", "honey bee varroa", "--source", "crossref", "--limit", "4", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("sources_used") == ["crossref"] and isinstance(data.get("experts"), list)


def test_institutions():
    result = run(["institutions", "otago", "--limit", "3", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "institutions" and data.get("count", 0) > 0


def test_search_by_institution():
    # University of Otago (I80281795) — stable OpenAlex institution id.
    result = run(["search", "aged care", "--institution", "I80281795",
                  "--limit", "3", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("sources_used") == ["openalex"] and isinstance(data.get("experts"), list)


def test_orcid():
    # Phil Lester (Victoria University of Wellington) — stable public ORCID record.
    result = run(["orcid", "0000-0002-1801-5687", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "orcid-record" and data.get("orcid") == "0000-0002-1801-5687"


def test_unis():
    result = run(["unis", "--json"], timeout=20)
    if result.returncode != 0:
        return False
    d = json.loads(result.stdout)
    slugs = [u["slug"] for u in d.get("universities", [])]
    return d.get("kind") == "universities" and "auckland" in slugs and "massey" in slugs


def test_directory_auckland():
    result = run(["directory", "aged care", "--uni", "auckland", "--limit", "3", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    d = json.loads(result.stdout)
    return d.get("kind") == "university-experts" and isinstance(d.get("experts"), list)


def test_directory_massey_no_contact():
    result = run(["directory", "milk", "--uni", "massey", "--limit", "3", "--json"])
    if is_network_skip(result):
        return "skip"
    if result.returncode != 0:
        return False
    low = result.stdout.lower()
    if "@massey" in low or '"email"' in low or '"phone"' in low:
        print("  LEAK: contact detail present in output")
        return False
    d = json.loads(result.stdout)
    return d.get("university") == "Massey University"


def test_directory_todo_refused():
    result = run(["directory", "x", "--uni", "otago"], timeout=20)
    return result.returncode == 1 and "wired up" in (result.stdout + result.stderr)


def main() -> int:
    results = [
        test("help lists subcommands", test_help),
        test("search requires a topic", test_search_requires_topic),
        test("topics resolves ids", test_topics),
        test("search returns NZ experts", test_search),
        test("crossref source search", test_search_crossref),
        test("wikidata source search", test_search_wikidata),
        test("institutions resolve", test_institutions),
        test("search by institution", test_search_by_institution),
        test("unis lists auckland+massey", test_unis),
        test("directory auckland", test_directory_auckland),
        test("directory massey, no contact leak", test_directory_massey_no_contact),
        test("directory todo uni refused", test_directory_todo_refused),
        test("orcid record fetch", test_orcid),
    ]
    passed = sum(1 for r in results if r is True)
    skipped = sum(1 for r in results if r == "skip")
    failed = sum(1 for r in results if r is False)
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
