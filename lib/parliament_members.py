"""Parsers for New Zealand Parliament member directory pages."""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin


def clean(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())


def _tables(page_html: str) -> list[list[list[str]]]:
    parsed = []
    for table in re.findall(r"<table\b.*?</table>", page_html, re.S | re.I):
        rows = []
        for row in re.findall(r"<tr\b.*?</tr>", table, re.S | re.I):
            cells = [clean(cell) for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row, re.S | re.I)]
            if cells:
                rows.append(cells)
        if rows:
            parsed.append(rows)
    return parsed


def parse_members(page_html: str, source_url: str, retrieved_at: str) -> list[dict[str, str]]:
    for raw_table in re.findall(r"<table\b.*?</table>", page_html, re.S | re.I):
        rows = _tables(raw_table)
        if not rows:
            continue
        table = rows[0]
        headers = [value.casefold() for value in table[0]]
        if not {"party", "electorate"}.issubset(headers):
            continue
        name_index = next((index for index, value in enumerate(headers) if "surname" in value or value == "name"), 0)
        party_index, electorate_index = headers.index("party"), headers.index("electorate")
        links = re.findall(r'<a\b[^>]*href="([^"]*/members-of-parliament/[^"]+)"', raw_table, re.I)
        output = []
        for index, row in enumerate(table[1:]):
            if max(name_index, party_index, electorate_index) >= len(row):
                continue
            profile_url = urljoin(source_url, links[index]) if index < len(links) else source_url
            output.append(
                {
                    "name": row[name_index],
                    "party": row[party_index],
                    "electorate": row[electorate_index],
                    "member_type": "list" if row[electorate_index].casefold() == "list" else "electorate",
                    "record_status": "current",
                    "source_url": profile_url,
                    "retrieved_at": retrieved_at,
                }
            )
        if output:
            return output
    raise ValueError("Parliament member directory contained no member table")


def parse_profile(page_html: str, source_url: str, retrieved_at: str) -> dict[str, object]:
    title = re.search(r"<h1\b[^>]*>(.*?)</h1>", page_html, re.S | re.I)
    published = re.search(r"Published date:\s*</?[^>]*>?\s*([^<\n]+)", page_html, re.I)
    if not title:
        raise ValueError("Parliament member profile is missing its title")
    current_match = re.search(r"<h3\b[^>]*>\s*Current Roles\s*</h3>(.*?)(?=<h3\b|<h2\b|$)", page_html, re.S | re.I)
    roles = []
    if current_match:
        for table in _tables(current_match.group(1)):
            headers = [value.casefold() for value in table[0]]
            if "role" not in headers or len(headers) < 2:
                continue
            subject_header = table[0][0]
            for row in table[1:]:
                if len(row) < 2:
                    continue
                roles.append(
                    {
                        "kind": subject_header,
                        "subject": row[0],
                        "role": row[1],
                        "start": row[2] if len(row) > 2 else None,
                        "end": row[3] if len(row) > 3 and row[3] else None,
                    }
                )
    emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@parliament\.govt\.nz", page_html, re.I)))
    return {
        "name": clean(title.group(1)),
        "published_date": clean(published.group(1)) if published else None,
        "current_roles": roles,
        "record_status": "current",
        "official_parliament_emails": emails,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }
