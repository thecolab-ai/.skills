#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=40,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def upstream_skip(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 2 and "upstream_unavailable" in result.stderr:
        print("  [SKIP] live upstream unavailable")
        return True
    return False


def test_help() -> bool:
    result = run(["--help"])
    return result.returncode == 0 and "Public Trust" in result.stdout


def test_search_json() -> bool:
    result = run(["search", "community", "--type", "organisation", "--limit", "3", "--json"])
    if upstream_skip(result):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    grants = data.get("grants")
    return isinstance(grants, list) and len(grants) <= 3 and "total" in data


def test_facets_json() -> bool:
    result = run(["facets", "--json"])
    if upstream_skip(result):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    facets = data.get("facets")
    return isinstance(facets, dict) and "grant_type" in facets


def test_bad_filter_edge_case() -> bool:
    result = run(["search", "unlikely-no-result-query-zzzzzz", "--limit", "2", "--json"])
    if upstream_skip(result):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    return isinstance(data.get("grants"), list) and data.get("total") == 0


results = [
    test("--help exits 0", test_help),
    test("search returns grants JSON", test_search_json),
    test("facets returns grant_type facet", test_facets_json),
    test("no-result search returns empty list", test_bad_filter_edge_case),
]

if all(results):
    print("All tests passed.")
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
