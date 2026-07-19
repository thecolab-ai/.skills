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


def test_resource_card_fixture() -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("ombudsman_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = """
    <li class="slat">
      <h3><a href="/resources/synthetic-case-note">Synthetic case note</a></h3>
      <span class="slat__term">Case note</span>
      <span class="slat__term slat__date"><time datetime="2026-07-19">19 July 2026</time></span>
      <div class="slat__body"><p>Synthetic summary.</p></div>
    </li>
    """
    records = module.parse_resource_cards(source)
    assert len(records) == 1
    assert records[0]["slug"] == "synthetic-case-note"
    assert records[0]["published_at"] == "2026-07-19"
    assert records[0]["category"] == ["Case note"]
    print("[PASS] fixture Ombudsman resource-card parser")
    return True


if not test_resource_card_fixture():
    sys.exit(1)


if not upstream_available():
    sys.exit(0)


results: list[bool] = []


results.append(check("--help exits 0", lambda: run(["--help"]).returncode == 0 and "case-notes" in run(["--help"]).stdout))


def test_complaints():
    data = parse_json(["complaints", "--act", "OIA", "--limit", "2", "--json"])
    assert data.get("command") == "complaints"
    assert data.get("status") == "ok"
    if data.get("matches"):
        assert all(match.get("act") == "OIA" for match in data["matches"] if match.get("act"))

    lgoima = parse_json(["complaints", "--act", "LGOIMA", "--limit", "2", "--json"])
    assert lgoima.get("status") == "ok"
    if lgoima.get("matches"):
        assert all(match.get("act") == "LGOIMA" for match in lgoima["matches"] if match.get("act"))
        assert any(match.get("kind") in {"received", "completed"} for match in lgoima["matches"])
    return True


results.append(check("complaints classify OIA/LGOIMA resources", test_complaints))



def test_complaints_period_filter():
    data = parse_json(["complaints", "--period", "2024-H1", "--act", "OIA", "--limit", "1", "--json"])
    assert data.get("status") == "ok"
    for match in data.get("matches", []):
        assert match.get("period") == "2024-H1"
    return True


results.append(check("complaints period-filter excludes unknown-period files", test_complaints_period_filter))


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
    print("[PASS] live smoke assertions completed")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
