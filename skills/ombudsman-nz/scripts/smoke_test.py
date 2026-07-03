#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=90,
    )


def parse_json(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout: {result.stdout[:300]}\nstderr: {result.stderr[:300]}")
    return json.loads(result.stdout)


def check(name: str, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}\n  error: {exc}")
        return False


def upstream_available() -> bool:
    try:
        req = urllib.request.Request(
            "https://www.ombudsman.parliament.nz/resources",
            headers={
                "User-Agent": "thecolab-ai-smoke-test",
                "Accept": "text/html",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"[SKIP] Ombudsman resources endpoint unavailable: {exc}")
        return False


if not upstream_available():
    sys.exit(0)


results: list[bool] = []


results.append(check("--help exits 0", lambda: run(["--help"]).returncode == 0 and "case-notes" in run(["--help"]).stdout))


def test_complaints():
    data = parse_json(["complaints", "--act", "OIA", "--limit", "2", "--json"])
    assert data.get("command") == "complaints"
    if "matches" in data:
        assert isinstance(data.get("matches"), list)
    else:
        assert isinstance(data.get("resources"), list)
    return True


results.append(check("complaints --act OIA returns structured JSON", test_complaints))


def test_case_notes_search():
    data = parse_json(["case-notes", "search", "--query", "complaints", "--limit", "3", "--json"])
    assert data.get("command") == "case-notes search"
    assert isinstance(data.get("results"), list)
    return True


results.append(check("case-notes search returns publication rows", test_case_notes_search))


def test_reports_opcat():
    data = parse_json(["reports", "--category", "OPCAT", "--limit", "3", "--json"])
    assert data.get("command") == "reports"
    assert isinstance(data.get("results"), list)
    return True


results.append(check("reports --category OPCAT returns publication rows", test_reports_opcat))


if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
