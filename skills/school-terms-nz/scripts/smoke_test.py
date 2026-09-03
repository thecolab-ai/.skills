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
    assert current["opening_requirements"] == [
        {"school_group": "primary_intermediate_specialist", "minimum_half_days": 378},
        {"school_group": "secondary_composite", "minimum_half_days": 376},
    ]
    assert current["caveats"] == [
        "Each school selects its own opening and closing dates within the published boundaries."
    ]
    assert "Public holiday" not in json.dumps(current)


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
    assert earliest_year_summer["certainty"] == "source_derived"
    assert "opening window" in earliest_year_summer["description"].lower()
    assert "preceding year's summer holidays section" in earliest_year_summer["caveat"].lower()
    assert earliest_year_summer["description"] != years[0]["terms"][0]["description"]
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
        module.fetch_years = lambda timeout: (years, SOURCE_URL, "2026-09-03T00:00:00Z")
        args = module.build_parser().parse_args(["next-break", "2026-02-01", "--json"])
        payload = module.run(args)
    finally:
        module.fetch_years = original

    assert set(payload) == {"status", "source_url", "fetched_at", "provenance", "kind", "date", "break"}
    assert payload["status"] == "ok"
    assert payload["source_url"] == SOURCE_URL
    assert payload["fetched_at"] == "2026-09-03T00:00:00Z"
    assert payload["kind"] == "next_break"
    assert payload["date"] == "2026-02-01"
    assert payload["break"]["certainty"] == "school_dependent"
    assert payload["break"]["days_until"] is None
    assert payload["provenance"]["source_owner"] == "New Zealand Ministry of Education"
    assert "CC BY-NC 4.0" in payload["provenance"]["source_content_notice"]
    assert "does not relicense source content" in payload["provenance"]["source_content_notice"]


results.append(check("next-break preserves its JSON envelope and provenance", opening_window_response_envelope))


def certain_next_break_queries() -> None:
    earliest_year_summer = module.next_break(years, "2025-01-15")
    assert earliest_year_summer["name"] == "Summer holidays"
    assert earliest_year_summer["days_until"] == 0
    assert earliest_year_summer["certainty"] == "source_derived"
    assert "opening window" in earliest_year_summer["description"].lower()
    assert "preceding year's summer holidays section" in earliest_year_summer["caveat"].lower()
    assert earliest_year_summer["description"] != years[0]["terms"][0]["description"]
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


def source_prose_is_not_redistributed() -> None:
    markers = {
        "term": "TERM_SOURCE_PROSE_MUST_NOT_ESCAPE",
        "break": "BREAK_SOURCE_PROSE_MUST_NOT_ESCAPE",
        "holiday": "HOLIDAY_SOURCE_PROSE_MUST_NOT_ESCAPE",
        "caveat": "CAVEAT_SOURCE_PROSE_MUST_NOT_ESCAPE",
    }
    mutated = fixture_text.replace(
        "Primary, intermediate and specialist schools: at least 378 instructional half-days during 2026.",
        "Primary, intermediate and specialist schools must be open for instruction for a minimum of 378 half days in 2026.",
        1,
    ).replace(
        "Instructional total: 78 to 96 half-days.",
        f"Instructional total: 78 to 96 half-days. {markers['term']}",
        1,
    ).replace(
        "Break interval: Friday 3 April through Sunday 19 April 2026.",
        f"Break interval: Friday 3 April through Sunday 19 April 2026. {markers['break']}",
        1,
    ).replace(
        "Instructional total: 106 half-days.</p>",
        f"Instructional total: 106 half-days.</p><p>Public holiday test note. {markers['holiday']}</p>",
        1,
    ).replace(
        "Calendar flexibility is local: each school picks dates within the stated limits.",
        f"Calendar flexibility is local: each school picks dates within the stated limits. {markers['caveat']}",
        1,
    )
    mutated_years = module.parse_school_terms(mutated, SOURCE_URL)
    serialised = json.dumps(mutated_years)

    assert not any(marker in serialised for marker in markers.values())
    assert mutated_years[1]["terms"][0]["description"] == (
        "Term 1 opens between 2026-01-26 and 2026-02-09 and ends on 2026-04-02."
    )
    assert mutated_years[1]["breaks"][0]["description"] == (
        "Term 1 break runs from 2026-04-03 through 2026-04-19."
    )
    assert mutated_years[1]["breaks"][3]["description"] == (
        "Summer holidays start by 2026-12-19; the end date depends on the school's next opening date."
    )
    assert mutated_years[1]["opening_requirements"][0] == {
        "school_group": "primary_intermediate_specialist",
        "minimum_half_days": 378,
    }
    assert "Primary, intermediate and specialist schools must be open" not in serialised


