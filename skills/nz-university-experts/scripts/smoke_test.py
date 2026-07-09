#!/usr/bin/env python3
"""Smoke tests for nz-university-experts (public directory APIs, stdlib only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args, timeout=60):
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, timeout=timeout)


def is_network_skip(result):
    text = (result.stdout + result.stderr).lower()
    return result.returncode == 2 and (
        "network error" in text or "blocked" in text or "upstream" in text
    )


def test(name, fn):
    try:
        outcome = fn()
        if outcome == "skip":
            print(f"[SKIP] {name}")
            return "skip"
        print(f"[{'PASS' if outcome else 'FAIL'}] {name}")
        return bool(outcome)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


def test_help():
    r = run(["--help"], timeout=20)
    return r.returncode == 0 and "search" in r.stdout and "unis" in r.stdout


def test_unis():
    r = run(["unis", "--json"], timeout=20)
    if r.returncode != 0:
        print(f"  stderr: {r.stderr.strip()}")
        return False
    d = json.loads(r.stdout)
    slugs = [u["slug"] for u in d.get("universities", [])]
    return d.get("kind") == "universities" and "auckland" in slugs


def test_unknown_uni():
    r = run(["search", "x", "--uni", "nope"], timeout=20)
    return r.returncode == 1  # validation error, no network


def test_search_auckland():
    r = run(["search", "aged care", "--uni", "auckland", "--limit", "3", "--json"])
    if is_network_skip(r):
        return "skip"
    if r.returncode != 0:
        print(f"  stderr: {r.stderr.strip()}")
        return False
    d = json.loads(r.stdout)
    if d.get("kind") != "university-experts" or not isinstance(d.get("experts"), list):
        return False
    if not d["experts"]:
        return True  # reachable but empty is acceptable
    e = d["experts"][0]
    return "name" in e and "profile_url" in e and "expertise" in e


def test_search_massey_no_contact():
    r = run(["search", "milk", "--uni", "massey", "--limit", "3", "--json"])
    if is_network_skip(r):
        return "skip"
    if r.returncode != 0:
        print(f"  stderr: {r.stderr.strip()}")
        return False
    # Contact details must never leak into output.
    low = r.stdout.lower()
    if "@massey" in low or '"email"' in low or '"phone"' in low:
        print("  LEAK: contact detail present in output")
        return False
    d = json.loads(r.stdout)
    return d.get("university") == "Massey University" and isinstance(d.get("experts"), list)


def test_todo_uni_refused():
    r = run(["search", "x", "--uni", "otago"], timeout=20)
    return r.returncode == 1 and "wired up" in (r.stdout + r.stderr)


def main():
    results = [
        test("help lists subcommands", test_help),
        test("unis lists auckland", test_unis),
        test("unknown uni errors", test_unknown_uni),
        test("todo uni is refused", test_todo_uni_refused),
        test("auckland search returns experts", test_search_auckland),
        test("massey search, no contact leak", test_search_massey_no_contact),
    ]
    passed = sum(1 for r in results if r is True)
    skipped = sum(1 for r in results if r == "skip")
    failed = sum(1 for r in results if r is False)
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
