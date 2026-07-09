#!/usr/bin/env python3
"""Read-only FYI.org.nz OIA/LGOIMA discovery CLI.

No credentials, no mutations, stdlib-only networking.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import re
import sys
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_URL = "https://fyi.org.nz"
AUTHORITIES_CSV = BASE_URL + "/body/all-authorities.csv"
BODY_JSON = BASE_URL + "/body/{slug}.json"
REQUEST_JSON = BASE_URL + "/request/{request_id}.json"
SEARCH_URLS = (
    BASE_URL + "/search/all",  # Alaveteli legacy search path
    BASE_URL + "/search",
)

REQUEST_TIMEOUT_SECONDS = 30
UA_HTTP_ACCEPT = "application/json, text/html, application/atom+xml, */*"
BLOCK_MARKERS = (
    "incap",
    "access denied",
    "blocked",
    "forbidden",
    "not authorized",
    "you must accept",
    "captcha",
    "are you a robot",
    "robot check",
    "bot detection",
    "bot management",
    "automated access",
)


class CliError(Exception):
    """Raised for command-facing failures."""

    def __init__(self, message: str, status: str = "error") -> None:
        super().__init__(message)
        self.status = status


def fail(message: str, code: int = 1) -> None:
    print(f"fyi-oia-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_meta(source_url: str, status: str = "ok", **extra: Any) -> dict[str, Any]:
    payload = {
        "source": "fyi.org.nz",
        "source_url": source_url,
        "fetched_at": utc_now_iso(),
        "status": status,
    }
    payload.update(extra)
    return payload


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_blocked(body: str, response_url: str) -> None:
    lowered = (body or "").lower()
    if any(marker in lowered for marker in BLOCK_MARKERS):
        raise CliError(f"upstream_blocked: suspicious block response from {response_url}", status="upstream_blocked")


def fetch_bytes(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bytes, str, str]:
    try:
        payload, content_type, response_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept=UA_HTTP_ACCEPT,
        )
    except nzfetch.Blocked as exc:
        raise CliError(f"upstream_blocked: network error from {url}: {exc}", status="upstream_blocked")
    except nzfetch.FetchError as exc:
        raise CliError(f"upstream_unavailable: network error for {url}: {exc}", status="upstream_unavailable")
    except (TimeoutError, OSError) as exc:
        raise CliError(f"upstream_unavailable: network failure for {url}: {exc}", status="upstream_unavailable")
    detect_blocked(payload.decode("utf-8", "replace"), response_url)
    return payload, response_url, content_type


def fetch_json(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[dict[str, Any] | list[Any], str, str]:
    raw, response_url, content_type = fetch_bytes(url, timeout=timeout)
    text = raw.decode("utf-8", "replace")
    if not text.strip():
        raise CliError(f"invalid upstream response from {url}: empty body", status="upstream_unavailable")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON from {url}: {exc}", status="upstream_unavailable")
    return data, response_url, content_type


def fetch_text(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[str, str, str]:
    raw, response_url, content_type = fetch_bytes(url, timeout=timeout)
    return raw.decode("utf-8", "replace"), response_url, content_type


def parse_authority_slug(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise CliError("empty body identifier")

    parsed = urllib.parse.urlparse(value)
    path = parsed.path
    if "/" in path:
        # Accept /body/<slug>, /body/<slug>.json, and full request/authority URLs
        parts = [p for p in path.strip("/").split("/") if p]
        for idx, part in enumerate(parts):
            if part == "body" and idx + 1 < len(parts):
                slug = parts[idx + 1]
                break
            if idx == len(parts) - 1:
                slug = part
        else:
            slug = parts[-1]
        slug = slug.replace(".json", "")
    else:
        slug = value

    slug = re.sub(r"[^A-Za-z0-9_-]", "_", slug).strip("_ ")
    if not slug:
        raise CliError(f"cannot derive body slug from {value!r}")
    return slug


def parse_request_id(value: str) -> tuple[str, str]:
    value = (value or "").strip()
    if not value:
        raise CliError("empty request identifier")

    parsed = urllib.parse.urlparse(value)
    path = parsed.path
    if "request" in path:
        # Accept /request/<id> or /request/<id>-<slug>
        m = re.search(r"/request/(\d+)(?:-[^/]*)?", path)
        if m:
            return m.group(1), m.group(0)

    if value.startswith("/request/"):
        value = value[len("/request/"):]

    if value.endswith(".json"):
        value = value[:-5]

    m = re.match(r"^(\d+)", value)
    if m:
        request_id = m.group(1)
        slug = f"/request/{value}"
        return request_id, slug

    raise CliError(f"request identifier must be numeric id or request URL: {value!r}")


def normalize_tag_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, (list, tuple)):
                if item:
                    values.append(str(item[0]))
            elif isinstance(item, str):
                values.append(item)
            elif item is not None:
                values.append(str(item))
        return sorted({v.strip() for v in values if str(v).strip()})
    if not isinstance(raw, str):
        return []
    parts = re.split(r"[,;]", raw)
    return sorted({p.strip() for p in parts if p.strip()})


def load_authorities() -> list[dict[str, Any]]:
    text, response_url, _ = fetch_text(AUTHORITIES_CSV)
    rows = list(csv.DictReader(io.StringIO(text)))
    out: list[dict[str, Any]] = []
    for row in rows:
        url_name = (row.get("URL name") or "").strip()
        if not url_name:
            continue
        tags = normalize_tag_list(row.get("Tags", ""))
        authority = {
            "name": row.get("Name") or "",
            "short_name": row.get("Short name") or "",
            "url_name": url_name,
            "tags": tags,
            "home_page": row.get("Home page") or "",
            "publication_scheme": row.get("Publication scheme") or "",
            "disclosure_log": row.get("Disclosure log") or "",
            "notes": row.get("Notes") or "",
            "created_at": row.get("Created at") or "",
            "updated_at": row.get("Updated at") or "",
            "version": row.get("Version") or "",
            "url": f"{BASE_URL}/body/{url_name}",
        }
        out.append(authority)
    if not out:
        raise CliError(f"empty or malformed authority CSV from {response_url}", status="upstream_unavailable")
    return out


def filter_authorities(authorities: list[dict[str, Any]], tags: list[str], query: str | None, limit: int) -> list[dict[str, Any]]:
    by_tag = [t.strip().lower() for t in tags if t.strip()]
    q = (query or "").strip().lower()

    def matches(row: dict[str, Any]) -> bool:
        row_tags = {t.lower() for t in row.get("tags", [])}
        if by_tag and not any(t in row_tags for t in by_tag):
            return False
        if q:
            hay = (
                f"{row.get('name','')} {row.get('short_name','')} {row.get('url_name','')} "
                f"{row.get('notes','')} {','.join(row.get('tags', []))}".lower()
            ).lower()
            if q not in hay:
                return False
        return True

    results = [row for row in authorities if matches(row)]
    return results[:limit]


def normalise_search_events(raw_events: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        events.append(
            {
                "id": event.get("id"),
                "event_type": event.get("event_type"),
                "created_at": event.get("created_at"),
                "described_state": event.get("described_state"),
                "calculated_state": event.get("calculated_state"),
                "display_status": event.get("display_status"),
                "last_described_at": event.get("last_described_at"),
                "incoming_message_id": event.get("incoming_message_id"),
                "outgoing_message_id": event.get("outgoing_message_id"),
                "comment_id": event.get("comment_id"),
            }
        )
    return events


def request_projection(raw: dict[str, Any], include_full: bool) -> dict[str, Any]:
    raw_body = raw.get("public_body")
    public_body: dict[str, Any] = {}
    if isinstance(raw_body, dict):
        public_body = {
            "id": raw_body.get("id"),
            "name": raw_body.get("name"),
            "url_name": raw_body.get("url_name"),
            "short_name": raw_body.get("short_name"),
            "url": f"{BASE_URL}/body/{raw_body.get('url_name')}" if raw_body.get("url_name") else None,
        }

    base: dict[str, Any] = {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "url_title": raw.get("url_title"),
        "described_state": raw.get("described_state"),
        "display_status": raw.get("display_status"),
        "awaiting_description": raw.get("awaiting_description"),
        "law_used": raw.get("law_used"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "tags": normalize_tag_list(raw.get("tags", [])),
        "url": f"{BASE_URL}/request/{raw.get('id')}",
        "public_body": public_body,
    }
    if include_full:
        events = raw.get("info_request_events")
        if isinstance(events, list):
            base["events"] = normalise_search_events(events)
            base["event_count"] = len(base["events"])
        else:
            base["events"] = []
            base["event_count"] = 0
    return base


def event_projection(raw: dict[str, Any]) -> dict[str, Any]:
    events = raw.get("info_request_events")
    if not isinstance(events, list):
        return {
            "kind": "events",
            "request_id": raw.get("id"),
            "title": raw.get("title"),
            "event_count": 0,
            "events": [],
        }
    normalized = normalise_search_events(events)
    return {
        "kind": "events",
        "request_id": raw.get("id"),
        "title": raw.get("title"),
        "event_count": len(normalized),
        "events": normalized,
    }


def parse_search_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    request_id = item.get("id")
    request_url = item.get("url") or item.get("request_url") or item.get("url_title") or ""
    if not request_id and request_url:
        m = re.search(r"/request/(\d+)", str(request_url))
        if m:
            request_id = m.group(1)

    if not request_id:
        return None

    pb = item.get("public_body")
    body = None
    if isinstance(pb, dict):
        body = {
            "id": pb.get("id"),
            "name": pb.get("name"),
            "url_name": pb.get("url_name"),
            "url": f"{BASE_URL}/body/{pb.get('url_name')}" if pb.get("url_name") else None,
        }

    return {
        "id": int(request_id) if str(request_id).isdigit() else request_id,
        "title": item.get("title") or item.get("summary") or "",
        "url": f"{BASE_URL}{request_url}" if request_url and request_url.startswith("/") else str(request_url),
        "described_state": item.get("described_state"),
        "display_status": item.get("display_status"),
        "calculated_state": item.get("calculated_state"),
        "created_at": item.get("created_at") or item.get("created"),
        "public_body": body,
    }


def parse_search_html(html: str) -> list[dict[str, Any]]:
    candidates = []
    found: set[str] = set()
    for href, label in re.findall(r"href=\"(/request/[^\"]+)\"[^>]*>(.*?)</a>", html, flags=re.I | re.S):
        if "/request/" not in href:
            continue
        request_id_match = re.search(r"/request/(\d+)", href)
        if not request_id_match:
            continue
        request_id = request_id_match.group(1)
        if request_id in found:
            continue
        found.add(request_id)
        title = strip_html(label)
        if not title:
            continue
        candidates.append(
            {
                "id": int(request_id),
                "title": title,
                "url": f"{BASE_URL}{href}",
            }
        )
    return candidates


def parse_search_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in ("results", "requests", "items", "rows", "records", "searches"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                candidates = maybe
                break
        else:
            # Some payloads may nest in a 'request' object from older endpoints
            maybe = payload.get("request")
            candidates = maybe if isinstance(maybe, list) else []
    else:
        return []

    out: list[dict[str, Any]] = []
    for item in candidates or []:
        parsed = parse_search_item(item)
        if parsed:
            out.append(parsed)
    return out


def emit(payload: dict[str, Any], as_json: bool, formatter) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        formatter(payload)


def cmd_authorities(args: argparse.Namespace) -> None:
    data = load_authorities()
    items = filter_authorities(data, args.tag, args.query, args.limit)
    payload = {
        "kind": "authorities",
        "count": len(items),
        "meta": make_meta(AUTHORITIES_CSV),
        "filters": {
            "tags": args.tag,
            "query": args.query,
        },
        "authorities": items,
    }
    emit(payload, args.json, render_authorities)


def cmd_categories(args: argparse.Namespace) -> None:
    data = load_authorities()
    counter = Counter()
    for row in data:
        for tag in row.get("tags", []):
            if tag:
                counter[tag] += 1
    rows = [{"category": tag, "count": count} for tag, count in counter.items() if tag]
    rows.sort(key=lambda x: (-x["count"], x["category"]))
    payload = {
        "kind": "categories",
        "count": len(rows),
        "meta": make_meta(AUTHORITIES_CSV),
        "categories": rows[: args.limit],
    }
    emit(payload, args.json, render_categories)


def cmd_body(args: argparse.Namespace) -> None:
    slug = parse_authority_slug(args.body)
    url = BODY_JSON.format(slug=urllib.parse.quote(slug))
    raw, response_url, _ = fetch_json(url)
    if not isinstance(raw, dict):
        raise CliError(f"unexpected authority JSON shape from {response_url}")

    payload = {
        "kind": "body",
        "meta": make_meta(response_url),
        "body": {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "short_name": raw.get("short_name") or "",
            "url_name": raw.get("url_name") or slug,
            "home_page": raw.get("home_page") or "",
            "publication_scheme": raw.get("publication_scheme") or "",
            "disclosure_log": raw.get("disclosure_log") or "",
            "notes": raw.get("notes") or "",
            "created_at": raw.get("created_at") or "",
            "updated_at": raw.get("updated_at") or "",
            "tags": normalize_tag_list(raw.get("tags", [])),
            "url": f"{BASE_URL}/body/{raw.get('url_name') or slug}",
        },
    }
    emit(payload, args.json, render_body)


def cmd_request(args: argparse.Namespace) -> None:
    request_id, _ = parse_request_id(args.request)
    raw, response_url, _ = fetch_json(REQUEST_JSON.format(request_id=request_id))
    if not isinstance(raw, dict):
        raise CliError(f"unexpected request JSON shape from {response_url}")

    payload = {
        "kind": "request",
        "meta": make_meta(response_url),
        "request": request_projection(raw, include_full=args.full),
    }
    emit(payload, args.json, lambda p: render_request(p, include_full=args.full))


def cmd_events(args: argparse.Namespace) -> None:
    request_id, _ = parse_request_id(args.request)
    raw, response_url, _ = fetch_json(REQUEST_JSON.format(request_id=request_id))
    if not isinstance(raw, dict):
        raise CliError(f"unexpected request JSON shape from {response_url}")

    payload = {
        "kind": "events",
        "meta": make_meta(response_url),
        **event_projection(raw),
    }
    emit(payload, args.json, render_events)


def cmd_search(args: argparse.Namespace) -> None:
    query = (" ".join(args.query_terms)).strip()
    if not query:
        raise CliError("search query is required")

    encoded = urllib.parse.quote_plus(query)
    candidate_urls = []
    for base in SEARCH_URLS:
        candidate_urls.append(f"{base}?query={encoded}")
        candidate_urls.append(f"{base}.json?query={encoded}")

    results: list[dict[str, Any]] = []
    source_url = ""
    last_failure: CliError | None = None
    saw_successful_response = False
    for candidate in candidate_urls:
        try:
            payload, resolved, content_type = fetch_json(candidate)
            saw_successful_response = True
            parsed = parse_search_json(payload)
            source_url = resolved
            results = parsed
            if parsed:
                break
        except CliError as exc:
            # continue to fallback search pages, but remember failures so total
            # upstream failure cannot be reported as an OK empty result.
            if exc.status in {"upstream_blocked", "upstream_unavailable", "http_error"}:
                last_failure = exc
                continue
            raise

    if not results:
        # HTML fallback for non-json search pages
        for base in SEARCH_URLS:
            try:
                html, resolved, _ = fetch_text(f"{base}?query={encoded}")
                saw_successful_response = True
                parsed = parse_search_html(html)
                source_url = resolved
                results = parsed
                if parsed:
                    break
            except CliError as exc:
                if exc.status in {"upstream_blocked", "upstream_unavailable", "http_error"}:
                    last_failure = exc
                    continue
                raise

    if not saw_successful_response:
        if last_failure:
            raise last_failure
        raise CliError(f"upstream_unavailable: no FYI search endpoint responded for {query!r}", status="upstream_unavailable")

    if not source_url:
        source_url = f"{BASE_URL}/search/all?query={encoded}"

    payload = {
        "kind": "request_search",
        "meta": make_meta(source_url),
        "query": query,
        "count": len(results),
        "limit": args.limit,
        "results": results[: args.limit],
    }
    emit(payload, args.json, render_search)


def render_authorities(payload: dict[str, Any]) -> None:
    print(f"FYI authorities: {payload['count']} shown")
    for item in payload.get("authorities", []):
        tags = ", ".join(item.get("tags", [])) or "-"
        print(f"- {item['name']} ({item['url_name']})")
        print(f"  tags: {tags}")
        print(f"  url: {item['url']}")


def render_categories(payload: dict[str, Any]) -> None:
    print(f"FYI authority categories: {payload['count']} available")
    for row in payload.get("categories", []):
        print(f"- {row['category']}: {row['count']}")


def render_body(payload: dict[str, Any]) -> None:
    body = payload["body"]
    print(f"Body: {body['name']} ({body['url_name']})")
    print(f"ID: {body['id']}")
    print(f"tags: {', '.join(body.get('tags', [])) or '-'}")
    print(f"home page: {body['home_page'] or '-'}")
    print(f"url: {body['url']}")


def render_request(payload: dict[str, Any], include_full: bool) -> None:
    req = payload["request"]
    print(f"Request: {req.get('title')}")
    print(f"ID: {req.get('id')}")
    print(f"state: {req.get('described_state')} / {req.get('display_status')}")
    print(f"law: {req.get('law_used')} | updated: {req.get('updated_at')}")
    if req.get("public_body"):
        body = req["public_body"]
        print(f"authority: {body.get('name') or ''} ({body.get('url_name') or ''})")
    if include_full:
        print(f"events: {req.get('event_count', 0)}")
        for event in req.get("events", [])[:10]:
            print(
                f"- {event.get('created_at')} {event.get('event_type')} "
                f"{event.get('described_state')} -> {event.get('calculated_state')}"
            )


def render_events(payload: dict[str, Any]) -> None:
    print(f"Request events: {payload['event_count']} for {payload.get('title')}")
    for event in payload.get("events", []):
        print(
            f"- {event.get('created_at')} {event.get('event_type')} "
            f"{event.get('described_state')} -> {event.get('calculated_state')}"
        )


def render_search(payload: dict[str, Any]) -> None:
    print(f"FYI search for {payload['query']!r}: {payload['count']} hits")
    for item in payload.get("results", []):
        body = item.get("public_body") or {}
        body_name = f" ({body.get('name')})" if isinstance(body, dict) and body.get("name") else ""
        print(f"- [{item.get('id')}] {item.get('title')}{body_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FYI.org.nz OIA/LGOIMA read-only CLI")
    parser.add_argument("--version", action="version", version="fyi-oia-nz 0.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("authorities", help="List authorities from all-authorities.csv")
    p.add_argument("--tag", action="append", default=[], help="filter by authority tag/category")
    p.add_argument("--query", help="filter by name/url_name/short_name text")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_authorities)

    p = sub.add_parser("categories", help="List tags/categories from all-authorities.csv")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_categories)

    p = sub.add_parser("body", help="Fetch public authority metadata")
    p.add_argument("body")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_body)

    p = sub.add_parser("search", help="Search request titles via FYI search pages")
    p.add_argument("query_terms", nargs="+", help="search term words")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("request", help="Fetch request metadata")
    p.add_argument("request")
    p.add_argument("--full", action="store_true", help="include event timeline")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_request)

    p = sub.add_parser("events", help="Flatten request event timeline")
    p.add_argument("request")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_events)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if hasattr(args, "limit") and args.limit < 1:
        fail("--limit must be >= 1")
    try:
        args.func(args)
    except CliError as exc:
        fail(f"{exc}", 1)


if __name__ == "__main__":
    main()
