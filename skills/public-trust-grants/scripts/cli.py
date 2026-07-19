#!/usr/bin/env python3
"""Read-only CLI for Public Trust NZ grant search."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import pathlib
import re
import sys
import textwrap
import urllib.parse
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_URL = "https://www.publictrust.co.nz"
GRANTS_URL = f"{BASE_URL}/grants/"
USER_AGENT = "thecolab-ai-public-trust-grants/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 10
MAX_HITS = 50
ALGOLIA_APP_ID = "00GCMOPT4B"
ALGOLIA_HOST = f"{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"


class UpstreamError(RuntimeError):
    pass


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    try:
        return nzfetch.fetch_text(url, timeout=timeout, accept="text/html,application/json")
    except nzfetch.FetchError as exc:
        raise UpstreamError(f"Could not fetch {url}: {exc}") from exc


def fetch_json(url: str, payload: dict[str, Any], app_id: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    try:
        return nzfetch.fetch_json(
            url,
            timeout=timeout,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": api_key,
            },
        )
    except nzfetch.FetchError as exc:
        raise UpstreamError(f"Could not query Public Trust Algolia search: {exc}") from exc


def _extract_config_value(page: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}:\"([^\"]+)\"", page)
    if not match:
        raise UpstreamError(f"Public Trust page did not expose expected {name} search configuration")
    return match.group(1)


def load_config(timeout: int = DEFAULT_TIMEOUT) -> dict[str, str]:
    """Load the public Algolia search config from the grants page.

    The API key is a browser search-only key already published in the Nuxt payload; this skill
    fetches it dynamically instead of committing it.
    """

    page = fetch_text(GRANTS_URL, timeout=timeout)
    config = {
        "app_id": _extract_config_value(page, "algoliaAppId"),
        "api_key": _extract_config_value(page, "algoliaApiKey"),
        "index": _extract_config_value(page, "algoliaGrantsIndex"),
        "alphabetical_index": _extract_config_value(page, "algoliaGrantsAlphabeticalReplica"),
    }
    if config["app_id"].upper() != ALGOLIA_APP_ID:
        raise UpstreamError(
            "Public Trust Algolia application ID changed; review the outbound allowlist before querying it"
        )
    return config


def algolia_query(payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    config = load_config(timeout=timeout)
    index = urllib.parse.quote(payload.pop("_index", config["index"]), safe="")
    url = f"https://{ALGOLIA_HOST}/1/indexes/{index}/query"
    return fetch_json(url, payload, config["app_id"], config["api_key"], timeout=timeout)


def normalise_hit(hit: dict[str, Any]) -> dict[str, Any]:
    uri = hit.get("uri") or ""
    source_url = urllib.parse.urljoin(BASE_URL, uri) if uri else None
    return {
        "title": hit.get("title"),
        "source_url": source_url,
        "uri": uri or None,
        "excerpt": hit.get("excerpt"),
        "grant_type": hit.get("grant_type") or [],
        "regions": hit.get("grants_regions") or [],
        "sectors": hit.get("sectors") or [],
        "applications_open_now": bool(hit.get("applications_open_now")),
        "applications_open_date": hit.get("applications_open_date"),
        "object_id": hit.get("objectID"),
    }


def build_filters(args: argparse.Namespace) -> str | None:
    filters: list[str] = []
    if args.type:
        filters.append(f"grant_type:{args.type}")
    if args.region:
        filters.append(f"grants_regions:{args.region}")
    if args.sector:
        filters.append(f"sectors:{args.sector}")
    if args.open_now:
        filters.append("applications_open_now:true")
    return " AND ".join(filters) if filters else None


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    per_page = max(1, min(args.limit, MAX_HITS))
    payload: dict[str, Any] = {
        "query": args.query or "",
        "hitsPerPage": per_page,
        "page": max(0, args.page),
        "facets": ["grant_type", "grants_regions", "sectors", "applications_open_now"],
    }
    filters = build_filters(args)
    if filters:
        payload["filters"] = filters
    if not args.query:
        payload["_index"] = load_config(timeout=args.timeout)["alphabetical_index"]
    data = algolia_query(payload, timeout=args.timeout)
    return {
        "source": "public_trust_algolia",
        "source_url": GRANTS_URL,
        "query": args.query or "",
        "filters": {"type": args.type, "region": args.region, "sector": args.sector, "open_now": args.open_now},
        "page": data.get("page"),
        "pages": data.get("nbPages"),
        "total": data.get("nbHits"),
        "grants": [normalise_hit(hit) for hit in data.get("hits", [])],
        "facets": data.get("facets", {}),
    }


def command_facets(args: argparse.Namespace) -> dict[str, Any]:
    """Derive available facets from public hits.

    The Public Trust index responds to facet filter expressions but did not return facet
    aggregations in recon, so this command counts the small public result set client-side.
    """

    config = load_config(timeout=args.timeout)
    first = algolia_query(
        {"_index": config["alphabetical_index"], "query": "", "hitsPerPage": 100, "page": 0},
        timeout=args.timeout,
    )
    hits = list(first.get("hits", []))
    pages = int(first.get("nbPages") or 1)
    for page in range(1, min(pages, 20)):
        data = algolia_query(
            {"_index": config["alphabetical_index"], "query": "", "hitsPerPage": 100, "page": page},
            timeout=args.timeout,
        )
        hits.extend(data.get("hits", []))
    facets: dict[str, dict[str, int]] = {
        "grant_type": {},
        "grants_regions": {},
        "sectors": {},
        "applications_open_now": {},
    }
    for hit in hits:
        for source_key, values in (
            ("grant_type", hit.get("grant_type") or []),
            ("grants_regions", hit.get("grants_regions") or []),
            ("sectors", hit.get("sectors") or []),
        ):
            for value in values:
                facets[source_key][value] = facets[source_key].get(value, 0) + 1
        open_key = "true" if hit.get("applications_open_now") else "false"
        facets["applications_open_now"][open_key] = facets["applications_open_now"].get(open_key, 0) + 1
    return {"source": "public_trust_algolia", "source_url": GRANTS_URL, "total_sampled": len(hits), "facets": facets}


class MainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "nav", "footer"}:
            self.skip += 1
        if tag in {"p", "li", "h1", "h2", "h3", "br"} and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "nav", "footer"} and self.skip:
            self.skip -= 1
        if tag in {"p", "li", "h1", "h2", "h3"} and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            text = " ".join(data.split())
            if text:
                self.parts.append(text + " ")

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = html_lib.unescape(raw)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def command_detail(args: argparse.Namespace) -> dict[str, Any]:
    slug_or_url = args.slug_or_url.strip()
    if slug_or_url.startswith("http://") or slug_or_url.startswith("https://"):
        url = slug_or_url
    else:
        slug = slug_or_url.strip("/")
        if slug.startswith("grants/"):
            slug = slug.split("/", 1)[1]
        url = f"{BASE_URL}/grants/{urllib.parse.quote(slug)}/"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"publictrust.co.nz", "www.publictrust.co.nz"}:
        raise ValueError("grant URL must use the declared Public Trust HTTPS host")
    page = fetch_text(url, timeout=args.timeout)
    title = None
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.I | re.S)
    if title_match:
        title = " ".join(re.sub(r"<[^>]+>", " ", title_match.group(1)).split())
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', page, flags=re.I)
    parser = MainTextParser()
    parser.feed(page)
    text = parser.text()
    # Keep detail output useful but bounded.
    max_chars = max(500, args.max_chars)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n…"
    return {
        "source": "public_trust_grant_page",
        "source_url": url,
        "title": title,
        "description": html_lib.unescape(desc_match.group(1)) if desc_match else None,
        "text": text,
    }


def print_human_search(data: dict[str, Any]) -> None:
    print(f"Public Trust grants: {data.get('total')} result(s), page {(data.get('page') or 0) + 1}/{data.get('pages')}")
    for grant in data["grants"]:
        print(f"\n- {grant['title']}")
        if grant["excerpt"]:
            print(textwrap.shorten(grant["excerpt"], width=220, placeholder="…"))
        tags = []
        for key in ("grant_type", "regions", "sectors"):
            if grant[key]:
                tags.append(f"{key}: {', '.join(grant[key])}")
        tags.append(f"applications open now: {grant['applications_open_now']}")
        print("  " + " | ".join(tags))
        if grant["source_url"]:
            print(f"  {grant['source_url']}")


def print_human_facets(data: dict[str, Any]) -> None:
    for facet, values in sorted(data.get("facets", {}).items()):
        print(f"{facet}:")
        for value, count in sorted(values.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {value}: {count}")


def print_human_detail(data: dict[str, Any]) -> None:
    print(data.get("title") or data["source_url"])
    if data.get("description"):
        print("\n" + data["description"])
    print(f"\nSource: {data['source_url']}\n")
    print(data.get("text") or "No readable page text found.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search Public Trust NZ public grant and scholarship listings.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Network timeout in seconds (default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search grant listings")
    search.add_argument("query", nargs="?", default="", help="Keyword query, e.g. community, education, scholarship")
    search.add_argument("--type", choices=["individual", "organisation"], help="Filter by grant type")
    search.add_argument("--region", help="Filter by grants_regions facet slug")
    search.add_argument("--sector", help="Filter by sectors facet slug")
    search.add_argument("--open-now", action="store_true", help="Only include grants marked applications_open_now")
    search.add_argument("--limit", type=int, default=10, help="Results per page, max 50")
    search.add_argument("--page", type=int, default=0, help="Zero-based result page")
    search.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    search.set_defaults(func=command_search, human=print_human_search)

    facets = sub.add_parser("facets", help="List available filter facet values and counts")
    facets.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    facets.set_defaults(func=command_facets, human=print_human_facets)

    detail = sub.add_parser("detail", help="Fetch readable text from a public grant detail page")
    detail.add_argument("slug_or_url", help="Grant slug, /grants/... path, or full Public Trust grant URL")
    detail.add_argument("--max-chars", type=int, default=5000, help="Maximum detail text characters to print")
    detail.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    detail.set_defaults(func=command_detail, human=print_human_detail)

    args = parser.parse_args(argv)
    try:
        data = args.func(args)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            args.human(data)
        return 0
    except UpstreamError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": "upstream_unavailable", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": "invalid_input", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
