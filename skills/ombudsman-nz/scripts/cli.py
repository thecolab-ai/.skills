#!/usr/bin/env python3
"""Query Ombudsman NZ public complaint data and publication resources.

This CLI performs discovery from the public HTML listings at
https://www.ombudsman.parliament.nz/resources and parses publication metadata,
case-note/report listings, and the OIA/LGOIMA complaints spreadsheets when
available.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://www.ombudsman.parliament.nz"
RESOURCES_URL = BASE_URL + "/resources"
UA = "thecolab-ai/ombudsman-nz-skill (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 30
DEFAULT_LIMIT = 20
MAX_DISCOVERY_PAGES = 8
MAX_XLSX_ROWS = 12

SOURCE_FALLBACKS = {
    "case notes": "74",
    "complaints data": "1989",
    "complaints": "1989",
    "opcat": "1993",
    "reports": "2148",
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


class CliError(RuntimeError):
    """User-visible command failure from upstream or parsing."""

    def __init__(self, message: str, *, source_url: str | None = None, code: str = "error"):
        super().__init__(message)
        self.source_url = source_url
        self.code = code


class UpstreamUnavailable(CliError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or "")).replace("\xa0", " ")).strip()


def normalise_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower().strip())


def safe_strip(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_http_prefix(url: str) -> str:
    return url.replace("https://", "")


def to_absolute(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return urllib.parse.urljoin(BASE_URL, path_or_url)


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    data, final_url, _ = fetch_bytes(url, timeout=timeout)
    encoding = "utf-8"
    return data.decode(encoding, errors="replace"), final_url


def fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xml,application/json,text/csv;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-NZ,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            body = resp.read()
            return body, resp.geturl(), (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = exc.read(600).decode("utf-8", errors="replace")
        except Exception:
            snippet = ""
        snippet = safe_strip(snippet)[:220]
        if exc.code in {403, 429}:
            raise UpstreamUnavailable(
                f"HTTP {exc.code} from upstream: likely bot/blocking or bot-protection page. {snippet}",
                source_url=url,
                code="upstream_blocked",
            ) from exc
        raise CliError(
            f"HTTP {exc.code} from upstream {url}. {snippet}",
            source_url=url,
            code="upstream_http",
        ) from exc
    except urllib.error.URLError as exc:
        raise UpstreamUnavailable(
            f"network error contacting {url}: {exc.reason}",
            source_url=url,
            code="upstream_unreachable",
        ) from exc
    except TimeoutError as exc:
        raise UpstreamUnavailable(
            f"timeout while fetching {url}",
            source_url=url,
            code="upstream_timeout",
        ) from exc


def parse_resource_cards(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for block_m in re.finditer(
        r"<li[^>]*class=\"[^\"]*\bslat\b[^\"]*\"[\s\S]*?</li>",
        html,
        flags=re.I,
    ):
        block = block_m.group(0)
        title_m = re.search(r"<h3[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*</h3>", block, flags=re.I | re.S)
        if not title_m:
            continue

        raw_href = title_m.group(1)
        raw_title = title_m.group(2)
        title = safe_strip(raw_title)
        url = to_absolute(raw_href)
        slug = urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1]

        terms = []
        published_at = None
        category = []
        for term_m in re.finditer(
            r'<span[^>]*class="([^"]*)"[^>]*>(.*?)</span>',
            block,
            flags=re.I | re.S,
        ):
            cls = term_m.group(1)
            if "slat__term" not in cls:
                continue
            text = safe_strip(term_m.group(2))
            if not text:
                continue
            if "slat__date" in cls:
                dt_m = re.search(r"datetime=\"([^\"]+)\"", term_m.group(0), flags=re.I)
                if dt_m:
                    published_at = dt_m.group(1)
            else:
                category.append(text)

        snippet_m = re.search(
            r'<div[^>]*class="[^\"]*slat__body[^\"]*"[^>]*>(.*?)</div>',
            block,
            flags=re.I | re.S,
        )
        snippet = safe_strip(snippet_m.group(1)) if snippet_m else ""

        items.append(
            {
                "title": title,
                "slug": slug,
                "source_url": url,
                "category": category,
                "published_at": published_at,
                "snippet": snippet,
            }
        )
    return items


def next_page_url(html: str) -> str | None:
    next_m = re.search(
        r'<li[^>]*class="[^"]*pager__item--next[^"]*"[\s\S]*?<a[^>]+href="([^"]+)"',
        html,
        flags=re.I,
    )
    if not next_m:
        return None
    return next_m.group(1)


def build_resources_url(
    *,
    category_id: str | None = None,
    query: str | None = None,
    page: int | None = None,
) -> str:
    params: list[tuple[str, str]] = []
    if category_id:
        params.append(("f[0]", f"category:{category_id}"))
    if query:
        params.append(("query", query))
    if page:
        params.append(("page", str(page)))
    if not params:
        return RESOURCES_URL
    return RESOURCES_URL + "?" + urllib.parse.urlencode(params, safe=":")


def discover_categories(timeout: int) -> dict[str, str]:
    html, _ = fetch_text(RESOURCES_URL, timeout=timeout)
    found: dict[str, str] = {**SOURCE_FALLBACKS}
    for match in re.finditer(
        r'href="([^"]*f%5B0%5D=category%3A(\d+)[^\"]*)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        category_id = match.group(2)
        label = normalise_text(match.group(3)).lower()
        if not label:
            continue
        found[label] = category_id
        compact = re.sub(r"\s+", "", label)
        found[compact] = category_id
        found[re.sub(r"[^a-z0-9]+", "-", label)] = category_id
    # Keep deterministic fallback with canonical names.
    for canonical, category_id in SOURCE_FALLBACKS.items():
        found.setdefault(canonical, category_id)
        found.setdefault(re.sub(r"[^a-z0-9]+", "", canonical), category_id)
    return found


def resolve_category(category: str | None, categories: dict[str, str]) -> str | None:
    if not category:
        return None
    text = category.strip()
    if text.isdigit():
        return text
    normal = normalise_slug(text)
    compact = re.sub(r"\s+", "", normal)
    candidates = {
        text.lower(),
        normal,
        compact,
        re.sub(r"[^a-z0-9]+", "-", normal),
    }
    for candidate in candidates:
        if candidate in categories:
            return categories[candidate]
    return None


def discover_publications(
    *,
    query: str | None,
    category_id: str | None,
    max_pages: int,
    timeout: int,
    limit: int,
    require_match: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    query_norm = normalise_slug(query or "")

    page = 0
    while page < max_pages:
        url = build_resources_url(category_id=category_id, query=query if query else None, page=page if page else None)
        if url in seen_urls:
            break
        seen_urls.add(url)
        html, _ = fetch_text(url, timeout=timeout)
        cards = parse_resource_cards(html)
        for card in cards:
            if card["source_url"] in {r["source_url"] for r in results}:
                continue
            if query_norm and require_match:
                haystack = normalise_slug(" ".join([card["title"], card["snippet"], " ".join(card["category"])]) )
                if query_norm not in haystack:
                    continue
            results.append(card)
        if len(results) >= limit:
            break
        n = next_page_url(html)
        if not n:
            break
        if n.startswith("#"):
            break
        page += 1

    return results[:limit]


def discover_source_categories(limit: int = 80, timeout: int = DEFAULT_TIMEOUT) -> dict[str, str]:
    return discover_categories(timeout)


def parse_case_notes_like_period(text: str | None) -> str | None:
    if not text:
        return None
    norm = text.lower()

    m = re.search(r"(20\d{2})\s*[-\s]?[Hh]([12])", norm)
    if m:
        return f"{m.group(1)}-H{m.group(2)}"

    month_patterns = "|".join(sorted(MONTHS.keys(), key=len, reverse=True))
    m = re.search(
        rf"(?:1\s*)?(?P<start>{month_patterns})[^a-z]{{1,15}}(?:and|to|\-)?\s*(?:31\s*)?(?P<end>{month_patterns})\s*(?P<year>20\d{{2}})",
        norm,
    )
    if m:
        start_month = MONTHS.get(m.group("start"), None)
        end_month = MONTHS.get(m.group("end"), None)
        year = m.group("year")
        if start_month and end_month:
            if start_month <= 6:
                return f"{year}-H1"
            return f"{year}-H2"

    m = re.search(
        rf"(?P<start>{month_patterns})\s*[-–]\s*(?P<end>{month_patterns})\s+(?P<year>20\d{{2}})",
        norm,
    )
    if m:
        start_month = MONTHS.get(m.group("start"), None)
        if start_month is None:
            return None
        year = m.group("year")
        return f"{year}-H1" if start_month <= 6 else f"{year}-H2"

    return None


def classify_dataset_file(file_info: dict[str, Any], title_hint: str | None = None) -> tuple[str | None, str | None, str | None]:
    # Attachment titles carry the specific act/kind (for example "OIA complaints
    # completed"), while the parent resource often says "OIA and LGOIMA
    # complaints received". Classify from the attachment title/URL first and use
    # the parent only as a period fallback to avoid turning every OIA attachment
    # into LGOIMA/received.
    own_text = normalise_slug(((file_info.get("title") or "") + " " + (file_info.get("source_url") or "")).lower())
    hint_text = normalise_slug((title_hint or "").lower())

    act = None
    if re.search(r"\boia\b", own_text):
        act = "OIA"
    elif re.search(r"\blgoima\b", own_text):
        act = "LGOIMA"
    elif re.search(r"\boia\b", hint_text) and not re.search(r"\blgoima\b", hint_text):
        act = "OIA"
    elif re.search(r"\blgoima\b", hint_text) and not re.search(r"\boia\b", hint_text):
        act = "LGOIMA"

    kind = None
    if "completed" in own_text:
        kind = "completed"
    elif "received" in own_text:
        kind = "received"
    elif "completed" in hint_text and "received" not in hint_text:
        kind = "completed"
    elif "received" in hint_text and "completed" not in hint_text:
        kind = "received"

    period = parse_case_notes_like_period(file_info.get("title") or "") or parse_case_notes_like_period(file_info.get("source_url") or "")
    if not period and title_hint:
        period = parse_case_notes_like_period(title_hint)

    return act, kind, period


def parse_resource_detail(url: str, timeout: int) -> dict[str, Any]:
    html, final_url = fetch_text(url, timeout=timeout)

    title_m = re.search(r'<span\s+lang="[^"]+"\s+class="page-header">(.*?)</span>', html, flags=re.I | re.S)
    if not title_m:
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I | re.S)
    title = safe_strip(title_m.group(1)) if title_m else ""

    date = None
    date_m = re.search(
        r'class="[^"]*field--name-field-(?:last-updated|issue-date)[^"]*"[\s\S]*?<time[^>]*datetime="([^"]+)"',
        html,
        flags=re.I | re.S,
    )
    if date_m:
        date = date_m.group(1)

    categories = []
    for cat_m in re.finditer(
        r'<div[^>]*class="[^"]*field--name-field-resource-type[^"]*"[\s\S]*?<a[^>]+href="/taxonomy/term/\d+"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        categories.append(safe_strip(cat_m.group(1)))

    body = ""
    body_m = re.search(
        r'<div[^>]*class="[^"]*field--name-body[^"]*"[\s\S]*?>([\s\S]*?)</div>\s*</div>',
        html,
        flags=re.I | re.S,
    )
    if body_m:
        body = safe_strip(body_m.group(1))
    else:
        body = safe_strip(html)[:900]

    attachments = parse_attachments(html, final_url)

    return {
        "title": title,
        "source_url": final_url,
        "published_at": date,
        "category": categories,
        "snippet": (body[:700] + ("…" if len(body) > 700 else "")) if body else "",
        "attachments": attachments,
    }


def parse_attachments(html: str, base_url: str) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    seen: set[str] = set()

    section_m = re.search(r'class="[^"]*field--name-field-related-files[^"]*"[\s\S]*?</section>', html, flags=re.I | re.S)
    pool = section_m.group(0) if section_m else html

    for li_m in re.finditer(r'<li[^>]*class="[^"]*field--item[^\"]*"[^>]*>([\s\S]*?)</li>', pool, flags=re.I):
        li = li_m.group(1)
        href_m = re.search(r'href="([^"]+)"', li)
        if not href_m:
            continue
        href = to_absolute(href_m.group(1))
        if '/sites/default/files/' not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        text = safe_strip(re.sub(r"<div[^>]+class=\"field--item\"[^>]*>\s*", "", li))
        mime_m = re.search(r'field-name-field-mimetype[^>]*>(.*?)</div>', li, flags=re.I | re.S)
        size_m = re.search(r'field-name-field-filesize[^>]*>(.*?)</div>', li, flags=re.I | re.S)
        ext = ""
        if "." in href:
            ext = href.rsplit(".", 1)[-1].split("?")[0].lower()
        if not ext:
            ext = ""
        attachments.append(
            {
                "title": text.split("  ")[0] if text else urllib.parse.urlsplit(href).path.split("/")[-1],
                "source_url": href,
                "format": ext.upper(),
                "mime": safe_strip(mime_m.group(1)) if mime_m else "",
                "size": safe_strip(size_m.group(1)) if size_m else "",
            }
        )

    if not attachments:
        for match in re.finditer(r'href="([^"]+)"', html, flags=re.I):
            href = to_absolute(match.group(1))
            if '/sites/default/files/' not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            text = safe_strip(match.group(0))
            ext = href.rsplit(".", 1)[-1].split("?")[0].lower() if "." in href else ""
            attachments.append(
                {
                    "title": text or urllib.parse.urlsplit(href).path.split("/")[-1],
                    "source_url": href,
                    "format": ext.upper(),
                    "mime": "",
                    "size": "",
                }
            )
    return attachments


def parse_csv_file(content: bytes, max_rows: int) -> tuple[list[dict[str, Any]], int]:
    text = content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], 0

    header = [safe_strip(v) for v in rows[0]]
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        norm = {
            (header[i] if i < len(header) and header[i] else f"column_{i + 1}"): (safe_strip(v) if i < len(row) else "")
            for i, v in enumerate(row)
        }
        out.append(norm)
        if len(out) >= max_rows:
            break
    return out, len(rows) - 1


def _column_number(addr: str) -> int:
    out = 0
    for ch in addr:
        if not ch.isalpha():
            continue
        out = out * 26 + (ord(ch.upper()) - 64)
    return max(0, out - 1)


def parse_xlsx_file(content: bytes, sheet_filter: str | None, max_rows: int) -> tuple[list[dict[str, Any]], int]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root_ss.findall(".//a:si", ns):
                text = "".join(x.text or "" for x in si.findall(".//a:t", ns))
                shared_strings.append(safe_strip(text))

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rel = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {node.attrib["Id"]: node.attrib["Target"] for node in rel}

        sheets = []
        for idx, sheet in enumerate(workbook.findall(".//a:sheet", ns), start=1):
            sheet_name = sheet.attrib.get("name", f"sheet-{idx}")
            if sheet_filter:
                target = sheet_filter.lower()
                if target.isdigit():
                    if idx != int(target):
                        continue
                elif target not in sheet_name.lower():
                    continue

            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rel_target = rel_map.get(rel_id, "")
            rel_name = ("xl/" + rel_target.lstrip("/")) if rel_target else ""
            if not rel_name or rel_name not in zf.namelist():
                continue

            ws_root = ET.fromstring(zf.read(rel_name))
            rows_raw: list[list[str]] = []
            for row in ws_root.findall(".//a:row", ns):
                cells: dict[int, str] = {}
                for c in row.findall("a:c", ns):
                    addr = c.attrib.get("r", "")
                    idx_col = _column_number("".join(ch for ch in addr if ch.isalpha()))
                    value = ""
                    t = c.attrib.get("t")
                    v = c.find("a:v", ns)
                    if t == "s" and v is not None and v.text is not None:
                        si = int(v.text)
                        if 0 <= si < len(shared_strings):
                            value = shared_strings[si]
                    elif t == "inlineStr":
                        txt = c.findall(".//a:t", ns)
                        value = "".join(x.text or "" for x in txt)
                    elif v is not None and v.text is not None:
                        value = v.text
                    cells[idx_col] = safe_strip(value)

                if not cells:
                    continue
                row_index_max = max(cells)
                row_values = ["" for _ in range(row_index_max + 1)]
                for c_idx, cell_value in cells.items():
                    if c_idx < len(row_values):
                        row_values[c_idx] = cell_value
                if any(row_values):
                    rows_raw.append(row_values)

            if not rows_raw:
                continue

            header: list[str] | None = None
            sheet_rows: list[dict[str, Any]] = []
            for row in rows_raw:
                if header is None:
                    if sum(1 for c in row if c) >= 2:
                        header = [safe_strip(col) or f"column_{i + 1}" for i, col in enumerate(row)]
                    continue
                if not any(row):
                    continue
                norm = {
                    header[i]: row[i]
                    for i in range(min(len(header), len(row)))
                    if row[i] and header[i]
                }
                sheet_rows.append(norm)
                if len(sheet_rows) >= max_rows:
                    break

            sheets.append(
                {
                    "name": sheet_name,
                    "header": header or [],
                    "rows": sheet_rows,
                    "row_count": len(sheet_rows),
                }
            )

            if sheet_filter and sheets:
                break

        return sheets, len(sheets)


def parse_structured_rows(url: str, kind: str | None, max_rows: int) -> tuple[list[dict[str, Any]], int]:
    normalized_url = urllib.parse.urlsplit(url)
    path = normalized_url.path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    data, _u, _ = fetch_bytes(url, timeout=DEFAULT_TIMEOUT)
    if ext == "csv":
        rows, total = parse_csv_file(data, max_rows)
        return [{"name": "csv", "header": list(rows[0].keys()) if rows else [], "rows": rows, "row_count": total}], 1
    if ext in {"xlsx", "xls"}:
        tables, total = parse_xlsx_file(data, sheet_filter=kind, max_rows=max_rows)
        return tables, total
    raise CliError(f"Unsupported table format: .{ext}", source_url=url, code="unsupported_format")


def discover_complaint_resources(
    *,
    query: str | None,
    period: str | None,
    act: str | None,
    kind_filter: str | None,
    timeout: int,
    max_pages: int,
    limit: int,
) -> list[dict[str, Any]]:
    categories = discover_categories(timeout)
    category_id = resolve_category("complaints data", categories)
    cards = discover_publications(
        query=query,
        category_id=category_id,
        max_pages=max_pages,
        timeout=timeout,
        limit=limit,
        require_match=True,
    )

    outputs: list[dict[str, Any]] = []
    for card in cards:
        if period or act or kind_filter:
            pass
        try:
            detail = parse_resource_detail(card["source_url"], timeout=timeout)
        except CliError:
            detail = {"title": card["title"], "source_url": card["source_url"], "attachments": []}

        attachment_candidates = []
        for a in detail.get("attachments", []):
            fmt = (a.get("format") or "").lower()
            if fmt not in {"xlsx", "xls", "csv"}:
                continue

            a_act, a_kind, a_period = classify_dataset_file(a, card["title"])
            a["act"] = a_act
            a["kind"] = a_kind
            a["period"] = a_period

            if act and a_act and a_act != act:
                continue
            if kind_filter and a_kind and kind_filter != "all" and a_kind != kind_filter:
                continue
            if period and a_period and a_period != period:
                continue
            attachment_candidates.append(a)

        if not attachment_candidates:
            continue

        outputs.append(
            {
                "resource_title": card["title"],
                "resource_url": card["source_url"],
                "resource_category": card.get("category", []),
                "resource_published_at": card.get("published_at"),
                "resource_snippet": card.get("snippet", ""),
                "dataset_files": attachment_candidates,
            }
        )

    return outputs


def filter_rows_by_agency(rows: list[dict[str, Any]], agency: str | None) -> list[dict[str, Any]]:
    if not agency:
        return rows
    needle = agency.lower()
    return [row for row in rows if any(needle in safe_strip(value).lower() for value in row.values())]


def parse_complaint_payload(
    args: argparse.Namespace,
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    if not (args.period or args.act or args.agency or args.kind != "all" or args.sheet):
        return {
            "resources": matches,
            "summary": {
                "count": len(matches),
                "note": "No complaints filters provided; listing available spreadsheet resources only.",
            },
        }

    data: list[dict[str, Any]] = []
    for item in matches:
        for file in item["dataset_files"]:
            if args.kind != "all" and file.get("kind") and file.get("kind") != args.kind:
                continue
            if args.act and file.get("act") and file.get("act") != args.act:
                continue
            if args.period and file.get("period") and file.get("period") != args.period:
                continue

            tables, _ = parse_structured_rows(file["source_url"], args.sheet, max_rows=args.limit)
            parsed_tables: list[dict[str, Any]] = []
            for table in tables:
                rows = table.get("rows", [])
                if args.agency:
                    rows = filter_rows_by_agency(rows, args.agency)
                parsed_tables.append(
                    {
                        "sheet": table.get("name"),
                        "rows": rows,
                        "columns": table.get("header", []),
                        "row_count": table.get("row_count", 0),
                        "filtered_count": len(rows),
                    }
                )

            data.append(
                {
                    "resource_title": item["resource_title"],
                    "resource_url": item["resource_url"],
                    "period": file.get("period"),
                    "act": file.get("act"),
                    "kind": file.get("kind"),
                    "source_url": file["source_url"],
                    "format": file.get("format"),
                    "tables": parsed_tables,
                }
            )

    return {
        "matches": data,
        "summary": {
            "requested_period": args.period,
            "requested_act": args.act,
            "requested_kind": args.kind,
            "requested_agency": args.agency,
            "requested_sheet": args.sheet,
            "count": len(data),
        },
    }


def command_result(command: str, args: argparse.Namespace, payload: dict[str, Any], source_url: str, warnings: list[str] | None = None, status: str = "ok") -> dict[str, Any]:
    return {
        "command": command,
        "status": status,
        "meta": {
            "source": "ombudsman-nz",
            "generated_at": now_iso(),
            "source_url": source_url,
            "timeout": args.timeout,
        },
        "query": {
            "command_args": {k: v for k, v in vars(args).items() if v is not None and k != "func"},
        },
        "warnings": warnings or [],
        **payload,
    }


def print_case_notes(results: list[dict[str, Any]]) -> None:
    print(f"Found {len(results)} publication(s)")
    for item in results[:20]:
        categories = ", ".join(item.get("category") or [])
        print(f"- {item['title']} ({categories or 'uncategorised'})")
        if item.get("published_at"):
            print(f"  Published: {item['published_at']}")
        print(f"  URL: {item['source_url']}")
        if item.get("snippet"):
            print(f"  {item['snippet'][:180]}")


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")


def cmd_case_notes_search(args: argparse.Namespace) -> dict[str, Any]:
    categories = discover_categories(args.timeout)
    category_id = resolve_category(args.category, categories)
    results = discover_publications(
        query=args.query,
        category_id=category_id,
        max_pages=args.max_pages,
        timeout=args.timeout,
        limit=max(args.limit, 100),
        require_match=False,
    )
    # Extra client-side matching on query, because category query is not always strict.
    if args.query:
        q = normalise_slug(args.query)
        if q:
            results = [r for r in results if q in normalise_slug(r["title"] + " " + r["snippet"] + " " + " ".join(r["category"]))]

    return command_result(
        "case-notes search",
        args,
        {
            "results": results[: args.limit],
            "count": len(results[: args.limit]),
            "requested_category": args.category,
        },
        RESOURCES_URL,
    )


def cmd_case_notes_show(args: argparse.Namespace) -> dict[str, Any]:
    url = to_absolute(args.identifier)
    detail = parse_resource_detail(url, timeout=args.timeout)
    return command_result(
        "case-notes show",
        args,
        {
            "resource": detail,
        },
        url,
    )


def cmd_reports(args: argparse.Namespace) -> dict[str, Any]:
    categories = discover_categories(args.timeout)
    category_id = resolve_category(args.category, categories)
    if not category_id:
        category_id = categories.get("opcat")

    results = discover_publications(
        query=args.query,
        category_id=category_id,
        max_pages=args.max_pages,
        timeout=args.timeout,
        limit=max(args.limit, 100),
        require_match=False,
    )

    if args.query:
        q = normalise_slug(args.query)
        results = [r for r in results if q in normalise_slug(r["title"] + " " + r["snippet"])]

    return command_result(
        "reports",
        args,
        {
            "results": results[: args.limit],
            "count": len(results[: args.limit]),
            "requested_category": args.category,
        },
        RESOURCES_URL,
    )


def cmd_reports_show(args: argparse.Namespace) -> dict[str, Any]:
    url = to_absolute(args.identifier)
    detail = parse_resource_detail(url, timeout=args.timeout)
    return command_result(
        "reports show",
        args,
        {
            "resource": detail,
        },
        url,
    )


def cmd_resource(args: argparse.Namespace) -> dict[str, Any]:
    url = to_absolute(args.identifier)
    detail = parse_resource_detail(url, timeout=args.timeout)
    return command_result(
        "resource",
        args,
        {"resource": detail},
        url,
    )


def cmd_complaints(args: argparse.Namespace) -> dict[str, Any]:
    query = "OIA and LGOIMA complaints received"
    matches = discover_complaint_resources(
        query=query,
        period=args.period,
        act=args.act,
        kind_filter=args.kind,
        timeout=args.timeout,
        max_pages=args.max_pages,
        limit=args.limit * 4,
    )
    payload = parse_complaint_payload(args, matches)
    if not payload.get("matches") and not payload.get("resources"):
        return command_result(
            "complaints",
            args,
            {"resources": [], "matches": [], "summary": {"count": 0, "note": "No matching machine-readable complaint tables found."}},
            RESOURCES_URL,
        )
    return command_result("complaints", args, payload, RESOURCES_URL)


def print_human(result: dict[str, Any], args: argparse.Namespace) -> None:
    cmd = result.get("command")
    if result.get("status") != "ok":
        print(f"{cmd}: {result.get('error', 'error')}")
        return

    if cmd in {"case-notes search", "case-notes show", "reports", "resource", "reports show", "complaints"}:
        if cmd in {"case-notes search", "reports"}:
            results = result.get("results", [])
            print(f"{cmd}: {result.get('count', len(results))} items")
            for row in results:
                date = row.get("published_at") or ""
                cats = ", ".join(row.get("category") or [])
                print(f"- {row.get('title')} ({cats or 'uncategorised'})")
                if date:
                    print(f"  Published: {date}")
                print(f"  {row.get('source_url')}")
                if row.get("snippet"):
                    print(f"  {row.get('snippet')[:150]}")
            return

        if cmd == "complaints":
            resources = result.get("resources") or []
            if resources:
                print(f"complaints (resource discovery): {len(resources)} available resource(s)")
                for row in resources:
                    print(f"- {row.get('resource_title')} ({row.get('resource_url')})")
                return

            matches = result.get("matches") or []
            print(f"complaints (datasets): {len(matches)} matching dataset(s)")
            for row in matches:
                print(f"- {row.get('resource_title')} | {row.get('act')} | {row.get('kind')} | {row.get('period')} | {row.get('source_url')}")
                for table in row.get("tables", []):
                    print(f"  - {table.get('sheet')} rows={table.get('filtered_count', 0)}")
            return

        resource = result.get("resource")
        if resource:
            print(resource.get("title"))
            print(resource.get("source_url"))
            if resource.get("published_at"):
                print(f"Published: {resource.get('published_at')}")
            cats = resource.get("category") or []
            if cats:
                print(f"Categories: {', '.join(cats)}")
            if resource.get("snippet"):
                print(resource.get("snippet")[:300])
            return

    print(json.dumps(result, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not hasattr(args, "func"):
        raise CliError("No command chosen")
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Ombudsman NZ public publications, reports, and complaints data.",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Network timeout in seconds.")

    sub = parser.add_subparsers(dest="command", required=True)

    complaints = sub.add_parser("complaints", help="Query complaints spreadsheets (OIA/LGOIMA) and filter by period, act, agency")
    complaints.add_argument("--act", choices=["OIA", "LGOIMA"], help="Filter by act")
    complaints.add_argument("--period", help="Filter by period, e.g. 2024-H1 or 2024-H2")
    complaints.add_argument("--agency", help="Filter rows by agency text (name search)")
    complaints.add_argument("--kind", choices=["all", "received", "completed"], default="all", help="Filter complaint file kind")
    complaints.add_argument("--sheet", help="Limit complaint workbook parse to one sheet (name fragment or index)")
    complaints.add_argument("--limit", type=int, default=20, help="Rows per sheet for parsed spreadsheets")
    complaints.add_argument("--max-pages", type=int, default=MAX_DISCOVERY_PAGES, help="Maximum /resources pages to scan")
    add_json_flag(complaints)
    complaints.set_defaults(func=cmd_complaints)

    case_notes = sub.add_parser("case-notes", help="Search Ombudsman case notes and related publication pages")
    case_notes_sub = case_notes.add_subparsers(dest="case_action", required=True)
    case_search = case_notes_sub.add_parser("search", help="Search case notes")
    case_search.add_argument("--query", help="Search by title/snippet text")
    case_search.add_argument("--category", default="case notes", help="Filter by category name or taxonomy id")
    case_search.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max results")
    case_search.add_argument("--max-pages", type=int, default=MAX_DISCOVERY_PAGES, help="Maximum /resources pages to scan")
    add_json_flag(case_search)
    case_search.set_defaults(func=cmd_case_notes_search)

    case_show = case_notes_sub.add_parser("show", help="Fetch and parse a case note publication")
    case_show.add_argument("identifier", help="Publication slug or absolute URL")
    add_json_flag(case_show)
    case_show.set_defaults(func=cmd_case_notes_show)

    reports = sub.add_parser("reports", help="Search or list inspection/OPCAT/publication pages")
    reports.add_argument("--query", help="Search query for titles")
    reports.add_argument("--category", default="OPCAT", help="Category name or taxonomy id")
    reports.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max results")
    reports.add_argument("--max-pages", type=int, default=MAX_DISCOVERY_PAGES, help="Maximum /resources pages to scan")
    add_json_flag(reports)
    reports.set_defaults(func=cmd_reports)

    reports_show = sub.add_parser("show", help="Show report/publication metadata")
    reports_show.add_argument("identifier", help="Publication slug or absolute URL")
    add_json_flag(reports_show)
    reports_show.set_defaults(func=cmd_reports_show)

    resource = sub.add_parser("resource", help="Fetch a resource URL/slug with metadata and attachments")
    resource.add_argument("identifier", help="Publication slug or absolute URL")
    add_json_flag(resource)
    resource.set_defaults(func=cmd_resource)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print_human(result, args)
        return 0
    except UpstreamUnavailable as exc:
        payload = {
            "command": getattr(args, "command", "unknown"),
            "status": "upstream_unavailable",
            "error": str(exc),
            "error_code": exc.code,
            "meta": {
                "source": "ombudsman-nz",
                "source_url": exc.source_url or RESOURCES_URL,
                "generated_at": now_iso(),
                "timeout": getattr(args, "timeout", DEFAULT_TIMEOUT),
            },
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ombudsman-nz: {payload['error']}", file=sys.stderr)
        return 1
    except CliError as exc:
        payload = {
            "command": getattr(args, "command", "unknown"),
            "status": "error",
            "error": str(exc),
            "error_code": exc.code,
            "meta": {
                "source": "ombudsman-nz",
                "source_url": exc.source_url or RESOURCES_URL,
                "generated_at": now_iso(),
                "timeout": getattr(args, "timeout", DEFAULT_TIMEOUT),
            },
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ombudsman-nz: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        if getattr(args, "json", False):
            print(json.dumps({"command": getattr(args, "command", "unknown"), "status": "error", "error": str(exc), "error_code": "unknown"}, indent=2, ensure_ascii=False))
        else:
            print(f"ombudsman-nz: unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
