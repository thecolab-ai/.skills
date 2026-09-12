#!/usr/bin/env python3
"""Conservative parser for official NZ Parliament Journal divisions."""
from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Any

DATE = re.compile(r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I)
MONTHS = {name.lower(): number for number, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
QUESTION = re.compile(
    r"^On the question(?:,\s*|\s+that\s+).+the votes were recorded as follows:$",
    re.I,
)
VOTE_LIKE = re.compile(r"\bthe votes were recorded as follows:\s*$", re.I)
TOTAL = re.compile(r"^(Ayes|Noes|Abstentions)\s*[:,]?\s*(\d+)\s*$", re.I)
PARTY_COUNT = re.compile(r"^(.+?)\s+(\d+)$")
# A singleton can be a surname, party label, or structural token. Preserve it,
# but never promote it to a person without stronger source semantics.
SINGLETON_LABEL = re.compile(r"^[^\W\d_][\w\-\u2019\u02bc']*$", re.UNICODE)
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class BlockParser(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "h4", "h5", "p", "li", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, str]] = []
        self.current: dict[str, Any] | None = None
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
            return
        if self.skip:
            return
        values = dict(attrs)
        if tag in self.BLOCKS and self.current is None:
            self.current = {"tag": tag, "classes": values.get("class") or "", "parts": []}
        elif self.current is not None and tag in {"br", "td", "th", "p"}:
            self.current["parts"].append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
            return
        if self.current is not None and tag == self.current["tag"]:
            text = " ".join("".join(self.current["parts"]).split())
            if text:
                self.blocks.append({"tag": tag, "classes": self.current["classes"], "text": text})
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and not self.skip:
            self.current["parts"].append(data)


def _printed_date(text: str) -> str | None:
    match = DATE.fullmatch(text.strip())
    if not match or match.group(2).lower() not in MONTHS:
        return None
    try:
        return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1))).isoformat()
    except ValueError:
        return None


def parse_search(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("source schema changed: search results must be an array")
    for key in ("page", "pageSize", "totalResults"):
        if type(payload.get(key)) is not int or payload[key] < 0:
            raise ValueError(f"source schema changed: {key} must be a non-negative integer")
    rows = []
    for item in payload["results"]:
        if not isinstance(item, dict) or not UUID.fullmatch(str(item.get("id", ""))):
            raise ValueError("source schema changed: result id is not a UUID")
        if item.get("documentType") != "Journal" or not isinstance(item.get("title"), str):
            raise ValueError("source schema changed: unexpected Journal search row")
        rows.append({
            "id": item["id"], "title": item["title"],
            "parliament_number": item.get("parliamentNumber"),
            "publication_date": item.get("publicationDate"),
            "detail_url": f"https://journals.parliament.nz/api/data/Journal/{item['id']}",
        })
    if len(rows) > payload["pageSize"]:
        raise ValueError("source schema changed: result count exceeds pageSize")
    return {"results": rows, "page": payload["page"], "page_size": payload["pageSize"], "total_results": payload["totalResults"]}


def _participants(detail: str, total: int, choice: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    chunks = [part.strip().rstrip(".") for part in detail.split(";") if part.strip().rstrip(".")]
    for chunk in chunks:
        party = PARTY_COUNT.fullmatch(chunk)
        if party and party.group(1).strip() and int(party.group(2)) > 0:
            records.append({"choice": choice, "entity_kind": "party", "source_label": party.group(1).strip(), "recorded_count": int(party.group(2)), "attribution_basis": "explicit_party_count"})
        elif SINGLETON_LABEL.fullmatch(chunk):
            records.append({"choice": choice, "entity_kind": "unknown", "source_label": chunk, "recorded_count": 1, "attribution_basis": "unresolved_singleton_label"})
            warnings.append(f"ambiguous_singleton_label_{choice}")
        else:
            return [], [f"participants_unresolved_{choice}"]
    if sum(record["recorded_count"] for record in records) != total:
        return [], [f"participant_total_mismatch_{choice}"]
    return records, warnings


def parse_journal(payload: Any, source_url: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("DocumentType") != "Journal":
        raise ValueError("source schema changed: expected a Journal object")
    document_id = str(payload.get("Id", ""))
    html = payload.get("PublishHtml")
    if not UUID.fullmatch(document_id) or not isinstance(html, str) or not html.strip():
        raise ValueError("source schema changed: Journal requires UUID Id and non-empty PublishHtml")
    parser = BlockParser()
    parser.feed(html)
    parser.close()
    blocks = parser.blocks
    if not blocks:
        raise ValueError("parser failure: Journal HTML produced no content blocks")
    headings: list[tuple[int, str]] = []
    event_date = None
    sitting_date = None
    votes: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        printed = _printed_date(block["text"])
        if printed and (block["tag"].startswith("h") or "jps-JHeadNextDay" in block["classes"].split()):
            event_date = printed
            if "jps-JHeadNextDay" not in block["classes"].split():
                sitting_date = printed
        if block["tag"].startswith("h"):
            level = int(block["tag"][1])
            headings = [(old_level, text) for old_level, text in headings if old_level < level]
            headings.append((level, block["text"]))
        if not QUESTION.fullmatch(block["text"]):
            if VOTE_LIKE.search(block["text"]):
                diagnostics.append({
                    "kind": "unrecognised_division_question",
                    "question": block["text"],
                    "reason": "vote-like wording did not match a supported Journal question form",
                })
            i += 1
            continue
        j = i + 1
        totals: dict[str, int | None] = {"ayes": None, "noes": None, "abstentions": None}
        participants: list[dict[str, Any]] = []
        warnings: list[str] = []
        while j + 1 < len(blocks) and j < i + 7:
            total_match = TOTAL.fullmatch(blocks[j]["text"])
            classes = blocks[j]["classes"].split()
            detail_classes = blocks[j + 1]["classes"].split()
            if not total_match or "jps-JVResultParty" not in classes or "jps-JVParty" not in detail_classes:
                break
            choice = total_match.group(1).lower()
            count = int(total_match.group(2))
            if totals[choice] is not None:
                warnings.append(f"duplicate_choice_{choice}")
            else:
                totals[choice] = count
                records, side_warnings = _participants(blocks[j + 1]["text"], count, choice)
                participants.extend(records)
                warnings.extend(side_warnings)
            j += 2
        if j == i + 1:
            diagnostics.append({"kind": "unsupported_division", "question": block["text"], "reason": "party vote style and tally rows were not established"})
            i += 1
            continue
        if totals["ayes"] is None or totals["noes"] is None:
            warnings.append("incomplete_tallies")
        if not event_date:
            warnings.append("event_date_unresolved")
        context = [text for _, text in headings]
        votes.append({
            "document_id": document_id, "source_url": source_url,
            "source_authority": "weekly_draft", "event_date": event_date,
            "sitting_date": sitting_date, "vote_type": "party",
            "question_text": block["text"], "heading_context": context,
            "totals": totals, "participants": participants,
            "warnings": sorted(set(warnings)),
        })
        i = j
    return {
        "document": {"id": document_id, "title": payload.get("Title"), "start_date": payload.get("StartDate"), "created_date": payload.get("CreatedDate"), "last_updated_date": payload.get("LastUpdatedDate"), "source_url": source_url, "authority": "weekly_draft"},
        "votes": votes, "diagnostics": diagnostics,
    }
