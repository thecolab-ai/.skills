"""Strict aggregate-only parsers for official Elections NZ finance pages."""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

FINANCE_HOSTS = {"elections.nz", "www.elections.nz"}
ANNUAL_URL = (
    "https://elections.nz/democracy-in-nz/political-parties-in-new-zealand/"
    "party-donations-and-loans-by-year"
)
EXPENSE_URLS = {
    2023: (
        "https://elections.nz/democracy-in-nz/historical-events/"
        "2023-general-election/party-expenses"
    )
}


def normalise(text: str) -> str:
    return " ".join(text.split())


def safe_source_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in FINANCE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("finance source URL is outside the official public HTTPS allowlist")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def parse_money(text: str) -> str | None:
    """Return an exact decimal NZD string; do not guess malformed or missing values."""
    value = normalise(text).rstrip("*").strip()
    if value.casefold() in {"nil", "zero"}:
        return "0.00"
    if value in {"", "-", "—", "–", "N/A"}:
        return None
    if not re.fullmatch(r"\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", value):
        raise ValueError(f"unrecognised finance amount: {value!r}")
    return str(Decimal(value.replace("$", "").replace(",", "").strip()).quantize(Decimal("0.01")))


def parse_dates(text: str) -> list[str]:
    dates: list[str] = []
    for token in re.split(r"\s*&\s*", normalise(text)):
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", token)
        if not match:
            return []
        day, month, year = map(int, match.groups())
        year = year + 2000 if year < 100 else year
        try:
            dates.append(dt.date(year, month, day).isoformat())
        except ValueError:
            return []
    return dates