results.append(check("source prose is transformed rather than redistributed", source_prose_is_not_redistributed))


def published_years_and_opening_counts_stay_dynamic() -> None:
    past_start = fixture_text.index("    <h3>2025 school terms")
    main_end = fixture_text.index("  </main>")
    without_2025 = fixture_text[:past_start] + fixture_text[main_end:]
    assert [item["year"] for item in module.parse_school_terms(without_2025, SOURCE_URL)] == [
        2026,
        2027,
        2028,
    ]

    future_start = fixture_text.index("    <h2>2028 school terms")
    past_heading = fixture_text.index("    <h2>Past years")
    future_sections = fixture_text[future_start:past_heading]
    future_sections = future_sections.replace("2028", "2029")
    future_sections = future_sections.replace("at least 382 instructional half-days", "at least 384 instructional half-days", 1)
    with_2029 = fixture_text[:past_heading] + future_sections + fixture_text[past_heading:]
    parsed = module.parse_school_terms(with_2029, SOURCE_URL)
    assert [item["year"] for item in parsed] == [2025, 2026, 2027, 2028, 2029]
    assert parsed[-1]["opening_requirements"][0]["minimum_half_days"] == 384


results.append(
    check(
        "published years and plausible opening counts are discovered from source structure",
        published_years_and_opening_counts_stay_dynamic,
    )
)


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

        module.nzfetch.fetch_bytes = original
        original_build_opener = module.nzfetch.urllib.request.build_opener

        class TimeoutOpener:
            def open(self, *args, **kwargs):
                raise TimeoutError("synthetic raw timeout")

        try:
            module.nzfetch.urllib.request.build_opener = lambda *args, **kwargs: TimeoutOpener()
            try:
                module.fetch_years(1)
            except module.SkillError as exc:
                assert exc.exit_code == 5
                assert exc.error_type == "upstream_unavailable"
            else:
                raise AssertionError("raw timeout did not map to exit 5")
        finally:
            module.nzfetch.urllib.request.build_opener = original_build_opener
    finally:
        module.nzfetch.fetch_bytes = original


results.append(check("fixture errors map schema, blocked and unavailable failures to exits 6, 4 and 5", error_contract))


def malformed_content_encodings_fail_closed_end_to_end() -> None:
    original_build_opener = module.nzfetch.urllib.request.build_opener
    original_argv = sys.argv

    class MalformedEncodingResponse:
        def __init__(self, content_encoding: str) -> None:
            self.body = fixture_text.encode("utf-8")
            self.headers = {
                "Content-Type": "text/html; charset=utf-8",
                "Content-Encoding": content_encoding,
            }

        def read(self, size: int = -1) -> bytes:
            result, self.body = self.body[:size], self.body[size:]
            return result

        def geturl(self) -> str:
            return SOURCE_URL

    class MalformedEncodingOpener:
        def __init__(self, content_encoding: str) -> None:
            self.content_encoding = content_encoding

        def open(self, *args, **kwargs):
            return MalformedEncodingResponse(self.content_encoding)

    try:
        for content_encoding, message in (
            ("gzip", "invalid gzip response body"),
            ("deflate", "invalid deflate response body"),
            ("br", "unsupported Content-Encoding"),
        ):
            module.nzfetch.urllib.request.build_opener = lambda *args, encoding=content_encoding, **kwargs: MalformedEncodingOpener(encoding)
            sys.argv = [str(CLI), "years", "--json"]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = module.main()
            payload = json.loads(output.getvalue())
            assert exit_code == 5
            assert payload["status"] == "error"
            assert payload["code"] == 5
            assert payload["error"] == "upstream_unavailable"
            assert message in payload["message"]
            assert "years" not in payload
    finally:
        module.nzfetch.urllib.request.build_opener = original_build_opener
        sys.argv = original_argv


