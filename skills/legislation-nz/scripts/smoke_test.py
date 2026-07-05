#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
XML_PROBE = "https://www.legislation.govt.nz/act/public/1990/109/en/latest.xml/"


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
        if "upstream_" in result.stderr or "bot-protection" in result.stderr:
            print(f"[SKIP] upstream unavailable for {' '.join(args)}: {result.stderr.strip()}")
            raise SystemExit(0)
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout: {result.stdout[:400]}\nstderr: {result.stderr[:400]}"
        )
    return json.loads(result.stdout)


def check(name: str, fn) -> bool:
    try:
        outcome = fn()
        if outcome is False:
            raise AssertionError("check returned False")
        print(f"[PASS] {name}")
        return True
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}\n  error: {exc}")
        return False


def upstream_available() -> bool:
    try:
        req = urllib.request.Request(
            XML_PROBE,
            headers={
                "User-Agent": "thecolab-ai-legislation-nz-smoke/1.0",
                "Accept": "application/xml,text/xml",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(120)
            return resp.status == 200 and b"<act" in body
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] legislation.govt.nz XML endpoint unavailable: {exc}")
        return False


if not upstream_available():
    raise SystemExit(0)


results: list[bool] = []

results.append(
    check(
        "--help exits 0",
        lambda: (
            run(["--help"]).returncode == 0
            and "get-section" in run(["--help"]).stdout
            and "list-bills" in run(["--help"]).stdout
        ),
    )
)


def test_get_section() -> None:
    data = parse_json(["get-section", "1990/109", "5", "--json"])
    assert data["command"] == "get-section"
    assert data["status"] == "ok"
    assert data["act"]["title"] == "New Zealand Bill of Rights Act 1990"
    assert data["section"]["label"] == "5"
    assert "demonstrably justified" in data["section"]["text"]
    assert data["section"]["source_url"].endswith("/latest/#DLM225501")


results.append(check("get-section returns official section text", test_get_section))


def test_search() -> None:
    data = parse_json(["search", "Grocery Industry", "--type", "act", "--limit", "2", "--json"])
    assert data["command"] == "search"
    assert data["status"] == "ok"
    assert data["results"], data
    assert any("Grocery Industry Competition Act 2023" in item["title"] for item in data["results"])


results.append(check("search parses keyless official result cards", test_search))


def test_versions() -> None:
    data = parse_json(["versions", "1990/109", "--json"])
    assert data["command"] == "versions"
    assert data["status"] == "ok"
    assert len(data["versions"]) >= 4
    assert data["versions"][0]["as_at"] == "2022-08-30"


results.append(check("versions parses point-in-time versions", test_versions))


def test_missing_section_edge() -> None:
    result = run(["get-section", "1990/109", "9999", "--json"])
    assert result.returncode != 0
    assert "section 9999 not found" in result.stderr
    assert "Traceback" not in result.stderr


results.append(check("missing section edge case is clear", test_missing_section_edge))


if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