def years_in(text: str) -> list[int]:
    return [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", text)]


def _single_year(text: str) -> int | None:
    values = set(years_in(text))
    return next(iter(values)) if len(values) == 1 else None


def _semantic_reporting_year(text: str) -> int | None:
    """Extract a reporting year, deliberately ignoring deadline-only years."""
    patterns = (
        r"\breturns?\s+for\s+(?:the\s+)?(20\d{2})\s+calendar year\b",
        r"\byear ending\s+[^.]*?\b(20\d{2})\b",
        r"\b(20\d{2})\s+general election\b",
        r"\bduring\s+(20\d{2})\b",
    )
    matches = {int(match.group(1)) for pattern in patterns for match in re.finditer(pattern, text, re.I)}
    return next(iter(matches)) if len(matches) == 1 else None


def _reporting_year_for_passage(
    passage: dict[str, str], page_year: int | None, current_year: int | None
) -> int | None:
    # Accordion section labels are the strongest context: prose within a 2023
    # section commonly also names its 2024 filing deadline.
    section_year = _single_year(passage["section"])
    if section_year is not None:
        return section_year
    if passage["heading"].casefold() == "what parties must report" and current_year is not None:
        return current_year
    # Election-expense pages put the election year in the h1, while their
    # later headings and paragraphs often contain no year at all.
    if page_year is not None:
        return page_year
    semantic_year = _semantic_reporting_year(passage["text"])
    if semantic_year is not None:
        return semantic_year
    return _single_year(passage["heading"]) or _single_year(passage["text"])


def party_name(text: str) -> str:
    value = re.sub(r"^Download\s+(?:the\s+)?", "", normalise(text), flags=re.I)
    value = re.split(r"\s*(?:\(|\[)\s*(?:PDF|XLS|amended|\d+(?:\.\d+)?\s*[KM]B)", value, flags=re.I)[0]
    value = re.split(r"\s+(?:amended\s+)?annual return\b", value, flags=re.I)[0]
    return value.strip().rstrip("*").strip()


class FinancePage(HTMLParser):
    """Capture tables and prose while retaining accordion reporting-year context."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.section = ""
        self.section_buffer: list[str] | None = None
        self.heading: list[str] | None = None
        self.headings: list[str] = []
        self.passage: dict[str, object] | None = None
        self.passages: list[dict[str, str]] = []
        self.table: dict[str, object] | None = None
        self.row: list[dict[str, object]] | None = None
        self.cell: dict[str, object] | None = None
        self.active_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "button" and "accordion__title" in (attributes.get("class") or ""):
            self.section_buffer = []
        if tag in {"h1", "h2", "h3", "h4"}:
            self.heading = []
        if tag in {"p", "li"}:
            self.passage = {"tag": tag, "parts": [], "section": self.section, "heading": self.headings[-1] if self.headings else ""}
        if tag == "table":
            self.table = {"section": self.section, "rows": []}
        if tag == "tr" and self.table is not None:
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = {"parts": [], "colspan": attributes.get("colspan", "1"), "links": []}
        if tag == "a" and attributes.get("href"):
            self.active_link = {"href": attributes["href"] or "", "label": ""}

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.section_buffer is not None:
            self.section_buffer.append(data)
        if self.heading is not None:
            self.heading.append(data)
        if self.passage is not None:
            parts = self.passage["parts"]
            assert isinstance(parts, list)
            parts.append(data)
        if self.cell is not None:
            parts = self.cell["parts"]
            assert isinstance(parts, list)
            parts.append(data)
        if self.active_link is not None:
            self.active_link["label"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a" and self.active_link is not None:
            if self.cell is not None:
                links = self.cell["links"]
                assert isinstance(links, list)
                links.append(self.active_link)
            self.active_link = None
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            parts = self.cell.pop("parts")
            assert isinstance(parts, list)
            self.cell["text"] = normalise("".join(parts))
            self.row.append(self.cell)
            self.cell = None
        if tag == "tr" and self.row is not None and self.table is not None:
            rows = self.table["rows"]
            assert isinstance(rows, list)
            rows.append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        if tag in {"p", "li"} and self.passage is not None and self.passage["tag"] == tag:
            parts = self.passage.pop("parts")
            assert isinstance(parts, list)
            text = normalise("".join(parts))
            if text:
                self.passages.append({"text": text, "section": str(self.passage["section"]), "heading": str(self.passage["heading"])})
            self.passage = None
        if tag in {"h1", "h2", "h3", "h4"} and self.heading is not None:
            title = normalise("".join(self.heading))
            if title:
                self.headings.append(title)
            self.heading = None
        if tag == "button" and self.section_buffer is not None:
            self.section = normalise("".join(self.section_buffer))
            self.section_buffer = None

    tables: list[dict[str, object]] = []


def parse_page(html: str) -> FinancePage:
    page = FinancePage()
    page.tables = []
    page.feed(html)
    page.close()
    return page


def _normalised_header(row: list[dict[str, object]]) -> list[str]:
    return [re.sub(r"[^a-z]", "", str(cell["text"]).casefold()) for cell in row]


def _row_party(cell: dict[str, object]) -> str:
    links = cell.get("links", [])
    assert isinstance(links, list)
    # Some Commission amended-return labels are split across adjacent anchors
    # that share one href (for example, party text then "audit report)"). Use
    # only the first label for each document before checking consistency.
    first_labels: dict[str, str] = {}
    for link in links:
        href = str(link["href"])
        first_labels.setdefault(href, str(link["label"]))
    names = {party_name(label) for label in first_labels.values() if party_name(label)}
    if len(names) > 1:
        raise ValueError("aggregate finance row contains inconsistent party labels")
    name = names.pop() if names else party_name(str(cell["text"]))
    if not name or name.casefold() in {"total", "totals"}:
        raise ValueError("aggregate finance row has a blank or total party label")
    return name


def parse_annual_aggregates(html: str, source_url: str, retrieved_at: str, year: int) -> list[dict[str, object]]:
    safe_source_url(source_url)
    page = parse_page(html)
    results: list[dict[str, object]] = []
    matched_layout = False
    for table in page.tables:
        rows = table["rows"]
        assert isinstance(rows, list)
        if not rows:
            continue
        header = [normalise(str(cell["text"])).casefold() for cell in rows[0]]
        if header[:3] != ["party", "total party donations", "total party loans"]:
            continue  # donor/contributor schedules and historical layouts are excluded
        section_years = set(years_in(str(table["section"])))
        if len(section_years) != 1:
            raise ValueError("annual aggregate table has no unambiguous reporting year")
        table_year = next(iter(section_years))
        if table_year != year:
            continue
        matched_layout = True
        for row in rows[1:]:
            if len(row) != len(header) or any(str(cell["colspan"]) != "1" for cell in row):
                raise ValueError("unsupported annual aggregate row layout")
            name = _row_party(row[0])
            filed_raw = str(row[header.index("date filed")]["text"]) if "date filed" in header else None
            for column, metric in ((1, "total_party_donations"), (2, "total_party_loans")):
                amount = parse_money(str(row[column]["text"]))
                results.append({
                    "party_name_as_published": name,
                    "reporting_year": year,
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "metric": metric,
                    "amount_nzd": amount,
                    "value_status": "missing" if amount is None else "reported",
                    "date_filed_raw": filed_raw,
                    "filing_dates": parse_dates(filed_raw) if filed_raw else [],
                    "basis": "commission_published_summary_not_recomputed_from_donors",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                })
    if not matched_layout:
        raise ValueError(
            f"annual finance page contains no supported aggregate summary table "
            f"for requested reporting year {year}"
        )
    keys = [(row["party_name_as_published"], row["reporting_year"], row["metric"]) for row in results]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate party-year metric in annual aggregate summary")
    return results


def parse_expense_aggregates(html: str, source_url: str, retrieved_at: str, year: int) -> list[dict[str, object]]:
    safe_source_url(source_url)
    page = parse_page(html)
    period_start, period_end = _expense_period(page, year)
    expected = ["party", "electionexpenselimit", "totalpartyexpenses", "broadcastingallocation", "totalbroadcastingallocationexpenses", "auditreport"]
    results: list[dict[str, object]] = []
    matched_layout = False
    for table in page.tables:
        rows = table["rows"]
        assert isinstance(rows, list)
        if not rows or _normalised_header(rows[0]) != expected:
            continue
        matched_layout = True
        for row in rows[1:]:
            if len(row) != 6 or any(str(cell["colspan"]) != "1" for cell in row):
                raise ValueError("unsupported party-expense aggregate row layout")
            name = _row_party(row[0])
            for column, metric in (
                (1, "election_expense_limit"),
                (2, "total_party_election_expenses"),
                (3, "broadcasting_allocation"),
                (4, "total_broadcasting_allocation_expenses"),
            ):
                amount = parse_money(str(row[column]["text"]))
                results.append({
                    "party_name_as_published": name,
                    "reporting_year": year,
                    "period_start": period_start,
                    "period_end": period_end,
                    "metric": metric,
                    "amount_nzd": amount,
                    "value_status": "missing" if amount is None else "reported",
                    "audit_report_raw": str(row[5]["text"]),
                    "basis": "commission_published_summary",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                })
    if not matched_layout:
        raise ValueError("party-expense page contains no supported aggregate summary table")
    return results


def _expense_period(page: FinancePage, year: int) -> tuple[str, str]:
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for passage in page.passages:
        match = re.search(
            r"regulated period.*?\b(20\d{2})\s+General Election\b.*?"
            r"ran from\s+(\d{1,2})\s+([A-Za-z]+)\s+to\s+(\d{1,2})\s+([A-Za-z]+)",
            passage["text"],
            re.I,
        )
        if not match:
            continue
        period_year, start_day, start_month, end_day, end_month = match.groups()
        if int(period_year) != year or start_month.casefold() not in months or end_month.casefold() not in months:
            raise ValueError("party-expense page has an unexpected regulated-period context")
        try:
            start = dt.date(year, months[start_month.casefold()], int(start_day))
            end = dt.date(year, months[end_month.casefold()], int(end_day))
        except ValueError as exc:
            raise ValueError("party-expense page has an invalid regulated period") from exc
        if end < start:
            raise ValueError("party-expense page has an invalid regulated period")
        return start.isoformat(), end.isoformat()
    raise ValueError(f"party-expense page contains no regulated period for reporting year {year}")


def parse_reporting_rules(html: str, source_url: str, retrieved_at: str, year: int | None) -> list[dict[str, object]]:
    safe_source_url(source_url)
    page = parse_page(html)
    current_year = next(
        (
            _semantic_reporting_year(passage["text"])
            for passage in page.passages
            if "returns for the year ending" in passage["text"].casefold()
            and _semantic_reporting_year(passage["text"]) is not None
        ),
        None,
    )
    page_year = _single_year(page.headings[0]) if page.headings else None
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for passage in page.passages:
        text = passage["text"]
        folded = text.casefold()
        reporting_year = _reporting_year_for_passage(passage, page_year, current_year)
        # Do not emit unscoped navigation labels, historical table values, or
        # rules from a reporting period other than the requested one.
        if year is not None and reporting_year != year:
            continue
        if not any(term in folded for term in ("$", "due on", "due to file", "regulated period", "component party", "gst", "must report", "must include", "not required", "had to file", "need to declare", "must declare", "required to include")):
            continue
        if text in seen:
            continue
        if "due on" in folded or "due to file" in folded:
            rule_type = "filing_deadline"
        elif "$" in text and (
            any(term in folded for term in ("report", "donat", "contribut", "loan", "expense", "allocation", "limit", "spend", "anonymous", "overseas"))
            or "expense" in passage["heading"].casefold()
        ):
            rule_type = "reporting_threshold_or_limit"
        elif "regulated period" in folded:
            rule_type = "regulated_period"
        elif "component party" in folded:
            rule_type = "component_party"
        elif "gst" in folded:
            rule_type = "gst_treatment"
        elif any(term in folded for term in ("must report", "must include", "not required", "had to file", "need to declare", "must declare", "required to include")):
            rule_type = "reporting_requirement"
        else:
            continue
        seen.add(text)
        results.append({
            "rule_type": rule_type,
            "reporting_year": reporting_year,
            "effective_from": None,
            "effective_to": None,
            "heading": passage["heading"],
            "section": passage["section"],
            "evidence_text": text,
            "amounts_nzd_mentioned": [parse_money(value) for value in re.findall(r"\$[\d,]+(?:\.\d+)?", text)],
            "interpretation_status": "source_wording_only_not_normalised_legal_rule",
            "source_url": source_url,
            "retrieved_at": retrieved_at,
        })
    if not results:
        scope = f" scoped to {year}" if year is not None else ""
        raise ValueError(f"finance page contains no supported reporting-rule passages{scope}")
    return results


def finance_source(kind: str, year: int) -> str:
    if kind == "annual":
        return ANNUAL_URL
    if year not in EXPENSE_URLS:
        raise ValueError("unsupported party-expense election year")
    return EXPENSE_URLS[year]


def filter_party(rows: list[dict[str, object]], query: str | None) -> list[dict[str, object]]:
    if not query:
        return rows
    needle = normalise(query).casefold()
    return [row for row in rows if needle in normalise(str(row.get("party_name_as_published", ""))).casefold()]