results.append(
    check(
        "malformed or unsupported Ministry content encodings cannot return successful years",
        malformed_content_encodings_fail_closed_end_to_end,
    )
)


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
        "Starts between Monday 26 January and Monday 9 February; the final day is Thursday 2 April 2026",
        "Starts between Monday 26 January; the final day is Thursday 2 April 2026",
        1,
    )
    assert_schema_error(incomplete_opening_range)

    duplicate_date = fixture_text.replace(
        "Starts between Monday 26 January and Monday 9 February; the final day is Thursday 2 April 2026",
        "Starts between Monday 26 January and Monday 26 January; the final day is Thursday 2 April 2026",
        1,
    )
    assert_schema_error(duplicate_date)

    duplicate_term = fixture_text.replace(
        '<h3>Term 2<a href="#term-2">#</a></h3>',
        '<h3>Term 1<a href="#term-2">#</a></h3>',
        1,
    )
    assert_schema_error(duplicate_term)

    duplicate_break = fixture_text.replace(
        "<h3>Term 2</h3><p>Break interval: Saturday 4 July through Sunday 19 July 2026.</p>",
        "<h3>Term 1</h3><p>Break interval: Saturday 4 July through Sunday 19 July 2026.</p>",
        1,
    )
    assert_schema_error(duplicate_break)

    wrong_year = fixture_text.replace(
        "final day is Thursday 2 April 2026",
        "final day is Thursday 2 April 2027",
        1,
    )
    assert_schema_error(wrong_year)

    missing_year = fixture_text.replace("final day is Thursday 2 April 2026", "final day is Thursday 2 April", 1)
    assert_schema_error(missing_year)

    wrong_term_shape = fixture_text.replace(
        "Date interval: Monday 20 April through Friday 3 July 2026",
        "Scheduled from Monday 20 April to no later than Friday 3 July 2026",
        1,
    )
    assert_schema_error(wrong_term_shape)

    wrong_break_shape = fixture_text.replace(
        "Start no later than Saturday 19 December 2026; the next school opening determines the finish",
        "Break interval: Saturday 19 December through Sunday 20 December 2026",
        1,
    )
    assert_schema_error(wrong_break_shape)

    term_break_gap = fixture_text.replace(
        "final day is Thursday 2 April 2026",
        "final day is Wednesday 1 April 2026",
        1,
    )
    assert_schema_error(term_break_gap)

    closing_summer_gap = fixture_text.replace(
        "to no later than Friday 18 December 2026",
        "to no later than Thursday 17 December 2026",
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
        "Primary, intermediate and specialist schools: at least 378 instructional half-days during 2026.",
        "Primary planning note: model 378 half days before secondary review in 2026.",
        1,
    )
    assert_schema_error(spoofed_opening_requirement)

    zero_opening_requirement = fixture_text.replace(
        "Primary, intermediate and specialist schools: at least 378 instructional half-days during 2026.",
        "Primary, intermediate and specialist schools: at least 000 instructional half-days during 2026.",
        1,
    )
    assert_schema_error(zero_opening_requirement)

    impossible_opening_requirement = fixture_text.replace(
        "Primary, intermediate and specialist schools: at least 378 instructional half-days during 2026.",
        "Primary, intermediate and specialist schools: at least 999 instructional half-days during 2026.",
        1,
    )
    assert_schema_error(impossible_opening_requirement)

    inconsistent_opening_requirements = fixture_text.replace(
        "Primary, intermediate and specialist schools: at least 378 instructional half-days during 2026.",
        "Primary, intermediate and specialist schools: at least 370 instructional half-days during 2026.",
        1,
    ).replace(
        "Secondary and composite schools: at least 376 instructional half-days during 2026.",
        "Secondary and composite schools: at least 380 instructional half-days during 2026.",
        1,
    )
    assert_schema_error(inconsistent_opening_requirements)


