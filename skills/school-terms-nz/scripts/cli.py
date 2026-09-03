#!/usr/bin/env python3
"""Query official New Zealand school term and holiday dates."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SOURCE_URL = "https://www.education.govt.nz/school/school-terms-and-holidays"
ALLOWED_HOSTS = {"www.education.govt.nz"}
DEFAULT_TIMEOUT = 10
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
DATE_FRAGMENT = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)",
    re.I,
)
YEAR_FRAGMENT = re.compile(r"\b20\d{2}\b")
EXPECTED_TERM_NAMES = [f"Term {number}" for number in range(1, 5)]
EXPECTED_BREAK_NAMES = ["Term 1 break", "Term 2 break", "Term 3 break", "Summer holidays"]
OPENING_REQUIREMENT_LABELS = (
    ("primary", "Primary, intermediate and specialist schools"),
    ("secondary", "Secondary and composite schools"),
)


class SkillError(RuntimeError):
    """Expected command failure with a stable repository exit code."""

    def __init__(self, message: str, *, exit_code: int, error_type: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.error_type = error_type


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep argparse failures machine-readable when the caller requested JSON."""

    def error(self, message: str) -> NoReturn:
        if "--json" in sys.argv[1:]:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "code": 2,
                        "error": "invalid_input",
                        "message": message,
                        "source_url": SOURCE_URL,
                    },
                    indent=2,
                )
            )
            self.exit(2)
        super().error(message)


class SourceOutlineParser(HTMLParser):
    """Collect only source headings and paragraphs, ignoring presentation markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[tuple[str, str]] = []
        self._capture: str | None = None
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and tag in {"h2", "h3", "h4", "p"} and self._capture is None:
            self._capture = tag
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and tag == self._capture:
            text = clean_text(" ".join(self._parts))
            text = re.sub(r"\s+#\s*$", "", text).strip()
            if text:
                self.nodes.append((tag, text))
            self._capture = None
            self._parts = []


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value).replace("\xa0", " ")).strip()


def iso_date(year: int, match: re.Match[str]) -> str:
    month = MONTHS[match.group("month").lower()]
    day = int(match.group("day"))
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError as exc:
        raise SkillError(
            f"source contains an invalid date for {year}: {match.group(0).strip()}",
            exit_code=6,
            error_type="source_schema",
        ) from exc


def date_fragments(text: str, year: int) -> list[str]:
    return [iso_date(year, match) for match in DATE_FRAGMENT.finditer(text)]


def semantic_dates(text: str, year: int, *, expected: int, description: str) -> list[str]:
    """Fail closed when a dated source sentence changes semantic shape."""
    explicit_years = {int(value) for value in YEAR_FRAGMENT.findall(text)}
    if explicit_years != {year}:
        raise SkillError(
            f"{description} for {year} must contain only its section year: {text}",
            exit_code=6,
            error_type="source_schema",
        )
    dates = date_fragments(text, year)
    if len(dates) != expected or len(set(dates)) != expected:
        raise SkillError(
            f"{description} for {year} expected {expected} unique dates: {text}",
            exit_code=6,
            error_type="source_schema",
        )
    parsed = [dt.date.fromisoformat(value) for value in dates]
    if parsed != sorted(parsed):
        raise SkillError(
            f"{description} for {year} contains dates out of order: {text}",
            exit_code=6,
            error_type="source_schema",
        )
    return dates


def has_precision(value: Any, expected: str) -> bool:
    return isinstance(value, dict) and value.get("precision") == expected


def opening_requirement_label(text: str, year: int) -> str | None:
    """Recognise only the two complete Ministry opening-requirement sentences."""
    for label, school_group in OPENING_REQUIREMENT_LABELS:
        pattern = (
            rf"{re.escape(school_group)} (?:must|are required to) be open for instruction "
            rf"for (?:a )?minimum of \d{{3}} half days in {year}\."
        )
        if re.fullmatch(pattern, text):
            return label
    return None


def opening_requirements_valid(item: dict[str, Any]) -> bool:
    labels = [opening_requirement_label(text, item["year"]) for text in item["opening_requirements"]]
    return labels == [label for label, _school_group in OPENING_REQUIREMENT_LABELS]


def year_semantics_valid(item: dict[str, Any]) -> bool:
    """Validate heading-specific date forms and whole-year chronology."""
    terms = item["terms"]
    breaks = item["breaks"]
    if len(terms) != 4 or len(breaks) != 4:
        return False
    shapes_valid = (
        has_precision(terms[0].get("start"), "range")
        and has_precision(terms[0].get("end"), "fixed")
        and all(isinstance(terms[index].get(key), str) for index in (1, 2) for key in ("start", "end"))
        and isinstance(terms[3].get("start"), str)
        and has_precision(terms[3].get("end"), "no_later_than")
        and all(isinstance(breaks[index].get(key), str) for index in range(3) for key in ("start", "end"))
        and has_precision(breaks[3].get("start"), "no_later_than")
        and breaks[3].get("end") is None
    )
    if not shapes_valid:
        return False

    ordered_values = [
        terms[0]["start"]["earliest"],
        terms[0]["start"]["latest"],
        terms[0]["end"]["date"],
        breaks[0]["start"],
        breaks[0]["end"],
        terms[1]["start"],
        terms[1]["end"],
        breaks[1]["start"],
        breaks[1]["end"],
        terms[2]["start"],
        terms[2]["end"],
        breaks[2]["start"],
        breaks[2]["end"],
        terms[3]["start"],
        terms[3]["end"]["latest"],
        breaks[3]["start"]["latest"],
    ]
    ordered_dates = [dt.date.fromisoformat(value) for value in ordered_values]
    if ordered_dates != sorted(set(ordered_dates)):
        return False
    adjacent_boundaries = (
        (terms[0]["end"]["date"], breaks[0]["start"]),
        (breaks[0]["end"], terms[1]["start"]),
        (terms[1]["end"], breaks[1]["start"]),
        (breaks[1]["end"], terms[2]["start"]),
        (terms[2]["end"], breaks[2]["start"]),
        (breaks[2]["end"], terms[3]["start"]),
        (terms[3]["end"]["latest"], breaks[3]["start"]["latest"]),
    )
    return all(
        dt.date.fromisoformat(right) - dt.date.fromisoformat(left) == dt.timedelta(days=1)
        for left, right in adjacent_boundaries
    )


def parse_term_dates(text: str, year: int) -> tuple[str | dict[str, str], str | dict[str, str]]:
    lowered = text.lower()
    if lowered.startswith("starts between"):
        dates = semantic_dates(text, year, expected=3, description="term opening range")
        return (
            {"precision": "range", "earliest": dates[0], "latest": dates[1]},
            {"precision": "fixed", "date": dates[2]},
        )
    if "to no later than" in lowered:
        dates = semantic_dates(text, year, expected=2, description="variable term range")
        return dates[0], {"precision": "no_later_than", "latest": dates[1]}
    dates = semantic_dates(text, year, expected=2, description="fixed term range")
    return dates[0], dates[1]


def parse_break_dates(text: str, year: int) -> tuple[str | dict[str, str], str | None]:
    if text.lower().startswith("start no later than"):
        dates = semantic_dates(text, year, expected=1, description="variable holiday start")
        return {"precision": "no_later_than", "latest": dates[0]}, None
    dates = semantic_dates(text, year, expected=2, description="fixed holiday range")
    return dates[0], dates[1]


def parse_school_terms(source_html: str, source_url: str = SOURCE_URL) -> list[dict[str, Any]]:
    """Parse all complete current and past term/holiday sections from the Ministry page."""
    parser = SourceOutlineParser()
    parser.feed(source_html)
    parser.close()

    by_year: dict[int, dict[str, Any]] = {}
    mode: str | None = None
    year: int | None = None
    current_term: dict[str, Any] | None = None
    current_break: dict[str, Any] | None = None
    subsection: str | None = None

    for tag, text in parser.nodes:
        if tag in {"h2", "h3", "h4"}:
            section = re.fullmatch(r"(20\d{2}) school (terms|holidays)", text, re.I)
            if section:
                year = int(section.group(1))
                mode = "terms" if section.group(2).lower() == "terms" else "breaks"
                by_year.setdefault(
                    year,
                    {
                        "year": year,
                        "terms": [],
                        "breaks": [],
                        "opening_requirements": [],
                        "caveats": [],
                        "source_url": source_url,
                    },
                )
                current_term = None
                current_break = None
                subsection = None
                continue
            if tag == "h2":
                mode = None
                year = None
                continue

        if year is None or mode is None:
            continue
        record = by_year[year]

        if tag in {"h3", "h4"}:
            term_heading = re.match(r"Term\s+([1-4])\b", text, re.I)
            if mode == "terms" and term_heading:
                current_term = {
                    "name": f"Term {term_heading.group(1)}",
                    "label": text,
                    "public_holidays": [],
                }
                record["terms"].append(current_term)
                current_break = None
                subsection = "term"
            elif mode == "breaks" and (term_heading or text.lower().startswith("summer holidays")):
                name = f"Term {term_heading.group(1)} break" if term_heading else "Summer holidays"
                current_break = {"name": name, "label": text, "public_holidays": []}
                record["breaks"].append(current_break)
                current_term = None
                subsection = "break"
            elif mode == "terms" and text.lower().startswith("half-day opening requirement"):
                current_term = None
                subsection = "requirements"
            elif mode == "terms" and text.lower().startswith("unused curriculum half-days"):
                current_term = None
                subsection = None
            else:
                current_term = None
                current_break = None
                subsection = None
            continue

        if tag != "p":
            continue
        if mode == "terms" and subsection == "term" and current_term is not None:
            if "start" not in current_term:
                start, end = parse_term_dates(text, year)
                current_term.update({"start": start, "end": end, "description": text})
            elif text.lower().startswith("public holiday"):
                current_term["public_holidays"].append(text)
        elif mode == "breaks" and subsection == "break" and current_break is not None:
            if "start" not in current_break:
                start, end = parse_break_dates(text, year)
                current_break.update({"start": start, "end": end, "description": text})
            elif text.lower().startswith("public holiday"):
                current_break["public_holidays"].append(text)
        elif mode == "terms" and subsection == "requirements":
            lowered = text.lower()
            if opening_requirement_label(text, year) is not None:
                record["opening_requirements"].append(text)
            if "flexibility" in lowered:
                record["caveats"].append(text)
    years = [by_year[key] for key in sorted(by_year)]
    invalid = []
    for item in years:
        term_names = [entry.get("name") for entry in item["terms"]]
        break_names = [entry.get("name") for entry in item["breaks"]]
        if (
            term_names != EXPECTED_TERM_NAMES
            or break_names != EXPECTED_BREAK_NAMES
            or not opening_requirements_valid(item)
            or not year_semantics_valid(item)
            or any("start" not in entry or "end" not in entry for entry in item["terms"])
            or any("start" not in entry or "end" not in entry for entry in item["breaks"])
        ):
            invalid.append(str(item["year"]))
    if not years or invalid:
        detail = f"; incomplete years: {', '.join(invalid)}" if invalid else ""
        raise SkillError(
            f"Ministry page did not contain complete published term and holiday sections{detail}",
            exit_code=6,
            error_type="source_schema",
        )
    return years


def fetched_at() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_years(timeout: int) -> tuple[list[dict[str, Any]], str, str]:
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            SOURCE_URL,
            timeout=timeout,
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            allowed_hosts=ALLOWED_HOSTS,
            expect_json=False,
        )
    except nzfetch.Blocked as exc:
        raise SkillError(str(exc), exit_code=4, error_type="blocked") from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc), exit_code=5, error_type="upstream_unavailable") from exc
    return parse_school_terms(body.decode("utf-8", "replace"), final_url), final_url, fetched_at()


def parse_query_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SkillError(
            f"invalid date {value!r}; use YYYY-MM-DD",
            exit_code=2,
            error_type="invalid_input",
        ) from exc


def year_record(years: list[dict[str, Any]], year: int) -> dict[str, Any]:
    for item in years:
        if item["year"] == year:
            return item
    available = ", ".join(str(item["year"]) for item in years)
    raise SkillError(
        f"year {year} is not published on the Ministry page; available years: {available}",
        exit_code=2,
        error_type="invalid_input",
    )


def fixed_end(value: str | dict[str, str]) -> str:
    return value if isinstance(value, str) else value.get("date") or value["latest"]


def classification(entry: dict[str, Any], kind: str, certainty: str, caveat: str | None = None) -> dict[str, Any]:
    result = {
        "kind": kind,
        "name": entry["name"],
        "certainty": certainty,
        "start": entry["start"],
        "end": entry["end"],
        "description": entry["description"],
    }
    if caveat:
        result["caveat"] = caveat
    return result


def pre_opening_summer_holiday(years: list[dict[str, Any]], query: dt.date) -> dict[str, Any] | None:
    """Return the summer break before the earliest published Term 1 opening."""
    current = next((item for item in years if item["year"] == query.year), None)
    previous = next((item for item in years if item["year"] == query.year - 1), None)
    if current is None:
        return None
    term_one = current["terms"][0]
    if term_one["name"] != "Term 1" or not isinstance(term_one["start"], dict):
        return None
    if query >= parse_query_date(term_one["start"]["earliest"]):
        return None
    if previous is not None:
        summer = next((item for item in previous["breaks"] if item["name"] == "Summer holidays"), None)
        if summer is not None:
            return summer
    source_summer = next((item for item in current["breaks"] if item["name"] == "Summer holidays"), None)
    if source_summer is None:
        return None
    return {
        **source_summer,
        "start": None,
        "end": term_one["start"],
        "description": term_one["description"],
    }


def classify_date(years: list[dict[str, Any]], value: str) -> dict[str, Any]:
    query = parse_query_date(value)
    try:
        published = year_record(years, query.year)
    except SkillError:
        return {
            "kind": "outside_published_years",
            "name": None,
            "certainty": "unavailable",
            "caveat": "The Ministry page does not publish a complete year covering this date.",
        }

    prior_summer = pre_opening_summer_holiday(years, query)
    if prior_summer is not None:
        return classification(
            prior_summer,
            "school_break",
            "published",
            "The summer holiday ends on each school's chosen opening date; this date is before the earliest published Term 1 opening.",
        )

    for item in published["breaks"]:
        start = item["start"]
        end = item["end"]
        if isinstance(start, str) and end and parse_query_date(start) <= query <= parse_query_date(end):
            return classification(item, "school_break", "published")
        if isinstance(start, dict) and query >= parse_query_date(start["latest"]):
            return classification(
                item,
                "school_break",
                "published",
                "The summer holiday starts on each school's closing date, no later than the published date.",
            )

    for item in published["terms"]:
        start = item["start"]
        end = item["end"]
        end_date = parse_query_date(fixed_end(end))
        if isinstance(start, dict):
            earliest = parse_query_date(start["earliest"])
            latest = parse_query_date(start["latest"])
            if earliest <= query <= latest:
                opening_window = {**item, "name": "Term 1 opening window"}
                return classification(
                    opening_window,
                    "school_term_or_break",
                    "school_dependent",
                    "The date falls inside the published Term 1 opening window; it is a school term after that school opens and summer break beforehand.",
                )
            if latest < query <= end_date:
                return classification(item, "school_term", "published")
        else:
            start_date = parse_query_date(start)
            if start_date <= query <= end_date:
                if isinstance(end, dict):
                    closing_window = {**item, "name": "Term 4 closing window"}
                    return classification(
                        closing_window,
                        "school_term_or_break",
                        "school_dependent",
                        "The date falls inside the published Term 4 closing window; whether it is a school term or summer holiday depends on the individual school's closing date.",
                    )
                return classification(item, "school_term", "published")

    return {
        "kind": "unclassified",
        "name": None,
        "certainty": "school_dependent",
        "caveat": "No fixed published term or break covers this date; check the individual school's calendar, teacher-only days and local closures.",
    }


def next_break(years: list[dict[str, Any]], value: str) -> dict[str, Any]:
    query = parse_query_date(value)
    prior_summer = pre_opening_summer_holiday(years, query)
    if prior_summer is not None:
        return {
            "name": prior_summer["name"],
            "start": prior_summer["start"],
            "end": prior_summer["end"],
            "days_until": 0,
            "description": prior_summer["description"],
            "certainty": "published",
            "caveat": "The summer holiday ends on each school's chosen opening date; this date is before the earliest published Term 1 opening.",
        }

    for published in years:
        opening_term = next(
            (item for item in published["terms"] if isinstance(item["start"], dict)),
            None,
        )
        if opening_term is None:
            continue
        opening_start = opening_term["start"]
        earliest = parse_query_date(opening_start["earliest"])
        latest = parse_query_date(opening_start["latest"])
        if not earliest <= query <= latest:
            continue

        fixed_candidates = [
            item
            for year in years
            for item in year["breaks"]
            if isinstance(item["start"], str) and parse_query_date(item["start"]) >= query
        ]
        if not fixed_candidates:
            raise SkillError(
                "no fixed future break is available in the published years",
                exit_code=2,
                error_type="invalid_input",
            )
        next_fixed = min(fixed_candidates, key=lambda item: parse_query_date(item["start"]))
        next_fixed_start = parse_query_date(next_fixed["start"])
        return {
            "name": "Term 1 opening window",
            "start": opening_start,
            "end": opening_start["latest"],
            "days_until": None,
            "description": "Schools may still be in summer holidays or may already be in Term 1 on this date.",
            "certainty": "school_dependent",
            "caveat": "Check the individual school's calendar: during the published Term 1 opening window, some schools are still in summer holidays while others have opened.",
            "next_fixed_break": {
                "name": next_fixed["name"],
                "start": next_fixed["start"],
                "end": next_fixed["end"],
                "days_until": (next_fixed_start - query).days,
            },
        }

    current_year = next((item for item in years if item["year"] == query.year), None)
    if current_year is not None:
        closing_term = next(
            (
                item
                for item in current_year["terms"]
                if isinstance(item["end"], dict) and item["end"].get("precision") == "no_later_than"
            ),
            None,
        )
        summer = next(
            (item for item in current_year["breaks"] if isinstance(item["start"], dict)),
            None,
        )
        if closing_term is not None and summer is not None:
            closing_start = parse_query_date(closing_term["start"])
            closing_latest = parse_query_date(closing_term["end"]["latest"])
            if closing_start <= query <= closing_latest:
                return {
                    "name": summer["name"],
                    "start": summer["start"],
                    "end": summer["end"],
                    "days_until": None,
                    "description": summer["description"],
                    "certainty": "school_dependent",
                    "caveat": "The summer holiday begins on the individual school's closing date, so no exact countdown is published; check that school's calendar.",
                }

    candidates: list[tuple[dt.date, dt.date | None, dict[str, Any]]] = []
    for published in years:
        for item in published["breaks"]:
            start_value = item["start"]
            start = parse_query_date(start_value if isinstance(start_value, str) else start_value["latest"])
            end = parse_query_date(item["end"]) if item["end"] else None
            if end is not None and query <= end:
                candidates.append((start, end, item))
            elif end is None and query.year == published["year"] and query <= dt.date(published["year"], 12, 31):
                candidates.append((start, None, item))
    if not candidates:
        raise SkillError(
            "no current or future break is available in the published years",
            exit_code=2,
            error_type="invalid_input",
        )
    start, end, item = min(candidates, key=lambda candidate: max(query, candidate[0]))
    days_until = max(0, (start - query).days)
    variable_start_has_passed = isinstance(item["start"], dict) and query >= start
    result = {
        "name": item["name"],
        "start": item["start"],
        "end": item["end"],
        "days_until": days_until,
        "description": item["description"],
        "certainty": "published" if isinstance(item["start"], str) or variable_start_has_passed else "school_dependent",
    }
    if isinstance(item["start"], dict):
        result["caveat"] = (
            "The summer holiday began on the individual school's closing date, no later than this published boundary."
            if variable_start_has_passed
            else "This is the latest possible summer-holiday start; the individual school may close earlier."
        )
    return result


def payload_base(source_url: str, retrieved: str) -> dict[str, Any]:
    return {"status": "ok", "source_url": source_url, "fetched_at": retrieved}


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout in seconds (default: 10)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Query official New Zealand school term and holiday dates")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("years", help="list all years currently published by the Ministry")
    add_common_flags(command)

    command = sub.add_parser("year", help="inspect terms, breaks and caveats for one published year")
    command.add_argument("year", type=int, help="published year, for example 2026")
    add_common_flags(command)

    command = sub.add_parser("date", help="identify the published term or break covering an ISO date")
    command.add_argument("date", help="date in YYYY-MM-DD format")
    add_common_flags(command)

    command = sub.add_parser("next-break", help="find the current or next published school break")
    command.add_argument("date", help="start date in YYYY-MM-DD format")
    add_common_flags(command)
    return parser


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    kind = payload.get("kind")
    if kind == "years":
        print("Published New Zealand school years:")
        for item in payload["years"]:
            print(f"- {item['year']}: {len(item['terms'])} terms, {len(item['breaks'])} breaks")
    elif kind == "year":
        item = payload["year"]
        print(f"{item['year']} New Zealand school terms")
        for term in item["terms"]:
            print(f"- {term['name']}: {term['description']}")
        print("School holidays")
        for school_break in item["breaks"]:
            print(f"- {school_break['name']}: {school_break['description']}")
        for caveat in item["caveats"]:
            print(f"Caveat: {caveat}")
    elif kind == "date":
        result = payload["result"]
        print(f"{payload['date']}: {result.get('name') or result['kind']} ({result['certainty']})")
        if result.get("description"):
            print(result["description"])
        if result.get("caveat"):
            print(f"Caveat: {result['caveat']}")
    elif kind == "next_break":
        result = payload["break"]
        print(f"{result['name']}: {result['description']}")
        if result["days_until"] is None:
            print("Days until: school-dependent")
        else:
            print(f"Days until: {result['days_until']}")
        if result.get("next_fixed_break"):
            next_fixed = result["next_fixed_break"]
            print(
                f"Next fixed break: {next_fixed['name']} from {next_fixed['start']} "
                f"({next_fixed['days_until']} days)"
            )
        if result.get("caveat"):
            print(f"Caveat: {result['caveat']}")
    print(f"Source: {payload['source_url']}")
    print(f"Retrieved: {payload['fetched_at']}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.timeout <= 0:
        raise SkillError("--timeout must be greater than zero", exit_code=2, error_type="invalid_input")
    if args.command in {"date", "next-break"}:
        parse_query_date(args.date)
    years, source_url, retrieved = fetch_years(args.timeout)
    base = payload_base(source_url, retrieved)
    if args.command == "years":
        return {**base, "kind": "years", "years": years}
    if args.command == "year":
        return {**base, "kind": "year", "year": year_record(years, args.year)}
    if args.command == "date":
        return {**base, "kind": "date", "date": args.date, "result": classify_date(years, args.date)}
    return {**base, "kind": "next_break", "date": args.date, "break": next_break(years, args.date)}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = run(args)
    except SkillError as exc:
        failure = {
            "status": "error",
            "code": exc.exit_code,
            "error": exc.error_type,
            "message": str(exc),
            "source_url": SOURCE_URL,
        }
        stream = sys.stdout if getattr(args, "json", False) else sys.stderr
        if getattr(args, "json", False):
            print(json.dumps(failure, indent=2, ensure_ascii=False), file=stream)
        else:
            print(f"school-terms-nz: {exc}", file=stream)
        return exc.exit_code
    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
