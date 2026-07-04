#!/usr/bin/env python3
"""Stats NZ DataInfo+ / Aria metadata lookup CLI."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


BASE_URL = "https://datainfoplus.stats.govt.nz"
UA = "statsnz-classifications-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 20
SOURCE_NAME = "Stats NZ DataInfo+ / Aria"

SEARCH_SCOPES = {
    "all": None,
    "codelists": "search/codelists",
    "concepts": "search/concepts",
    "qualitystandards": "search/qualitystandards",
    "concept-sets": "search/concept-sets",
}


class UpstreamError(Exception):
    def __init__(self, status: str, message: str, url: str | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.url = url
        self.reason = reason


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def die(message: str, code: int = 1) -> None:
    print(f"statsnz-classifications-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", html.unescape(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def pick_localized(value: Any) -> str | None:
    if isinstance(value, str):
        return coerce_text(value)
    if isinstance(value, dict):
        for key in ("en-NZ", "en", "en-US", "en-GB"):
            if key in value:
                text = coerce_text(value.get(key))
                if text:
                    return text
        for text in value.values():
            chosen = coerce_text(text)
            if chosen:
                return chosen
    return None


def meta(source_urls: list[str] | str, status: str = "ok") -> dict[str, Any]:
    source_urls_list = [source_urls] if isinstance(source_urls, str) else source_urls
    return {
        "source": SOURCE_NAME,
        "source_url": source_urls_list[0] if source_urls_list else BASE_URL,
        "source_urls": source_urls_list,
        "status": status,
        "fetched_at": now_utc(),
    }


def is_upstream_blocked(code: int | None, body: str | None = None) -> bool:
    if code in {401, 403, 429, 451}:
        return True
    if not body:
        return False
    text = body.lower()
    return "blocked" in text or "forbidden" in text or "bot" in text or "captcha" in text


def decode_response(response: urllib.response.addinfourl) -> str:
    charset = response.headers.get_content_charset() or "utf-8"
    return response.read().decode(charset, errors="replace")


def request_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return decode_response(response), response.geturl()
    except urllib.error.HTTPError as exc:
        reason = decode_response(exc).strip() if hasattr(exc, "read") else ""
        status = "upstream_blocked" if is_upstream_blocked(exc.code, reason) else "upstream_unavailable"
        raise UpstreamError(status, f"HTTP {exc.code} from {url}", url=url, reason=reason[:240]) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpstreamError("upstream_unavailable", f"Network error calling {url}: {exc}", url=url) from None


def request_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[dict[str, Any], str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = decode_response(response)
            try:
                return json.loads(raw), response.geturl()
            except json.JSONDecodeError as exc:
                raise UpstreamError("upstream_unavailable", f"Invalid JSON from {url}: {exc}", url=url) from None
    except urllib.error.HTTPError as exc:
        reason = decode_response(exc).strip() if hasattr(exc, "read") else ""
        status = "upstream_blocked" if is_upstream_blocked(exc.code, reason) else "upstream_unavailable"
        raise UpstreamError(status, f"HTTP {exc.code} from {url}", url=url, reason=reason[:240]) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpstreamError("upstream_unavailable", f"Network error calling {url}: {exc}", url=url) from None


def item_url(agency: str, identifier: str) -> str:
    return f"{BASE_URL}/item/{agency}/{identifier}"


def item_json_url(agency: str, identifier: str) -> str:
    return f"{item_url(agency, identifier)}/json"


def item_history_url(agency: str, identifier: str) -> str:
    return f"{item_url(agency, identifier)}/_history"


def parse_item_reference(raw: str, default_agency: str | None = None) -> tuple[str, str]:
    text = raw.strip()
    if not text:
        raise ValueError("Expected an item identifier")

    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        text = parsed.path

    if text.startswith("/item/"):
        text = text[6:]
    if text.startswith("item/"):
        text = text[5:]

    text = text.split("?", 1)[0].split("#", 1)[0]
    if "/" in text:
        agency, identifier = text.split("/", 1)
        if agency and identifier:
            return agency, identifier

    if not default_agency:
        raise ValueError("Agency is required when identifier is not an /item/{agency}/{id} path.")
    return default_agency, text


def parse_search_cards(html: str) -> list[str]:
    cards = []
    marker = '<div class="card mb-3 search-result-'
    pos = 0
    while True:
        start = html.find(marker, pos)
        if start == -1:
            break
        next_start = html.find(marker, start + len(marker))
        end = next_start if next_start != -1 else len(html)
        cards.append(html[start:end])
        pos = end
    return cards


def parse_breadcrumbs(card: str) -> list[dict[str, Any]]:
    breadcrumbs = []
    for match in re.finditer(
        r'<li[^>]*class="[^"]*search-result-breadcrumb[^"]*"[^>]*>(.*?)</li>',
        card,
        re.S,
    ):
        raw = match.group(1)
        kind = clean_text(re.search(r"<span>(.*?)</span>", raw).group(1)) if re.search(r"<span>(.*?)</span>", raw) else None
        href_match = re.search(r'href="([^"]+)"', raw)
        href = href_match.group(1).strip() if href_match else None
        text = clean_text(re.sub(r"<[^>]+>", "", raw))
        if href:
            href = f"{BASE_URL}{href}" if href.startswith("/") else href
        breadcrumbs.append(
            {
                "kind": kind.rstrip(":") if kind else None,
                "label": text,
                "url": href,
            }
        )
    return breadcrumbs


def extract_item_reference(card: str) -> tuple[str, str] | None:
    match = re.search(r'href="(/item/[^"\s]+)"', card)
    if not match:
        return None
    href = match.group(1).split("?", 1)[0].split("#", 1)[0]
    if not re.fullmatch(r"/item/[^/]+/[^/]+", href):
        return None
    _, _, agency, identifier = href.split("/", 3)
    return agency, identifier


def parse_search_card(card: str) -> dict[str, Any] | None:
    link_parts = extract_item_reference(card)
    if not link_parts:
        return None

    agency, identifier = link_parts
    card_type = re.search(r'card mb-3 (search-result-[^"\s>]+)', card)
    card_type_text = card_type.group(1).replace("-", " ").strip() if card_type else "Unknown"

    title = None
    title_match = re.search(r'search-link-text-wrapper[^>]*>.*?<a[^>]*>(.*?)</a>', card, re.S)
    if title_match:
        title = clean_text(title_match.group(1))

    label = None
    label_match = re.search(r'<dt class="search-result-label-label">Label</dt>\s*<dd class="search-result-label-value">(.*?)</dd>', card, re.S)
    if label_match:
        label = clean_text(label_match.group(1))
    if not label:
        label = title

    item_name = None
    name_match = re.search(r'<dt class="search-result-name-label">Name</dt>\s*<dd class="search-result-name-value">(.*?)</dd>', card, re.S)
    if name_match:
        item_name = clean_text(name_match.group(1))

    image_type = None
    image_match = re.search(r'<img[^>]*title="([^"]+)"', card)
    if image_match:
        image_type = clean_text(image_match.group(1))
    item_type = image_type or card_type_text

    breadcrumbs = parse_breadcrumbs(card)
    description = clean_text(re.search(r'<p class="search-result-description-value">(.*?)</p>', card, re.S).group(1)) if re.search(r'<p class="search-result-description-value">(.*?)</p>', card, re.S) else None

    return {
        "agency": agency,
        "identifier": identifier,
        "url": item_url(agency, identifier),
        "title": title,
        "name": item_name,
        "label": label,
        "item_type": item_type,
        "description": description,
        "breadcrumbs": breadcrumbs,
    }


def search_scope(scope: str, query: str, limit: int, timeout: int) -> tuple[list[dict[str, Any]], str]:
    path = SEARCH_SCOPES[scope]
    params = {"Query": query or "", "IncludeDeprecated": "false"}
    url = f"{BASE_URL}/{path}?{urllib.parse.urlencode(params)}"
    html_text, final_url = request_text(url, timeout=timeout)

    cards = parse_search_cards(html_text)
    parsed = [item for item in (parse_search_card(card) for card in cards) if item is not None]

    if not parsed and "No results were found" in html_text:
        return [], final_url

    seen = set()
    unique = []
    for item in parsed:
        item_key = f"{item['agency']}/{item['identifier']}"
        if item_key in seen:
            continue
        item["scope"] = scope
        seen.add(item_key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique, final_url


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    query = (args.query or "").strip()
    limit = args.limit

    if args.scope == "all":
        all_results: list[dict[str, Any]] = []
        seen: set[str] = set()
        source_urls: list[str] = []
        scopes = ["codelists", "concepts", "qualitystandards", "concept-sets"]
        for scope in scopes:
            items, source_url = search_scope(scope, query, limit, args.timeout)
            source_urls.append(source_url)
            for item in items:
                key = f"{item['agency']}/{item['identifier']}"
                if key in seen:
                    continue
                item["search_scope"] = scope
                seen.add(key)
                all_results.append(item)
                if len(all_results) >= limit:
                    break
        status = "ok" if all_results else "not_found"
        return {
            "kind": "search",
            "status": status,
            "query": query,
            "scope": args.scope,
            "count": len(all_results),
            "results": all_results,
            "meta": meta(source_urls or BASE_URL, status=status),
        }

    items, source_url = search_scope(args.scope, query, limit, args.timeout)
    for item in items:
        item["search_scope"] = args.scope
    status = "ok" if items else "not_found"
    return {
        "kind": "search",
        "status": status,
        "query": query,
        "scope": args.scope,
        "count": len(items),
        "results": items,
        "meta": meta(source_url, status=status),
    }


def parse_codes(payload: dict[str, Any], code_limit: int, code_depth: int) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    raw_codes = payload.get("Codes")
    if not isinstance(raw_codes, list):
        raw_codes = payload.get("CodeList")
    if not raw_codes:
        return [], []

    max_depth = max(1, code_depth)
    limit = code_limit if code_limit > 0 else 0
    category_pairs: list[tuple[str, str]] = []
    output: list[dict[str, Any]] = []

    def walk(codes: list[dict[str, Any]], depth: int, parent: str | None = None, path: str | None = None) -> None:
        if not codes:
            return
        for entry in codes:
            if limit and len(output) >= limit:
                return
            if not isinstance(entry, dict):
                continue

            identifier = coerce_text(entry.get("Identifier"))
            value = pick_localized(entry.get("Label")) or coerce_text(entry.get("Value")) or coerce_text(entry.get("Code"))
            if identifier and parent:
                code_path = f"{path or ''}/{identifier}"
            else:
                code_path = f"{path or ''}/{value}" if value else (path or "")

            category = None
            cat_ref = entry.get("Category")
            if isinstance(cat_ref, dict):
                cat_agency = coerce_text(cat_ref.get("AgencyId"))
                cat_identifier = coerce_text(cat_ref.get("Identifier"))
                if cat_agency and cat_identifier:
                    category = {"agency": cat_agency, "identifier": cat_identifier, "url": item_url(cat_agency, cat_identifier)}
                    pair = (cat_agency, cat_identifier)
                    if pair not in category_pairs:
                        category_pairs.append(pair)

            output.append(
                {
                    "identifier": identifier,
                    "value": value,
                    "depth": depth,
                    "parent_identifier": parent,
                    "code_path": code_path.strip("/"),
                    "category": category,
                }
            )

            child_codes = entry.get("ChildCodes")
            if depth < max_depth and isinstance(child_codes, list):
                walk(child_codes, depth + 1, identifier, code_path.strip("/") if code_path else None)
            if limit and len(output) >= limit:
                return

    walk(raw_codes, 1)
    return output, category_pairs


def parse_classification_item(payload: dict[str, Any], source_url: str) -> dict[str, Any]:
    return {
        "agency": coerce_text(payload.get("AgencyId")),
        "identifier": coerce_text(payload.get("Identifier")),
        "item_type": coerce_text(payload.get("ItemType")),
        "version": payload.get("Version"),
        "version_date": coerce_text(payload.get("VersionDate")),
        "name": pick_localized(payload.get("ItemName")) or pick_localized(payload.get("DisplayLabel")) or pick_localized(payload.get("Label")),
        "label": pick_localized(payload.get("Label")),
        "description": pick_localized(payload.get("Description")),
        "is_published": bool(payload.get("IsPublished")) if payload.get("IsPublished") is not None else None,
        "is_populated": bool(payload.get("IsPopulated")) if payload.get("IsPopulated") is not None else None,
        "version_responsibility": pick_localized(payload.get("VersionResponsibility")),
        "source_url": source_url,
    }


def parse_category_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "agency": coerce_text(payload.get("AgencyId")),
        "identifier": coerce_text(payload.get("Identifier")),
        "name": pick_localized(payload.get("ItemName")) or pick_localized(payload.get("DisplayLabel")) or pick_localized(payload.get("Label")),
        "label": pick_localized(payload.get("Label")),
        "description": pick_localized(payload.get("Description")),
        "is_populated": bool(payload.get("IsPopulated")) if payload.get("IsPopulated") is not None else None,
    }


def resolve_category_details(pairs: list[tuple[str, str]], timeout: int, limit: int) -> list[dict[str, Any]]:
    details = []
    for agency, identifier in pairs[:limit]:
        source_url = item_url(agency, identifier)
        try:
            payload, payload_url = request_json(item_json_url(agency, identifier), timeout=timeout)
            details.append(
                {
                    **parse_category_summary(payload),
                    "source_url": payload_url,
                    "status": "ok",
                }
            )
        except UpstreamError as exc:
            details.append(
                {
                    "agency": agency,
                    "identifier": identifier,
                    "name": None,
                    "label": None,
                    "description": None,
                    "is_populated": None,
                    "source_url": source_url,
                    "status": exc.status,
                    "error": exc.message,
                }
            )
    return details


def command_classification_get(args: argparse.Namespace) -> dict[str, Any]:
    if args.code_limit < 0:
        die("--code-limit must be >= 0")
    if args.code_depth < 1:
        die("--code-depth must be >= 1")
    if args.category_limit < 0:
        die("--category-limit must be >= 0")

    agency, identifier = parse_item_reference(args.identifier, args.agency)
    source_url = item_url(agency, identifier)

    payload, payload_url = request_json(item_json_url(agency, identifier), timeout=args.timeout)
    metadata = parse_classification_item(payload, source_url)
    raw_codes = payload.get("Codes") or payload.get("CodeList") or []
    codes, category_pairs = parse_codes(payload, code_limit=args.code_limit, code_depth=args.code_depth)

    category_limit = args.category_limit
    categories = resolve_category_details(category_pairs, timeout=args.timeout, limit=category_limit) if category_pairs and category_limit > 0 else []

    return {
        "kind": "classification",
        "status": "ok",
        "metadata": metadata,
        "code_total": len(raw_codes),
        "codes_returned": len(codes),
        "code_depth": args.code_depth,
        "code_limit": args.code_limit,
        "codes": codes,
        "category_total": len(category_pairs),
        "category_returned": len(categories),
        "categories": categories,
        "meta": meta(payload_url, status="ok"),
    }


def parse_history_rows(html: str) -> list[dict[str, Any]]:
    table_match = re.search(r"<table[^>]*class=\"table\"[^>]*>(.*?)</table>", html, re.S)
    if not table_match:
        return []

    rows = []
    for row_raw in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.S):
        row_html = row_raw.group(1)
        if "<th" in row_html:
            continue
        cells = [clean_text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)]
        if len(cells) < 5:
            continue
        if not any(cells):
            continue

        date_cell = cells[-3]
        date_match = re.search(r'data-date="([^"]+)"', row_html)
        if date_match:
            date_cell = date_match.group(1)
        rows.append(
            {
                "label": cells[-5],
                "version": cells[-4],
                "date": date_cell,
                "responsibility": cells[-2],
                "message": cells[-1],
            }
        )
    return rows


def command_classification_versions(args: argparse.Namespace) -> dict[str, Any]:
    agency, identifier = parse_item_reference(args.identifier, args.agency)
    if args.limit < 0:
        die("--limit must be >= 0")

    html_text, final_url = request_text(item_history_url(agency, identifier), timeout=args.timeout)
    rows = parse_history_rows(html_text)

    status = "ok" if rows else "not_found"
    if args.limit:
        rows = rows[:args.limit]

    return {
        "kind": "classification_versions",
        "status": status,
        "agency": agency,
        "identifier": identifier,
        "item_url": item_url(agency, identifier),
        "version_count": len(rows),
        "versions": rows,
        "meta": meta(final_url, status=status),
    }


def command_classification_categories(args: argparse.Namespace) -> dict[str, Any]:
    if args.code_limit < 0:
        die("--code-limit must be >= 0")
    if args.code_depth < 1:
        die("--code-depth must be >= 1")
    if args.limit < 0:
        die("--limit must be >= 0")

    agency, identifier = parse_item_reference(args.identifier, args.agency)
    payload, final_url = request_json(item_json_url(agency, identifier), timeout=args.timeout)
    _, category_pairs = parse_codes(payload, code_limit=args.code_limit, code_depth=args.code_depth)

    limit = args.limit
    categories = resolve_category_details(category_pairs, timeout=args.timeout, limit=limit) if category_pairs and limit > 0 else []
    status = "ok" if categories else ("not_found" if not category_pairs else "ok")

    return {
        "kind": "classification_categories",
        "status": status,
        "agency": agency,
        "identifier": identifier,
        "classification_url": item_url(agency, identifier),
        "category_total": len(category_pairs),
        "category_returned": len(categories),
        "categories": categories,
        "meta": meta(final_url, status=status),
    }


def command_standards(args: argparse.Namespace) -> dict[str, Any]:
    query = (args.query or "").strip()
    items, source_url = search_scope("qualitystandards", query, args.limit, args.timeout)

    if query and not items:
        fallback, fallback_source_url = search_scope("qualitystandards", "", args.limit, args.timeout)
        query_lower = query.lower()
        items = [
            item
            for item in fallback
            if query_lower in (item.get("title") or "").lower()
            or query_lower in (item.get("label") or "").lower()
            or query_lower in (item.get("name") or "").lower()
        ]
        source_urls = [source_url, fallback_source_url]
    else:
        source_urls = [source_url]

    if not items:
        status = "not_found"
    else:
        status = "ok"

    return {
        "kind": "standards",
        "status": status,
        "query": query,
        "count": len(items),
        "standards": items[: args.limit],
        "meta": meta(source_urls, status=status),
    }


def build_concordance_queries(from_term: str, to_term: str, extra: str) -> list[str]:
    terms = [from_term.strip(), to_term.strip(), from_term.strip() + " " + to_term.strip()]
    variants = [
        t.strip()
        for t in ",".join([from_term, to_term, extra]).split(",")
        if t.strip()
    ]
    terms.extend([f"{t} concordance" for t in variants])
    terms.extend([f"{t} correspondence" for t in variants])
    return list(dict.fromkeys(terms))


def enrich_concordance_item(item: dict[str, Any], timeout: int) -> dict[str, Any]:
    payload, source_url = request_json(item["url"] + "/json", timeout=timeout)
    code_count = len(payload.get("Codes") or payload.get("CodeList") or [])
    item["meta"] = {
        "source": SOURCE_NAME,
        "source_url": source_url,
        "status": "ok",
        "fetched_at": now_utc(),
    }
    item["item_type_id"] = coerce_text(payload.get("ItemType"))
    item["is_published"] = bool(payload.get("IsPublished")) if payload.get("IsPublished") is not None else None
    item["is_populated"] = bool(payload.get("IsPopulated")) if payload.get("IsPopulated") is not None else None
    item["version"] = payload.get("Version")
    item["version_date"] = coerce_text(payload.get("VersionDate"))
    item["code_count"] = code_count
    return item


def command_concordance(args: argparse.Namespace) -> dict[str, Any]:
    from_term = (args.from_code or "").strip()
    to_term = (args.to_code or "").strip()
    if not from_term or not to_term:
        die("both FROM and TO terms are required")

    queries = build_concordance_queries(from_term, to_term, args.query_queries)
    limit = max(1, args.limit)
    seen: set[str] = set()
    matches: list[dict[str, Any]] = []
    source_urls = []

    for query in queries:
        if len(matches) >= limit:
            break
        candidates, source_url = search_scope("concept-sets", query, limit, args.timeout)
        source_urls.append(source_url)
        for item in candidates:
            key = f"{item['agency']}/{item['identifier']}"
            if key in seen:
                continue
            text = " ".join(
                part
                for part in [
                    item.get("title") or "",
                    item.get("name") or "",
                    item.get("label") or "",
                    item.get("item_type") or "",
                    " ".join((b.get("label") or "") for b in item.get("breadcrumbs", [])),
                ]
            ).lower()
            if from_term.lower() not in text or to_term.lower() not in text:
                continue

            try:
                enrich_concordance_item(item, args.timeout)
            except UpstreamError as exc:
                item["status"] = exc.status
                item["error"] = exc.message
            item["search_query"] = query
            item["match_score"] = "high" if from_term.lower() in text and to_term.lower() in text else "medium"
            seen.add(key)
            matches.append(item)
            if len(matches) >= limit:
                break

    status = "ok" if matches else "unsupported"
    if matches:
        # deterministic order for testing and stable output
        matches = matches[:limit]

    return {
        "kind": "concordance",
        "status": status,
        "from": from_term,
        "to": to_term,
        "query_count": len(matches),
        "count": len(matches),
        "matches": matches,
        "meta": meta(source_urls or BASE_URL, status=status),
    }


def print_human(data: dict[str, Any]) -> None:
    kind = data.get("kind")
    if kind == "search":
        print(f"Search {data.get('scope')} for {data.get('query')!r}: {data.get('count')} result(s)")
        for item in data.get("results", []):
            print(f"- {item.get('title') or item.get('name') or item.get('label')}")
            print(f"  id: {item.get('agency')}/{item.get('identifier')}")
            print(f"  type: {item.get('item_type')}")
            if item.get("description"):
                print(f"  description: {item.get('description')}")
            print(f"  source: {item.get('url')}")
        return

    if kind == "classification":
        metadata = data.get("metadata", {})
        print(f"Classification {metadata.get('identifier')} ({metadata.get('agency')})")
        print(f"name: {metadata.get('name') or metadata.get('label')}")
        print(f"version: {metadata.get('version')} ({metadata.get('version_date')})")
        print(f"codes returned: {data.get('codes_returned')} of {data.get('code_total')}")
        print(f"categories returned: {data.get('category_returned')} of {data.get('category_total')}")
        return

    if kind == "classification_versions":
        print(f"Versions for {data.get('agency')}/{data.get('identifier')}: {data.get('version_count')} rows")
        for row in data.get("versions", []):
            print(f"- v{row.get('version')} | {row.get('date')} | {row.get('label')}")
        return

    if kind == "classification_categories":
        print(f"Categories for {data.get('agency')}/{data.get('identifier')}: {data.get('category_returned')} shown")
        for category in data.get("categories", []):
            status = category.get("status")
            if status and status != "ok":
                print(f"- {category.get('agency')}/{category.get('identifier')} | {status}")
            else:
                print(f"- {category.get('agency')}/{category.get('identifier')} | {category.get('label') or category.get('name')}")
        return

    if kind == "standards":
        print(f"Standards: {data.get('query') or '[all]'} -> {data.get('count')} record(s)")
        for standard in data.get("standards", []):
            print(f"- {standard.get('title') or standard.get('name') or standard.get('label')} ({standard.get('agency')}/{standard.get('identifier')})")
        return

    if kind == "concordance":
        print(f"Concordance search {data.get('from')} -> {data.get('to')}: {data.get('count')} match(es)")
        for match in data.get("matches", []):
            print(f"- {match.get('title') or match.get('name') or match.get('label')} ({match.get('agency')}/{match.get('identifier')})")
        return

    print(json.dumps(data, indent=2, ensure_ascii=False))


def emit_output(data: dict[str, Any], args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if data.get("status") in {"upstream_unavailable", "upstream_blocked"}:
            return 2
        return 0

    print_human(data)
    if data.get("status") in {"upstream_unavailable", "upstream_blocked"}:
        return 2
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Stats NZ DataInfo+ classifications and standards metadata")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="network timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="search DataInfo+ items")
    search.add_argument("query", help="search query")
    search.add_argument(
        "--scope",
        choices=list(SEARCH_SCOPES.keys()),
        default="all",
        help="scope to search",
    )
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    search.set_defaults(func=command_search)

    classification = sub.add_parser("classification", help="work with one item by id/path")
    cls_sub = classification.add_subparsers(dest="classification_command", required=True)

    cls_get = cls_sub.add_parser("get", help="get metadata, codes and category links for one item")
    cls_get.add_argument("identifier", help="item identifier or /item/{agency}/{id} URL")
    cls_get.add_argument("--agency", default="nz.govt.stats", help="agency identifier when identifier is a raw UUID")
    cls_get.add_argument("--code-limit", type=int, default=200, help="max codes to return (0 for unlimited)")
    cls_get.add_argument("--code-depth", type=int, default=2, help="maximum code hierarchy depth")
    cls_get.add_argument("--category-limit", type=int, default=30, help="max category metadata rows to resolve")
    cls_get.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    cls_get.set_defaults(func=command_classification_get)

    cls_versions = cls_sub.add_parser("versions", help="fetch item version history")
    cls_versions.add_argument("identifier", help="item identifier or /item/{agency}/{id} URL")
    cls_versions.add_argument("--agency", default="nz.govt.stats", help="agency identifier when identifier is a raw UUID")
    cls_versions.add_argument("--limit", type=int, default=25, help="max versions to return")
    cls_versions.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    cls_versions.set_defaults(func=command_classification_versions)

    cls_categories = cls_sub.add_parser("categories", help="resolve category metadata referenced by one item")
    cls_categories.add_argument("identifier", help="item identifier or /item/{agency}/{id} URL")
    cls_categories.add_argument("--agency", default="nz.govt.stats", help="agency identifier when identifier is a raw UUID")
    cls_categories.add_argument("--code-limit", type=int, default=200, help="max codes to inspect for category references (0 for unlimited)")
    cls_categories.add_argument("--code-depth", type=int, default=2, help="maximum hierarchy depth to inspect")
    cls_categories.add_argument("--limit", type=int, default=50, help="max categories to resolve")
    cls_categories.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    cls_categories.set_defaults(func=command_classification_categories)

    concordance = sub.add_parser("concordance", help="find concordance/crosswalk metadata")
    concordance.add_argument("from_code", help="from classification/term")
    concordance.add_argument("to_code", help="to classification/term")
    concordance.add_argument(
        "--query-queries",
        default="",
        help="comma-separated extra query variants (e.g. 'crosswalk, correspondence')",
    )
    concordance.add_argument("--limit", type=int, default=10, help="max matches to return")
    concordance.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    concordance.set_defaults(func=command_concordance)

    standards = sub.add_parser("standards", help="list/search quality standard metadata")
    standards.add_argument("query", nargs="?", help="optional filter text")
    standards.add_argument("--limit", type=int, default=20, help="max standards to return")
    standards.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    standards.set_defaults(func=command_standards)

    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        data = args.func(args)
    except UpstreamError as exc:
        data = {
            "kind": args.command,
            "status": exc.status,
            "error": exc.message,
            "meta": meta(exc.url or BASE_URL, status=exc.status),
        }
        if exc.reason:
            data["reason"] = exc.reason
        return emit_output(data, args)
    except ValueError as exc:
        die(str(exc), code=1)
    except SystemExit:
        raise

    return emit_output(data, args)


if __name__ == "__main__":
    raise SystemExit(main())
