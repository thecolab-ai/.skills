#!/usr/bin/env python3
"""Smoke tests for Stats NZ DataInfo+ classifications skill."""

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


def is_upstream_skip(result: subprocess.CompletedProcess[str]) -> bool:
    text = (result.stdout + result.stderr).lower()
    return result.returncode == 2 and ("upstream_unavailable" in text or "upstream_blocked" in text)


def test(name: str, fn):
    try:
        outcome = fn()
        if outcome == "skip":
            print(f"[SKIP] {name}")
            return "skip"
        status = "PASS" if outcome else "FAIL"
        print(f"[{status}] {name}")
        return bool(outcome)
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


def test_help():
    result = run(["--help"], timeout=20)
    return result.returncode == 0 and "classification" in result.stdout and "concordance" in result.stdout


def test_search():
    result = run(["search", "region", "--scope", "codelists", "--limit", "3", "--json"])
    if is_upstream_skip(result):
        print(f"  upstream unavailable: {result.stderr.strip()}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "search" and data.get("count", 0) > 0


def test_classification_get():
    result = run(["classification", "get", "ca9760fe-c843-40b4-98c9-11d2f4ea597e", "--json"])
    if is_upstream_skip(result):
        print(f"  upstream unavailable: {result.stderr.strip()}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "classification" and data.get("metadata", {}).get("identifier") == "ca9760fe-c843-40b4-98c9-11d2f4ea597e"


def test_classification_versions():
    result = run(["classification", "versions", "ca9760fe-c843-40b4-98c9-11d2f4ea597e", "--json", "--limit", "3"])
    if is_upstream_skip(result):
        print(f"  upstream unavailable: {result.stderr.strip()}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "classification_versions" and isinstance(data.get("versions"), list)


def test_standards():
    result = run(["standards", "--json", "--limit", "3"])
    if is_upstream_skip(result):
        print(f"  upstream unavailable: {result.stderr.strip()}")
        return "skip"
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "standards" and isinstance(data.get("standards"), list)


def test_concordance():
    result = run(["concordance", "industry", "census", "--json", "--limit", "2"])
    if is_upstream_skip(result):
        print(f"  upstream unavailable: {result.stderr.strip()}")
        return "skip"
    if result.returncode not in (0, 2):
        print(f"  stderr: {result.stderr.strip()}")
        return False
    if result.returncode == 2:
        print(f"  upstream blocked: {result.stderr.strip()}")
        return "skip"
    if not result.stdout.strip():
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "concordance" and "from" in data and "to" in data


results = [
    test("--help", test_help),
    test("search region --scope codelists --json", test_search),
    test("classification get (known id) --json", test_classification_get),
    test("classification versions --json", test_classification_versions),
    test("standards --json", test_standards),
    test("concordance industry census --json", test_concordance),
]

if __name__ == "__main__":
    failures = [result for result in results if result is False]
    if failures:
        print(f"{len(failures)} test(s) failed.")
        sys.exit(1)
    print("All non-skipped tests passed.")
    sys.exit(0)
