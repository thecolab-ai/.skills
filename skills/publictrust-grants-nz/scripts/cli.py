#!/usr/bin/env python3
"""Public Trust grants NZ read-only CLI.

Fetches Public Trust's public grants finder configuration, then queries the
public Algolia grants index. No login, application submission, or mutation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NoReturn

BASE = "https://www.publictrust.co.nz"
GRANTS_PAGE = f"{BASE}/grants/?query=&type=organisation"
DEFAULT_INDEX = "prod_publictrust_grants"
UA = os.environ.get(
    "PUBLICTRUST_GRANTS_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(message: str, code: int = 1) -> NoReturn:
    print(f"publictrust-grants-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_text(url: str, *, timeout: int = 10) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-NZ,en;q=0.9",
            "Referer": BASE + "/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        die(f"HTTP {e.code} fetching {url}: {strip_tags(detail)}")
    except urllib.error.URLError as e:
        die(f"network error fetching {url}: {e.reason}")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def js_config_value(page: str, name: str) -> str | None:
    marker = name + ':"'
    if marker not in page:
        return None
    return page.split(marker, 1)[1].split('"', 1)[0].encode("utf-8").decode("unicode_escape")


def get_config(timeout: int = 10) -> dict[str, str]:
    page = fetch_text(GRANTS_PAGE, timeout=timeout)
    app_id = js_config_value(page, "algoliaAppId")
    api_key = js_config_value(page, "algoliaApiKey")
    index = js_config_value(page, "algoliaGrantsIndex") or DEFAULT_INDEX
    alphabetical = js_config_value(page, "algoliaGrantsAlphabeticalReplica")
    if not app_id or not api_key:
        die("could not find Public Trust Algolia app id/search key in the public grants page config")
    return {
        "app_id": app_id,
        "api_key": api_key,
        "index": index,
        "alphabetical_index": alphabetical or index,
        "source_url": GRANTS_PAGE,
    }


def algolia_query(config: dict[str, str], params: dict[str, Any], *, index: str | None = None, timeout: int = 10) -> dict[str, Any]:
    app_id = config["app_id"]
    url = f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
    body = json.dumps({"requests": [{"indexName": index or config["index"], "params": urllib.parse.urlencode(params, doseq=True)}]}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": GRANTS_PAGE,
            "x-algolia-application-id": app_id,
            "x-algolia-api-key": config["api_key"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        die(f"Algolia HTTP {e.code}; Public Trust search key or index may have changed: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling Algolia: {e.reason}")
    except json.JSONDecodeError:
        die("Algolia returned invalid JSON")
    results = data.get("results") or []
    if not results:
        die("Algolia response did not include results")
    result = results[0]
    if isinstance(result, dict) and result.get("message") and not result.get("hits"):
        die(f"Algolia error: {result.get('message')}")
    return result


def algolia_get_object(config: dict[str, str], object_id: str, *, timeout: int = 10) -> dict[str, Any] | None:
    app_id = config["app_id"]
    url = f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/{urllib.parse.quote(config['index'], safe='')}/{urllib.parse.quote(object_id, safe='')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": GRANTS_PAGE,
            "x-algolia-application-id": app_id,
            "x-algolia-api-key": config["api_key"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        detail = e.read().decode("utf-8", "replace")[:300]
        die(f"Algolia object lookup HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling Algolia: {e.reason}")


def slugify(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def public_url(uri: str | None) -> str | None:
    return urllib.parse.urljoin(BASE, uri) if uri else None


def norm_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def normalise_grant(hit: dict[str, Any]) -> dict[str, Any]:
    title = hit.get("title") or ""
    uri = hit.get("uri")
    return {
        "id": hit.get("objectID"),
        "distinct_id": hit.get("distinctObjectID"),
        "slug": uri.rstrip("/").rsplit("/", 1)[-1] if isinstance(uri, str) and uri else slugify(title),
        "title": title or None,
        "url": public_url(uri),
        "grant_type": norm_list(hit.get("grant_type")),
        "regions": norm_list(hit.get("grants_regions")),
        "sectors": norm_list(hit.get("sectors")),
        "applications_open_now": bool(hit.get("applications_open_now")),
        "applications_open_date": hit.get("applications_open_date"),
        "excerpt": strip_tags(str(hit.get("excerpt") or "")) or None,
        "keywords": norm_list(hit.get("keywords")),
    }


def envelope(config: dict[str, str], command: str, result: dict[str, Any], elapsed_ms: int) -> dict[str, Any]:
    return {
        "source_url": config["source_url"],
        "index_name": config["index"],
        "fetched_at": now_iso(),
        "elapsed_ms": elapsed_ms,
        "command": command,
        **result,
    }


def facet_filters(args: argparse.Namespace) -> list[str]:
    filters: list[str] = []
    if getattr(args, "region", None):
        filters.append(f"grants_regions:{args.region}")
    if getattr(args, "sector", None):
        filters.append(f"sectors:{args.sector}")
    if getattr(args, "type", None):
        filters.append(f"grant_type:{args.type}")
    return filters


def search_data(args: argparse.Namespace) -> dict[str, Any]:
    if not args.query.strip():
        die("search requires a non-empty query; use list-open for currently open grants or raw-query for debugging")
    return run_search(args, query=args.query, command="search")


def run_search(args: argparse.Namespace, *, query: str, command: str, index: str | None = None) -> dict[str, Any]:
    start = time.time()
    config = get_config(timeout=args.timeout)
    filters = []
    if getattr(args, "open_only", False):
        filters.append("applications_open_now:true")
    params: dict[str, Any] = {
        "query": query,
        "hitsPerPage": max(1, min(args.limit, 100)),
        "page": max(0, getattr(args, "page", 0)),
    }
    if filters:
        params["filters"] = " AND ".join(filters)
    facets = facet_filters(args)
    if facets:
        params["facetFilters"] = json.dumps(facets)
    data = algolia_query(config, params, index=index, timeout=args.timeout)
    elapsed = int((time.time() - start) * 1000)
    grants = [normalise_grant(hit) for hit in data.get("hits") or [] if isinstance(hit, dict)]
    return envelope(config, command, {"query": query, "page": data.get("page"), "nb_hits": data.get("nbHits"), "returned_count": len(grants), "grants": grants}, elapsed)


def list_open_data(args: argparse.Namespace) -> dict[str, Any]:
    args.open_only = True
    start = time.time()
    config = get_config(timeout=args.timeout)
    params = {"query": "", "hitsPerPage": max(1, min(args.limit, 100)), "page": max(0, args.page), "filters": "applications_open_now:true"}
    facets = facet_filters(args)
    if facets:
        params["facetFilters"] = json.dumps(facets)
    data = algolia_query(config, params, index=config.get("alphabetical_index") or config["index"], timeout=args.timeout)
    elapsed = int((time.time() - start) * 1000)
    grants = [normalise_grant(hit) for hit in data.get("hits") or [] if isinstance(hit, dict)]
    return envelope(config, "list-open", {"page": data.get("page"), "nb_hits": data.get("nbHits"), "returned_count": len(grants), "grants": grants}, elapsed)


def detail_data(args: argparse.Namespace) -> dict[str, Any]:
    start = time.time()
    config = get_config(timeout=args.timeout)
    ident = args.id_or_slug.strip()
    grant = algolia_get_object(config, ident, timeout=args.timeout)
    if grant is None:
        # Slug or title fallback via normal search.
        data = algolia_query(config, {"query": ident, "hitsPerPage": 20, "page": 0}, timeout=args.timeout)
        wanted = slugify(ident)
        matches = [h for h in data.get("hits") or [] if isinstance(h, dict)]
        grant = next((h for h in matches if normalise_grant(h).get("slug") == wanted or slugify(str(h.get("title") or "")) == wanted), None)
        if grant is None and len(matches) == 1:
            grant = matches[0]
    if grant is None:
        die(f"no Public Trust grant found for {ident!r}", 2)
    elapsed = int((time.time() - start) * 1000)
    return envelope(config, "detail", {"grant": normalise_grant(grant)}, elapsed)


def list_values(args: argparse.Namespace, field: str, command: str) -> dict[str, Any]:
    start = time.time()
    config = get_config(timeout=args.timeout)
    data = algolia_query(config, {"query": "", "hitsPerPage": 100, "page": 0}, timeout=args.timeout)
    values: dict[str, int] = {}
    total = data.get("nbHits") or 0
    pages = min(10, max(1, int((int(total) + 99) / 100))) if isinstance(total, int) else 1
    for page in range(pages):
        if page:
            data = algolia_query(config, {"query": "", "hitsPerPage": 100, "page": page}, timeout=args.timeout)
        for hit in data.get("hits") or []:
            for value in norm_list(hit.get(field)):
                values[value] = values.get(value, 0) + 1
    elapsed = int((time.time() - start) * 1000)
    return envelope(config, command, {command: [{"value": k, "count": v} for k, v in sorted(values.items())]}, elapsed)


def raw_query_data(args: argparse.Namespace) -> dict[str, Any]:
    start = time.time()
    config = get_config(timeout=args.timeout)
    params: dict[str, Any] = {"query": args.query, "hitsPerPage": max(1, min(args.limit, 100)), "page": max(0, args.page)}
    if args.params:
        for pair in args.params:
            if "=" not in pair:
                die(f"raw-query --param expects key=value, got {pair!r}")
            k, v = pair.split("=", 1)
            params[k] = v
    data = algolia_query(config, params, timeout=args.timeout)
    elapsed = int((time.time() - start) * 1000)
    return envelope(config, "raw-query", {"params": params, "algolia_result": data}, elapsed)


def print_output(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if "grant" in data:
        grants = [data["grant"]]
    else:
        grants = data.get("grants") or []
    if grants:
        print(f"Public Trust grants ({data.get('returned_count', len(grants))} shown; {data.get('nb_hits', 'unknown')} matching)")
        for g in grants:
            status = "open" if g.get("applications_open_now") else "not currently open"
            print(f"- {g.get('title')} [{status}]")
            if g.get("applications_open_date"):
                print(f"  Dates: {g['applications_open_date']}")
            if g.get("regions"):
                print(f"  Regions: {', '.join(g['regions'])}")
            if g.get("sectors"):
                print(f"  Sectors: {', '.join(g['sectors'])}")
            print(f"  {g.get('url')}")
        return
    for key in ("sectors", "regions"):
        if key in data:
            for row in data[key]:
                print(f"{row['value']} ({row['count']})")
            return
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Query Public Trust NZ public grants finder data")
    p.add_argument("--timeout", type=int, default=10, help="network timeout in seconds")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search grants by keyword")
    s.add_argument("query")
    s.add_argument("--region")
    s.add_argument("--sector")
    s.add_argument("--type", default="organisation")
    s.add_argument("--open-only", action="store_true")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--page", type=int, default=0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=search_data)

    o = sub.add_parser("list-open", help="list grants flagged as open now")
    o.add_argument("--region")
    o.add_argument("--sector")
    o.add_argument("--type", default=None)
    o.add_argument("--limit", type=int, default=10)
    o.add_argument("--page", type=int, default=0)
    o.add_argument("--json", action="store_true")
    o.set_defaults(func=list_open_data)

    d = sub.add_parser("detail", help="look up one grant by Algolia object id, title, or slug")
    d.add_argument("id_or_slug")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=detail_data)

    sec = sub.add_parser("sectors", help="list observed sector facet values")
    sec.add_argument("--json", action="store_true")
    sec.set_defaults(func=lambda a: list_values(a, "sectors", "sectors"))

    reg = sub.add_parser("regions", help="list observed region facet values")
    reg.add_argument("--json", action="store_true")
    reg.set_defaults(func=lambda a: list_values(a, "grants_regions", "regions"))

    raw = sub.add_parser("raw-query", help="debug raw Algolia query parameters")
    raw.add_argument("query")
    raw.add_argument("--limit", type=int, default=10)
    raw.add_argument("--page", type=int, default=0)
    raw.add_argument("--param", dest="params", action="append", default=[], help="extra Algolia key=value parameter")
    raw.add_argument("--json", action="store_true")
    raw.set_defaults(func=raw_query_data)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data = args.func(args)
    print_output(data, getattr(args, "json", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
