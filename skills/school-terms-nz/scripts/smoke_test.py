#!/usr/bin/env python3
"""Deterministic parser checks plus one bounded live Ministry source probe."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
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

    earliest_year_summer = module.classify_date(years, "2025-01-15")
    assert earliest_year_summer["kind"] == "school_break"
    assert earliest_year_summer["name"] == "Summer holidays"
    assert earliest_year_summer["certainty"] == "published"
    assert earliest_year_summer["description"] == years[0]["terms"][0]["description"]
    assert earliest_year_summer["end"] == years[0]["terms"][0]["start"]

    fixed_term = module.classify_date(years, "2026-05-11")
    assert fixed_term["kind"] == "school_term"
    assert fixed_term["name"] == "Term 2"
    assert fixed_term["certainty"] == "published"


results.append(check("date lookup distinguishes fixed and school-dependent dates", date_queries))


def term_four_closing_window_queries() -> None:
    ambiguous = module.classify_date(years, "2026-12-17")
    assert ambiguous["kind"] == "school_term_or_break"
    assert ambiguous["name"] == "Term 4 closing window"
    assert ambiguous["certainty"] == "school_dependent"
    assert "individual school" in ambiguous["caveat"].lower()

    next_result = module.next_break(years, "2026-12-17")
    assert next_result["name"] == "Summer holidays"
    assert next_result["days_until"] is None
    assert next_result["certainty"] == "school_dependent"
    assert "individual school" in next_result["caveat"].lower()

    fixed_term = module.classify_date(years, "2026-09-01")
    assert fixed_term["kind"] == "school_term"
    assert fixed_term["name"] == "Term 3"
    assert fixed_term["certainty"] == "published"


results.append(check("Term 4 closing dates remain school-dependent without invented precision", term_four_closing_window_queries))


def opening_window_next_break_query() -> None:
    expected_window = {
        "precision": "range",
        "earliest": "2026-01-26",
        "latest": "2026-02-09",
    }
    for query, fixed_days_until in (
        ("2026-01-26", 67),
        ("2026-02-01", 61),
        ("2026-02-09", 53),
    ):
        ambiguous = module.next_break(years, query)
        assert ambiguous["name"] == "Term 1 opening window"
        assert ambiguous["start"] == expected_window
        assert ambiguous["end"] == "2026-02-09"
        assert ambiguous["days_until"] is None
        assert ambiguous["certainty"] == "school_dependent"
        assert "individual school" in ambiguous["caveat"].lower()
        assert ambiguous["next_fixed_break"] == {
            "name": "Term 1 break",
            "start": "2026-04-03",
            "end": "2026-04-19",
            "days_until": fixed_days_until,
        }


results.append(check("next-break marks the inclusive Term 1 opening window as school-dependent", opening_window_next_break_query))


def opening_window_response_envelope() -> None:
    original = module.fetch_years
    try:
        setattr(module, "fetch_years", lambda timeout: (years, SOURCE_URL, "2026-09-03T00:00:00Z"))
        args = module.build_parser().parse_args(["next-break", "2026-02-01", "--json"])
        payload = module.run(args)
    finally:
        setattr(module, "fetch_years", original)

    assert set(payload) == {"status", "source_url", "fetched_at", "kind", "date", "break"}
    assert payload["status"] == "ok"
    assert payload["source_url"] == SOURCE_URL
    assert payload["fetched_at"] == "2026-09-03T00:00:00Z"
    assert payload["kind"] == "next_break"
    assert payload["date"] == "2026-02-01"
    assert payload["break"]["certainty"] == "school_dependent"
    assert payload["break"]["days_until"] is None


results.append(check("next-break preserves its JSON envelope and provenance", opening_window_response_envelope))


def certain_next_break_queries() -> None:
    earliest_year_summer = module.next_break(years, "2025-01-15")
    assert earliest_year_summer["name"] == "Summer holidays"
    assert earliest_year_summer["days_until"] == 0
    assert earliest_year_summer["certainty"] == "published"
    assert earliest_year_summer["description"] == years[0]["terms"][0]["description"]
    assert earliest_year_summer["end"] == years[0]["terms"][0]["start"]

    before_opening = module.next_break(years, "2026-01-25")
    assert before_opening["name"] == "Summer holidays"
    assert before_opening["days_until"] == 0
    assert before_opening["certainty"] == "published"

    after_opening = module.next_break(years, "2026-02-10")
    assert after_opening["name"] == "Term 1 break"
    assert after_opening["start"] == "2026-04-03"
    assert after_opening["days_until"] == 52
    assert after_opening["certainty"] == "published"

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

    after_closing_boundary = module.next_break(years, "2026-12-19")
    assert after_closing_boundary["name"] == "Summer holidays"
    assert after_closing_boundary["days_until"] == 0
    assert after_closing_boundary["certainty"] == "published"

    classified_after_boundary = module.classify_date(years, "2026-12-19")
    assert classified_after_boundary["kind"] == "school_break"
    assert classified_after_boundary["certainty"] == "published"


results.append(check("next-break preserves certain current and future break cases", certain_next_break_queries))


def summer_duration_stays_source_derived() -> None:
    mutated = fixture_text.replace("run for 5 or 6 weeks", "run for 12 weeks", 1)
    mutated_years = module.parse_school_terms(mutated, SOURCE_URL)

    classified = module.classify_date(mutated_years, "2026-12-20")
    next_result = module.next_break(mutated_years, "2026-12-20")
    assert "12 weeks" in classified["description"]
    assert "12 weeks" in next_result["description"]
    assert "5 or 6 weeks" not in json.dumps([classified, next_result])


results.append(check("summer duration claims stay source-derived", summer_duration_stays_source_derived))


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

        setattr(module.nzfetch, "fetch_bytes", lambda *args, **kwargs: (_ for _ in ()).throw(module.nzfetch.FetchError("synthetic outage")))
        try:
            module.fetch_years(1)
        except module.SkillError as exc:
            assert exc.exit_code == 5
        else:
            raise AssertionError("failed fetch did not map to exit 5")

        setattr(module.nzfetch, "fetch_bytes", original)
        original_build_opener = module.nzfetch.urllib.request.build_opener

        class TimeoutOpener:
            def open(self, *args, **kwargs):
                raise TimeoutError("synthetic raw timeout")

        try:
            setattr(module.nzfetch.urllib.request, "build_opener", lambda *args, **kwargs: TimeoutOpener())
            try:
                module.fetch_years(1)
            except module.SkillError as exc:
                assert exc.exit_code == 5
                assert exc.error_type == "upstream_unavailable"
            else:
                raise AssertionError("raw timeout did not map to exit 5")
        finally:
            setattr(module.nzfetch.urllib.request, "build_opener", original_build_opener)
    finally:
        setattr(module.nzfetch, "fetch_bytes", original)


results.append(check("fixture errors map schema, blocked and unavailable failures to exits 6, 4 and 5", error_contract))


def source_drift_mutations() -> None:
    def assert_schema_error(mutated: str) -> None:
        try:
            module.parse_school_terms(mutated, SOURCE_URL)
        except module.SkillError as exc:
            assert exc.exit_code == 6
            assert exc.error_type == "source_schema"
        else:
            raise AssertionError("semantic source drift did not fail closed")

    incomplete_opening_range = fixture_text.replace(
        "Starts between Monday 26 January and Monday 9 February and ends Thursday 2 April 2026",
        "Starts between Monday 26 January and ends Thursday 2 April 2026",
        1,
    )
    assert_schema_error(incomplete_opening_range)

    duplicate_date = fixture_text.replace(
        "Starts between Monday 26 January and Monday 9 February and ends Thursday 2 April 2026",
        "Starts between Monday 26 January and Monday 26 January and ends Thursday 2 April 2026",
        1,
    )
    assert_schema_error(duplicate_date)

    duplicate_term = fixture_text.replace("Term 2 (11 weeks)", "Term 1 (11 weeks)", 1)
    assert_schema_error(duplicate_term)

    duplicate_break = fixture_text.replace(
        "<h3>Term 2</h3><p>Saturday 4 July to Sunday 19 July 2026.</p>",
        "<h3>Term 1</h3><p>Saturday 4 July to Sunday 19 July 2026.</p>",
        1,
    )
    assert_schema_error(duplicate_break)

    wrong_year = fixture_text.replace(
        "ends Thursday 2 April 2026",
        "ends Thursday 2 April 2027",
        1,
    )
    assert_schema_error(wrong_year)

    missing_year = fixture_text.replace("ends Thursday 2 April 2026", "ends Thursday 2 April", 1)
    assert_schema_error(missing_year)

    wrong_term_shape = fixture_text.replace(
        "Monday 20 April to Friday 3 July 2026",
        "Monday 20 April to no later than Friday 3 July 2026",
        1,
    )
    assert_schema_error(wrong_term_shape)

    wrong_break_shape = fixture_text.replace(
        "Start no later than Saturday 19 December 2026",
        "Saturday 19 December to Sunday 20 December 2026",
        1,
    )
    assert_schema_error(wrong_break_shape)

    term_break_gap = fixture_text.replace(
        "ends Thursday 2 April 2026",
        "ends Wednesday 1 April 2026",
        1,
    )
    assert_schema_error(term_break_gap)

    closing_summer_gap = fixture_text.replace(
        "no later than Friday 18 December 2026",
        "no later than Thursday 17 December 2026",
        1,
    )
    assert_schema_error(closing_summer_gap)

    missing_opening_requirements = fixture_text.replace(
        "Half-day opening requirement 2026",
        "Unrecognised opening section 2026",
        1,
    )
    assert_schema_error(missing_opening_requirements)

    spoofed_opening_requirement = fixture_text.replace(
        "Primary, intermediate and specialist schools must be open for instruction for a minimum of 378 half days in 2026.",
        "Primary planning note: model 378 half days before secondary review in 2026.",
        1,
    )
    assert_schema_error(spoofed_opening_requirement)


results.append(check("semantic source drift fails closed with source_schema", source_drift_mutations))


def invalid_dates_do_not_fetch() -> None:
    original_fetch = module.fetch_years
    original_argv = sys.argv
    fetch_calls = 0

    def fail_if_fetched(timeout: int):
        nonlocal fetch_calls
        fetch_calls += 1
        raise AssertionError(f"fetch_years({timeout}) called for invalid local input")

    try:
        setattr(module, "fetch_years", fail_if_fetched)
        cases = (
            (["date", "not-a-date", "--json"], "invalid_input"),
            (["next-break", "not-a-date", "--json"], "invalid_input"),
            (["years", "--timeout", "0", "--json"], "invalid_input"),
        )
        for arguments, error_type in cases:
            sys.argv = [str(CLI), *arguments]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = module.main()
            payload = json.loads(output.getvalue())
            assert exit_code == 2
            assert payload["status"] == "error"
            assert payload["code"] == 2
            assert payload["error"] == error_type
        assert fetch_calls == 0
    finally:
        setattr(module, "fetch_years", original_fetch)
        sys.argv = original_argv


results.append(check("invalid date commands return structured exit 2 without fetching", invalid_dates_do_not_fetch))


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
