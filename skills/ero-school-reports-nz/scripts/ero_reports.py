"""Parse Education Review Office institution pages with section provenance."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch

ALLOWED_HOSTS = {"ero.govt.nz", "www.ero.govt.nz"}
REPORTS_API_URL = "https://www.ero.govt.nz/api/ReportsApi/GetReports"


class Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.heading = None
        self.heading_parts = []
        self.sections = []
        self.current = None
        self.links = []
        self.active_link = None
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attributes = dict(attrs)
        if tag in {"nav", "footer", "script", "style", "form"}:
            self.ignored.append((tag, self.depth))
        if self.ignored:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5"}:
            self.heading = (tag, self.depth)
            self.heading_parts = []
        if tag == "a" and attributes.get("href"):
            self.active_link = {"href": attributes["href"], "depth": self.depth, "parts": []}
        if tag in {"p", "li", "br", "tr"} and self.current:
            self.current["parts"].append("\n")

    def handle_data(self, data):
        if self.ignored:
            return
        if self.heading:
            self.heading_parts.append(data)
        elif self.current:
            self.current["parts"].append(data)
        if self.active_link:
            self.active_link["parts"].append(data)

    def handle_endtag(self, tag):
        if self.ignored and self.ignored[-1] == (tag, self.depth):
            self.ignored.pop()
        if self.ignored:
            self.depth -= 1
            return
        if tag == "a" and self.active_link and self.active_link["depth"] == self.depth:
            self.links.append([self.active_link["href"], "".join(self.active_link["parts"])])
            self.active_link = None
        if self.heading and self.heading[0] == tag and self.heading[1] == self.depth:
            title = " ".join("".join(self.heading_parts).split())
            if title:
                self.current = {"level": int(tag[1]), "heading": title, "parts": []}
                self.sections.append(self.current)
            self.heading = None
            self.heading_parts = []
        self.depth -= 1


def _institution_title(title, url):
    title = " ".join(title.split())
    if title and not re.match(r"^(?:view|read)\b", title, re.IGNORECASE):
        return title
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def parse_page(html, source_url, retrieved_at):
    if re.search(r"captcha|access denied", html, re.IGNORECASE):
        raise ValueError("ERO source returned an access challenge")
    parser = Extract()
    parser.feed(html)
    host = urlparse(source_url).hostname
    links = {}
    link_scores = {}
    for href, title in parser.links:
        url = urljoin(source_url, href)
        title = " ".join(title.split())
        generic = not title or bool(re.match(r"^(?:view|read)\b", title, re.IGNORECASE))
        if urlparse(url).hostname == host and re.search(r"/institution/\d+", url):
            candidate = {"title": _institution_title(title, url), "source_url": url, "retrieved_at": retrieved_at}
            score = 0 if generic else 1
            if score > link_scores.get(url, -1):
                links[url] = candidate
                link_scores[url] = score
    sections = []
    for index, section in enumerate(parser.sections):
        text = " ".join("".join(section["parts"]).split())
        sections.append(
            {
                "section_index": index,
                "heading": section["heading"],
                "level": section["level"],
                "text": text,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "provenance": {"format": "html", "section_heading": section["heading"], "section_index": index},
            }
        )
    if not sections and not links:
        raise ValueError("ERO page contained no recognisable institutions or report sections")
    return {"institutions": list(links.values()), "sections": sections}


def school_id(value):
    match = re.search(r"(?:/institution/)?(\d+)", value)
    return match.group(1) if match else None


def fetch_reports_index(search_term, *, page_number=1, page_size=100, timeout=30):
    url = (
        f"{REPORTS_API_URL}?searchTerm={quote_plus(search_term)}"
        f"&pageNumber={page_number}&pageSize={page_size}"
    )
    payload = json.loads(nzfetch.fetch_text(url, timeout=timeout, allowed_hosts=ALLOWED_HOSTS))
    if not isinstance(payload, dict):
        raise ValueError("ERO reports index returned an unexpected payload")  # noqa: TRY004
    return payload


def _matches_report_organisation(row, query):
    ident = school_id(query)
    if ident:
        return str(row.get("moeNumberDisplay") or row.get("moeNumber") or "") == ident
    needle = query.casefold()
    return needle in str(row.get("name") or "").casefold()


def _report_organisation_rows(payload):
    if not isinstance(payload, dict) or "reportOrganisation" not in payload:
        raise ValueError("ERO reports index returned an unexpected payload")
    rows = payload["reportOrganisation"]
    if not isinstance(rows, list):
        raise ValueError("ERO reports index returned an unexpected payload")  # noqa: TRY004
    return rows


def report_organisation_rows(payload, retrieved_at, query=None):
    rows = _report_organisation_rows(payload)
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if query is not None and not _matches_report_organisation(row, query):
            continue
        results.append(
            {
                "title": str(row.get("name") or "").strip(),
                "source_url": urljoin("https://www.ero.govt.nz", str(row.get("url") or "")),
                "retrieved_at": retrieved_at,
            }
        )
    return results


def resolve_report_organisation_url(payload, query):
    rows = _report_organisation_rows(payload)
    for row in rows:
        if isinstance(row, dict) and _matches_report_organisation(row, query):
            return urljoin("https://www.ero.govt.nz", str(row.get("url") or ""))
    raise ValueError("ERO institution ID was not present in the official reports index")


def resolve_institution_url(query, *, timeout=30, page_size=100):
    search_term = school_id(query) or query
    payload = fetch_reports_index(search_term, page_size=page_size, timeout=timeout)
    return resolve_report_organisation_url(payload, query)


def report_sections(page):
    sections = page["sections"]
    out = []
    current_date = None
    current_school = None
    markers = []
    date_pattern = r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b"
    for index, section in enumerate(sections):
        if section["level"] == 1:
            current_school = section["heading"]
        heading = section["heading"].casefold()
        text = f"{section['heading']} {section['text']}"
        heading_has_date = re.search(date_pattern, section["heading"], re.IGNORECASE)
        text_has_date = re.search(date_pattern, section["text"], re.IGNORECASE)
        is_report_marker = section["level"] == 2 and heading != "other reports" and not heading.startswith("reports for ") and (
            "report" in heading or any(key in heading for key in ("evaluation", "assurance", "profile")) or heading_has_date or text_has_date
        )
        if is_report_marker:
            date_match = heading_has_date or text_has_date or re.search(date_pattern, text, re.IGNORECASE)
            if date_match:
                try:
                    current_date = datetime.strptime(date_match.group(1), "%d %b %Y").date().isoformat()  # noqa: DTZ007
                except ValueError:
                    try:
                        current_date = datetime.strptime(date_match.group(1), "%d %B %Y").date().isoformat()  # noqa: DTZ007
                    except ValueError:
                        pass
            markers.append((index, current_school, current_date))
    marker_indices = {item[0] for item in markers}
    for _, (index, school, published) in enumerate(markers):
        section = sections[index]
        end = len(sections)
        for cursor in range(index + 1, len(sections)):
            if (
                cursor in marker_indices
                or sections[cursor]["level"] < section["level"]
                or (section["level"] == 2 and sections[cursor]["level"] == 2)
            ):
                end = cursor
                break
        report_content = sections[index:end]
        slug = re.sub(r"[^a-z0-9]+", "-", section["heading"].casefold()).strip("-")
        institution = re.search(r"/institution/(\d+)", section["source_url"])
        stable_id = f"{institution.group(1) + '/' if institution else ''}{published or 'date-unknown'}:{slug}"
        out.append(
            {
                "id": stable_id,
                "school": school,
                "report_type": section["heading"],
                "published_on": published,
                "source_url": section["source_url"],
                "retrieved_at": section["retrieved_at"],
                "section": section,
                "sections": report_content,
            }
        )
    return sorted(out, key=lambda item: (item["published_on"] or "", item["id"]), reverse=True)


def require_report(reports, requested):
    report = next((item for item in reports if item["id"] == requested), None)
    if report is None:
        raise ValueError("requested report ID was not found on the official institution page")
    return report