results.append(check("semantic source drift fails closed with source_schema", source_drift_mutations))


def duplicate_section_headings_fail_closed() -> None:
    mutations = {
        "terms": fixture_text.replace(
            '<h2 id="2026-school-holidays-1">2026 school holidays</h2>',
            '<h2>2026 school terms</h2>\n    '
            '<h2 id="2026-school-holidays-1">2026 school holidays</h2>',
            1,
        ),
        "holidays": fixture_text.replace(
            "  </main>",
            "    <h2>2026 school holidays</h2>\n  </main>",
            1,
        ),
        "opening requirements": fixture_text.replace(
            '<h2 id="2026-school-holidays-1">2026 school holidays</h2>',
            '<h3>Half-day opening requirement 2026</h3>\n    '
            '<h2 id="2026-school-holidays-1">2026 school holidays</h2>',
            1,
        ),
    }
    for section_name, mutated in mutations.items():
        try:
            module.parse_school_terms(mutated, SOURCE_URL)
        except module.SkillError as exc:
            assert exc.exit_code == 6, section_name
            assert exc.error_type == "source_schema", section_name
            assert "duplicate" in str(exc).lower(), section_name
        else:
            raise AssertionError(f"duplicate empty {section_name} heading did not fail closed")


results.append(
    check(
        "duplicate empty calendar and requirements headings fail closed",
        duplicate_section_headings_fail_closed,
    )
)


def invalid_dates_do_not_fetch() -> None:
    original_fetch = module.fetch_years
    original_argv = sys.argv
    fetch_calls = 0

    def fail_if_fetched(timeout: int):
        nonlocal fetch_calls
        fetch_calls += 1
        raise AssertionError(f"fetch_years({timeout}) called for invalid local input")

    try:
        module.fetch_years = fail_if_fetched
        cases = (
            (["date", "not-a-date", "--json"], "invalid_input"),
            (["next-break", "not-a-date", "--json"], "invalid_input"),
            (["years", "--timeout", "0", "--json"], "invalid_input"),
            (["years", "--timeout", "121", "--json"], "invalid_input"),
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
        module.fetch_years = original_fetch
        sys.argv = original_argv


results.append(check("invalid date commands return structured exit 2 without fetching", invalid_dates_do_not_fetch))


def oversized_timeout_is_safe() -> None:
    oversized = "9" * 72
    completed = run(["years", "--timeout", oversized, "--json"])
    assert completed.returncode == 2
    assert completed.stderr == ""
    assert "Traceback" not in completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "error"
    assert payload["code"] == 2
    assert payload["error"] == "invalid_input"
    assert payload["message"] == "--timeout must be between 1 and 120 seconds"


results.append(check("oversized timeout returns concise structured exit 2", oversized_timeout_is_safe))


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
assert payload["provenance"]["source_owner"] == "New Zealand Ministry of Education"
assert "does not relicense source content" in payload["provenance"]["source_content_notice"]
assert len(payload["years"]) >= 1
assert all(len(item["terms"]) == 4 and len(item["breaks"]) == 4 for item in payload["years"])
for published in payload["years"]:
    assert all(
        entry["description"] == module.independent_description(entry["name"], entry["start"], entry["end"])
        for entry in [*published["terms"], *published["breaks"]]
    )
    assert all(
        set(requirement) == {"school_group", "minimum_half_days"}
        for requirement in published["opening_requirements"]
    )
assert "public_holidays" not in json.dumps(payload)
assert '"label"' not in json.dumps(payload)
print("[PASS] live Ministry page returned complete published school years with provenance")
raise SystemExit(0)
