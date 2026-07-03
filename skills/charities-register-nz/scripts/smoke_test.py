#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
BASE = "https://www.odata.charities.govt.nz/"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR.parent.parent),
        timeout=timeout,
    )


def upstream_available() -> bool:
    try:
        req = urllib.request.Request(BASE, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/xml"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[SKIP] Charities Register OData unavailable or blocked: {e}")
        return False


def check(name: str, fn) -> bool:
    try:
        ok = bool(fn())
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def json_cmd(args: list[str]) -> dict:
    result = run([*args, "--json"])
    if result.returncode != 0:
        # Upstream Incapsula/403 or transient network errors should skip cleanly.
        blocked = "blocked_by_upstream" in result.stderr or "HTTP 403" in result.stderr or "network error" in result.stderr
        if blocked:
            print(f"[SKIP] upstream unavailable during {' '.join(args)}: {result.stderr.strip()[:300]}")
            raise SystemExit(0)
        print(result.stderr[:500])
        return {}
    return json.loads(result.stdout)


results: list[bool] = []

results.append(check("--help exits 0", lambda: run(["--help"]).returncode == 0))

if not upstream_available():
    sys.exit(0 if all(results) else 1)


def test_activities() -> bool:
    data = json_cmd(["activities", "--limit", "5"])
    return data.get("kind") == "activities" and len(data.get("rows", [])) > 0


def test_search() -> bool:
    data = json_cmd(["search", "foundation", "--limit", "3"])
    return data.get("kind") == "search" and "meta" in data and isinstance(data.get("rows"), list)


def test_grantmakers() -> bool:
    data = json_cmd(["grantmakers", "--min-grants", "10000", "--limit", "2"])
    rows = data.get("rows", [])
    return data.get("kind") == "grantmakers" and isinstance(rows, list) and all((r.get("GrantsPaidWithinNZ") or 0) >= 10000 for r in rows)


results.append(check("activities returns taxonomy rows", test_activities))
results.append(check("search emits JSON rows", test_search))
results.append(check("grantmakers filters by GrantsPaidWithinNZ", test_grantmakers))

if all(results):
    print("All tests passed.")
    sys.exit(0)

print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
