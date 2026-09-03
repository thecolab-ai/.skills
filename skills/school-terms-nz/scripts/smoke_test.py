#!/usr/bin/env python3
"""Deterministic parser checks plus one bounded live Ministry source probe."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURE = SKILL_DIR / "tests" / "fixtures" / "source-sample.html"
SOURCE_URL = "https://www.education.govt.nz/school/school-terms-and-holidays"


def load_cli():
    spec = importlib.util.spec_from_file_location("school_terms_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check(name: str, function) -> bool:
    try:
        function()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] fixture {name}: {exc}")
        return False
    print(f"[PASS] fixture {name}")
    return True


module = load_cli()
fixture_text = FIXTURE.read_text(encoding="utf-8")
years = module.parse_school_terms(fixture_text, SOURCE_URL)
results: list[bool] = []


def parser_shape() -> None:
    assert [item["year"] for item in years] == [2025, 2026, 2027, 2028]
    assert years[0]["terms"][0]["start"]["earliest"] == "2025-01-27"
    assert years[0]["breaks"][3]["start"]["latest"] == "2025-12-20"
    assert years[3]["terms"][3]["end"]["latest"] == "2028-12-15"
    assert years[3]["breaks"][3]["start"]["latest"] == "2028-12-16"
    current = years[1]
    assert len(current["terms"]) == 4
    assert len(current["breaks"]) == 4
    assert current["terms"][0]["start"] == {
        "precision": "range",
        "earliest": "2026-01-26",
        "latest": "2026-02-09",
    }
    assert current["terms"][3]["end"] == {
        "precision": "no_later_than",
        "latest": "2026-12-18",
    }
    assert current["breaks"][0]["start"] == "2026-04-03"
    assert current["breaks"][0]["end"] == "2026-04-19"
    assert current["breaks"][3]["start"] == {
        "precision": "no_later_than",
        "latest": "2026-12-19",
    }
    assert "378 half days" in current["opening_requirements"][0]
    assert any("flexibility" in note.lower() for note in current["caveats"])


results.append(check("HTML parser extracts ranges, breaks, requirements and caveats", parser_shape))


def date_queries() -> None:
    fixed_break = module.classify_date(years, "2026-04-10")
    assert fixed_break["kind"] == "school_break"
    assert fixed_break["name"] == "Term 1 break"
    assert fixed_break["certainty"] == "published"

    variable_start = module.classify_date(years, "2026-02-01")
    assert variable_start["kind"] == "school_term_or_break"
    assert variable_start["name"] == "Term 1 opening window"
    assert variable_start["certainty"] == "school_dependent"
    assert "opening window" in variable_start["caveat"].lower()

    previous_summer = module.classify_date(years, "2027-01-15")
    assert previous_summer["kind"] == "school_break"
    assert previous_summer["name"] == "Summer holidays"

    fixed_term = module.classify_date(years, "2026-05-11")
    assert fixed_term["kind"] == "school_term"
    assert fixed_term["name"] == "Term 2"
    assert fixed_term["certainty"] == "published"


results.append(check("date lookup distinguishes fixed and school-dependent dates", date_queries))


def next_break_query() -> None:
    next_break = module.next_break(years, "2026-06-01")
    assert next_break["name"] == "Term 2 break"
    assert next_break["start"] == "2026-07-04"
    assert next_break["days_until"] == 33

    current_break = module.next_break(years, "2026-07-10")
    assert current_break["name"] == "Term 2 break"
    assert current_break["days_until"] == 0

    current_summer = module.next_break(years, "2027-01-15")
    assert current_summer["name"] == "Summer holidays"
    assert current_summer["days_until"] == 0


results.append(check("next-break returns the current or next published break", next_break_query))


def cli_surface() -> None:
    expected = {"years", "year", "date", "next-break"}
    help_result = run(["--help"])
    assert help_result.returncode == 0
    assert expected <= set(module.build_parser()._subparsers._group_actions[0].choices)
    for command in expected:
        result = run([command, "--help"])
        assert result.returncode == 0
        assert "--json" in result.stdout
        assert "--timeout" in result.stdout
    missing_date = run(["date", "--json"])
    assert missing_date.returncode == 2
    error = json.loads(missing_date.stdout)
    assert error["error"] == "invalid_input"
    assert error["code"] == 2


results.append(check("CLI exposes all documented JSON and timeout surfaces", cli_surface))


def error_contract() -> None:
    malformed = fixture_text.replace("2028 school holidays", "Missing holiday section", 1)
    try:
        module.parse_school_terms(malformed, SOURCE_URL)
    except module.SkillError as exc:
        assert exc.exit_code == 6
        assert exc.error_type == "source_schema"
    else:
        raise AssertionError("incomplete source fixture did not fail")

    original = module.nzfetch.fetch_bytes
    try:
        module.nzfetch.fetch_bytes = lambda *args, **kwargs: (_ for _ in ()).throw(module.nzfetch.Blocked("synthetic block"))
        try:
            module.fetch_years(1)
        except module.SkillError as exc:
            assert exc.exit_code == 4
        else:
            raise AssertionError("blocked fetch did not map to exit 4")

        module.nzfetch.fetch_bytes = lambda *args, **kwargs: (_ for _ in ()).throw(module.nzfetch.FetchError("synthetic outage"))
        try:
            module.fetch_years(1)
        except module.SkillError as exc:
            assert exc.exit_code == 5
        else:
            raise AssertionError("failed fetch did not map to exit 5")
    finally:
        module.nzfetch.fetch_bytes = original


results.append(check("fixture errors map schema, blocked and unavailable failures to exits 6, 4 and 5", error_contract))


if not all(results):
    raise SystemExit(1)

live = run(["years", "--timeout", "10", "--json"], timeout=20)
text = live.stdout or live.stderr
try:
    payload = json.loads(text)
except json.JSONDecodeError as exc:
    print(f"[FAIL] live source did not return JSON: {exc}")
    raise SystemExit(1)

if live.returncode in {4, 5}:
    print(f"[SKIP] live upstream unavailable or blocked: {payload.get('message', 'unknown source error')}")
    raise SystemExit(0)
if live.returncode != 0:
    print(f"[FAIL] live source command failed with exit {live.returncode}: {payload}")
    raise SystemExit(1)
assert payload["status"] == "ok"
assert payload["source_url"] == SOURCE_URL
assert payload["fetched_at"].endswith("Z")
assert len(payload["years"]) >= 1
assert all(len(item["terms"]) == 4 and len(item["breaks"]) == 4 for item in payload["years"])
print("[PASS] live Ministry page returned complete published school years with provenance")
raise SystemExit(0)
