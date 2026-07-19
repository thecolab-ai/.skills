"""Parse specific Electoral Commission exports and finance-document pages."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from html import unescape
from urllib.parse import urljoin, urlparse


def _csv_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))) if any(cell.strip() for cell in row)]


def _record(values: dict[str, object], source_url: str, retrieved_at: str) -> dict[str, object]:
    return {**values, "source_url": source_url, "retrieved_at": retrieved_at, "result_status": "official final"}


def parse_overall_results(text: str, source_url: str, retrieved_at: str) -> list[dict[str, object]]:
    rows = _csv_rows(text)
    start = next((index for index, row in enumerate(rows) if row and row[0] == "Parties(Grouped)"), None)
    if start is None:
        raise ValueError("overall-results export is missing the Parties(Grouped) header")
    results: list[dict[str, object]] = []
    category: str | None = None
    for row in rows[start + 1 :]:
        padded = row + [""] * (9 - len(row))
        if padded[0] == "State of the Parties":
            break
        if padded[0] in {"Registered Parties with List", "Unregistered Parties"}:
            category = padded[0]
            continue
        if not padded[0] or not re.fullmatch(r"-?\d+", padded[1] or ""):
            continue
        results.append(_record({
            "party": padded[0], "category": category, "list_seats": int(padded[1]),
            "party_votes": int(padded[2] or 0), "party_vote_percentage": float(padded[3] or 0),
            "party_list_size": int(padded[4] or 0), "electorate_seats": int(padded[5] or 0),
            "electorate_votes": int(padded[6] or 0), "electorate_vote_percentage": float(padded[7] or 0),
            "electorate_candidates": int(padded[8] or 0), "total_seats": int(padded[1]) + int(padded[5] or 0),
        }, source_url, retrieved_at))
    if not results:
        raise ValueError("overall-results export contained no party records")
    return results


def parse_turnout(text: str, source_url: str, retrieved_at: str) -> list[dict[str, object]]:
    rows = _csv_rows(text)
    start = next((index for index, row in enumerate(rows) if row and row[0] == "Electoral District"), None)
    if start is None:
        raise ValueError("turnout export is missing the Electoral District header")
    names = (
        "electorate", "ordinary_valid_votes", "special_valid_votes", "valid_votes", "ordinary_informal_votes",
        "special_informal_votes", "informal_votes", "ordinary_disallowed_votes", "special_disallowed_votes",
        "total_votes_cast", "electors_on_master_roll", "electoral_population", "turnout_percentage", "informal_percentage",
    )
    results: list[dict[str, object]] = []
    for row in rows[start + 1 :]:
        if row and row[0].startswith("("):
            continue
        if len(row) < len(names) or not row[0] or not row[1].replace(",", "").isdigit():
            continue
        values: dict[str, object] = {"electorate": row[0]}
        for index, name in enumerate(names[1:], 1):
            raw = row[index].replace(",", "")
            values[name] = float(raw) if "percentage" in name else int(raw)
        results.append(_record(values, source_url, retrieved_at))
    if not results:
        raise ValueError("turnout export contained no electorate records")
    return results


def parse_winning_candidates(text: str, source_url: str, retrieved_at: str) -> list[dict[str, object]]:
    rows = _csv_rows(text)
    header = next((index for index, row in enumerate(rows) if row and row[0] == "Electoral District" and "Electorate Candidate" in row), None)
    if header is None:
        raise ValueError("winning-candidates export is missing its header")
    results = []
    for row in rows[header + 1 :]:
        padded = row + [""] * (7 - len(row))
        if not padded[0] or not padded[3].replace(",", "").isdigit():
            continue
        results.append(_record({
            "electorate": padded[0], "candidate": padded[1], "party": padded[2],
            "valid_votes": int(padded[3].replace(",", "")), "majority": int(padded[4].replace(",", "") or 0),
            "vote_percentage": float(padded[5].rstrip("%") or 0), "on_party_list": padded[6].casefold() == "yes",
        }, source_url, retrieved_at))
    if not results:
        raise ValueError("winning-candidates export contained no candidate records")
    return results


def normalise_name(value: str) -> str:
    # Remove combining marks after compatibility decomposition so an ASCII
    # query such as "Chloe" matches the published "Chlöe" spelling without
    # splitting the name into the false tokens "chlo e".
    folded = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    ).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


def candidate_matches(candidate: str, query: str) -> bool:
    forms = {normalise_name(candidate)}
    if "," in candidate:
        family, given = candidate.split(",", 1)
        forms.add(normalise_name(f"{given} {family}"))
    needle = normalise_name(query)
    tokens = needle.split()
    return any(needle in form or all(token in form.split() for token in tokens) for form in forms)


def parse_document_links(html: str, source_url: str, retrieved_at: str, query: str) -> list[dict[str, object]]:
    host = urlparse(source_url).hostname
    results: list[dict[str, object]] = []
    blocks = [body for _, body in re.findall(r'<(section|article|tr|li)\b[^>]*>(.*?)</\1>', html, flags=re.I | re.S)] or [html]
    for block in blocks:
        block_text = " ".join(unescape(re.sub(r"<[^>]+>", " ", block)).split())
        if query.casefold() not in block_text.casefold():
            continue
        for href, body in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S):
            url = urljoin(source_url, unescape(href))
            title = " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())
            if urlparse(url).hostname != host or not urlparse(url).path.lower().endswith((".pdf", ".csv", ".xlsx")):
                continue
            results.append({"title": title or url.rsplit("/", 1)[-1], "document_url": url, "context": block_text[:600], "source_url": source_url, "retrieved_at": retrieved_at})
    return list({row["document_url"]: row for row in results}.values())
