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


def parse_term_dates(text: str, year: int) -> tuple[str | dict[str, str], str | dict[str, str]]:
    dates = date_fragments(text, year)
    lowered = text.lower()
    if lowered.startswith("starts between") and len(dates) >= 3:
        return (
            {"precision": "range", "earliest": dates[0], "latest": dates[1]},
            {"precision": "fixed", "date": dates[2]},
        )
    if "to no later than" in lowered and len(dates) >= 2:
        return dates[0], {"precision": "no_later_than", "latest": dates[1]}
    if len(dates) >= 2:
        return dates[0], dates[1]
    raise SkillError(
        f"could not parse published term dates for {year}: {text}",
        exit_code=6,
        error_type="source_schema",
    )


def parse_break_dates(text: str, year: int) -> tuple[str | dict[str, str], str | None]:
    dates = date_fragments(text, year)
    if text.lower().startswith("start no later than") and dates:
        return {"precision": "no_later_than", "latest": dates[0]}, None
    if len(dates) >= 2:
        return dates[0], dates[1]
    raise SkillError(
        f"could not parse published holiday dates for {year}: {text}",
        exit_code=6,
        error_type="source_schema",
    )


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
            if "half days" in lowered and ("primary" in lowered or "secondary" in lowered):
                record["opening_requirements"].append(text)
            if "flexibility" in lowered:
                record["caveats"].append(text)
    years = [by_year[key] for key in sorted(by_year)]
    invalid = [
        str(item["year"])
        for item in years
        if len(item["terms"]) != 4
        or len(item["breaks"]) != 4
        or any("start" not in entry or "end" not in entry for entry in item["terms"])
        or any("start" not in entry or "end" not in entry for entry in item["breaks"])
    ]
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


def previous_summer_holiday(years: list[dict[str, Any]], query: dt.date) -> dict[str, Any] | None:
    """Return the prior year's summer break before the earliest Term 1 opening."""
    current = next((item for item in years if item["year"] == query.year), None)
    previous = next((item for item in years if item["year"] == query.year - 1), None)
    if current is None or previous is None:
        return None
    term_one = current["terms"][0]
    if term_one["name"] != "Term 1" or not isinstance(term_one["start"], dict):
        return None
    if query >= parse_query_date(term_one["start"]["earliest"]):
        return None
    summer = next((item for item in previous["breaks"] if item["name"] == "Summer holidays"), None)
    if summer is None:
        return None
    return summer


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

    prior_summer = previous_summer_holiday(years, query)
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
                "The summer holiday starts on each school's closing date, no later than the published date, and runs for 5 or 6 weeks.",
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
                    return classification(
                        item,
                        "school_term",
                        "school_dependent",
                        "Term 4 starts on the published date, but each school may close before the no-later-than end date.",
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
    prior_summer = previous_summer_holiday(years, query)
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
    result = {
        "name": item["name"],
        "start": item["start"],
        "end": item["end"],
        "days_until": days_until,
        "description": item["description"],
        "certainty": "published" if isinstance(item["start"], str) else "school_dependent",
    }
    if isinstance(item["start"], dict):
        result["caveat"] = "This is the latest possible summer-holiday start; the individual school may close earlier."
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
        print(f"Days until: {result['days_until']}")
        if result.get("caveat"):
            print(f"Caveat: {result['caveat']}")
    print(f"Source: {payload['source_url']}")
    print(f"Retrieved: {payload['fetched_at']}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.timeout <= 0:
        raise SkillError("--timeout must be greater than zero", exit_code=2, error_type="invalid_input")
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
