#!/usr/bin/env python3
"""NZ News RSS aggregator CLI.

Read-only stdlib wrapper aggregating RSS/Atom feeds from major New Zealand
news websites. Provides headlines, search, source status, and summary.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

UA = "nz-news-cli/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 10

# Feed definitions
FEEDS = [
    {"id": "herald",         "name": "NZ Herald",       "url": "https://rss.nzherald.co.nz/rss/xml/nzhrsscid_000000001.xml", "format": "rss"},
    {"id": "stuff",          "name": "Stuff",            "url": "https://www.stuff.co.nz/rss",                                "format": "atom"},
    {"id": "rnz",            "name": "RNZ",              "url": "https://www.rnz.co.nz/rss/news.xml",                         "format": "rss"},
    {"id": "rnz-politics",   "name": "RNZ Politics",     "url": "https://www.rnz.co.nz/rss/political.xml",                    "format": "rss", "category": "politics"},
    {"id": "rnz-business",   "name": "RNZ Business",     "url": "https://www.rnz.co.nz/rss/business.xml",                     "format": "rss", "category": "business"},
    {"id": "rnz-national",   "name": "RNZ National",     "url": "https://www.rnz.co.nz/rss/national.xml",                     "format": "rss", "category": "national"},
    {"id": "rnz-world",      "name": "RNZ World",        "url": "https://www.rnz.co.nz/rss/world.xml",                        "format": "rss", "category": "world"},
    {"id": "rnz-sport",      "name": "RNZ Sport",        "url": "https://www.rnz.co.nz/rss/sport.xml",                        "format": "rss", "category": "sport"},
    {"id": "rnz-te-ao-maori","name": "RNZ Te Ao Maori",  "url": "https://www.rnz.co.nz/rss/te-ao-maori.xml",                  "format": "rss", "category": "te-ao-maori"},
    {"id": "newsroom",       "name": "Newsroom",         "url": "https://www.newsroom.co.nz/rss",                             "format": "rss"},
    {"id": "spinoff",        "name": "The Spinoff",      "url": "https://thespinoff.co.nz/feed",                              "format": "atom"},
    {"id": "interest",       "name": "Interest.co.nz",   "url": "https://www.interest.co.nz/rss",                             "format": "rss"},
]

PRIMARY_FEED_IDS = ["herald", "stuff", "rnz", "newsroom", "spinoff", "interest"]
FEED_BY_ID = {f["id"]: f for f in FEEDS}

try:
    from zoneinfo import ZoneInfo
    NZ_TZ: dt.tzinfo = ZoneInfo("Pacific/Auckland")
except Exception:
    NZ_TZ = dt.timezone(dt.timedelta(hours=12), name="Pacific/Auckland")


def die(message: str, code: int = 1) -> None:
    print(f"nz-news: {message}", file=sys.stderr)
    raise SystemExit(code)


def positive_int(raw: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    if v <= 0:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    return v


def positive_number(raw: str) -> float:
    try:
        v = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected positive number, got: {raw}")
    if not (v > 0 and v != float("inf")):
        raise argparse.ArgumentTypeError(f"Expected positive number, got: {raw}")
    return v


def parse_since_date(raw: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.isoformat()
    except Exception:
        raise argparse.ArgumentTypeError(f"Expected ISO date or date-time, got: {raw}")


def parse_csv_list(raw: str) -> list[str]:
    values = [v.strip() for v in raw.split(",") if v.strip()]
    if not values:
        raise argparse.ArgumentTypeError("Expected a comma-separated list with at least one value.")
    return values


def format_date(published: dt.datetime) -> str:
    if published.timestamp() == 0:
        return "unknown"
    try:
        d = published.astimezone(NZ_TZ)
        return d.strftime("%-d %b %Y, %-I:%M %p")
    except Exception:
        return published.isoformat()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- RSS/Atom parsing ---

def decode_entities(text: str) -> str:
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&apos;", "'")
    return text


def strip_cdata(text: str) -> str:
    m = re.match(r"^\s*<!\[CDATA\[([\s\S]*?)\]\]>\s*$", text)
    return m.group(1) if m else text


def extract_tag(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", xml, re.IGNORECASE)
    if not m:
        return ""
    return decode_entities(strip_cdata(m.group(1).strip()))


def extract_attr(xml: str, tag: str, attr: str) -> str:
    m = re.search(rf'<{tag}[^>]*?{attr}="([^"]*)"', xml, re.IGNORECASE)
    return decode_entities(m.group(1)) if m else ""


def parse_date(raw: str) -> dt.datetime:
    if not raw:
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    # Standard parsing
    try:
        # Handle RFC 2822 style dates (most RSS)
        return dt.datetime.strptime(raw.strip(), "%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        pass
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass
    # Try Interest.co.nz format: "10th Apr 26, 4:12pm"
    m = re.match(r"(\d+)\w*\s+(\w+)\s+(\d+),\s*(\d+):(\d+)(am|pm)", raw, re.IGNORECASE)
    if m:
        day, month, year, hours, minutes, ampm = m.groups()
        full_year = 2000 + int(year) if int(year) < 100 else int(year)
        h = int(hours)
        if ampm.lower() == "pm" and h < 12:
            h += 12
        if ampm.lower() == "am" and h == 12:
            h = 0
        try:
            d = dt.datetime(full_year, dt.datetime.strptime(month, "%b").month, int(day), h, int(minutes),
                            tzinfo=dt.timezone(dt.timedelta(hours=12)))
            return d
        except Exception:
            pass
    return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def parse_rss_items(xml: str, feed: dict) -> list[dict]:
    items = []
    for m in re.finditer(r"<item>([\s\S]*?)</item>", xml, re.IGNORECASE):
        block = m.group(1)
        title = extract_tag(block, "title")
        link = extract_tag(block, "link")
        pub_date = extract_tag(block, "pubDate")
        description = extract_tag(block, "description")
        if title and link:
            items.append({
                "title": strip_html(title).strip(),
                "url": link.strip(),
                "published": parse_date(pub_date),
                "source": feed["name"],
                "sourceId": feed["id"],
                "summary": strip_html(description).strip() or None,
            })
    return items


def parse_atom_items(xml: str, feed: dict) -> list[dict]:
    items = []
    for m in re.finditer(r"<entry>([\s\S]*?)</entry>", xml, re.IGNORECASE):
        block = m.group(1)
        title = extract_tag(block, "title")
        link = extract_attr(block, "link", "href")
        published = extract_tag(block, "published") or extract_tag(block, "updated")
        summary = extract_tag(block, "summary") or extract_tag(block, "content")
        if title and link:
            items.append({
                "title": strip_html(title).strip(),
                "url": link.strip(),
                "published": parse_date(published),
                "source": feed["name"],
                "sourceId": feed["id"],
                "summary": strip_html(summary).strip() or None,
            })
    return items


def fetch_feed(feed: dict) -> dict:
    start = time.monotonic()
    try:
        xml = nzfetch.fetch_text(
            feed["url"],
            timeout=DEFAULT_TIMEOUT,
            accept="application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            headers={"User-Agent": UA},
        )
        duration_ms = round((time.monotonic() - start) * 1000)
        items = parse_atom_items(xml, feed) if feed.get("format") == "atom" else parse_rss_items(xml, feed)
        return {"feed": feed, "items": items, "ok": True, "error": None, "durationMs": duration_ms}
    except nzfetch.Blocked as e:
        return {"feed": feed, "items": [], "ok": False, "error": f"network error: {e}", "durationMs": round((time.monotonic() - start) * 1000)}
    except nzfetch.FetchError as e:
        return {"feed": feed, "items": [], "ok": False, "error": str(e), "durationMs": round((time.monotonic() - start) * 1000)}
    except Exception as err:
        return {"feed": feed, "items": [], "ok": False, "error": str(err), "durationMs": round((time.monotonic() - start) * 1000)}


def fetch_feeds(feed_ids: list[str] | None = None) -> list[dict]:
    selected = [FEED_BY_ID[fid] for fid in (feed_ids or PRIMARY_FEED_IDS) if fid in FEED_BY_ID]
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_feed, feed): feed for feed in selected}
        for future in as_completed(futures):
            results.append(future.result())
    # Maintain stable order matching selected
    order = {f["id"]: i for i, f in enumerate(selected)}
    results.sort(key=lambda r: order.get(r["feed"]["id"], 999))
    return results


def deduplicate_items(items: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in items:
        key = re.sub(r"[^a-z0-9]+", " ", item["title"].lower()).strip()
        existing = seen.get(key)
        if not existing or item["published"] > existing["published"]:
            seen[key] = item
    return list(seen.values())


def sort_by_date(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: i["published"], reverse=True)


def collect_items(results: list[dict]) -> list[dict]:
    all_items = [item for r in results for item in r["items"]]
    return sort_by_date(deduplicate_items(all_items))


def normalise_search_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def searchable_text(item: dict) -> str:
    return normalise_search_text(f"{item['title']} {item.get('summary') or ''}")


def matches_keyword(item: dict, keyword: str, exact: bool = False, contains_all: bool = False) -> bool:
    haystack = searchable_text(item)
    kw = normalise_search_text(keyword)
    if not kw:
        return True
    if exact:
        pattern = r"(^| )" + re.escape(kw).replace(r"\ ", r" +") + r"( |$)"
        return bool(re.search(pattern, haystack, re.IGNORECASE))
    if contains_all:
        terms = kw.split()
        return all(t in haystack for t in terms)
    return kw in haystack


def within_since_window(item: dict, since_hours: float | None, since_date: str | None) -> bool:
    ts = item["published"].timestamp()
    if ts == 0:
        return False
    if since_hours is not None:
        cutoff = time.time() - since_hours * 3600
        return ts >= cutoff
    if since_date:
        try:
            cutoff = dt.datetime.fromisoformat(since_date).timestamp()
            return ts >= cutoff
        except Exception:
            pass
    return True


def passes_exclude(item: dict, exclude: list[str]) -> bool:
    if not exclude:
        return True
    haystack = searchable_text(item)
    return not any(normalise_search_text(term) in haystack for term in exclude)


def apply_search_filters(
    items: list[dict],
    keyword: str,
    since_hours: float | None = None,
    since_date: str | None = None,
    exact: bool = False,
    contains_all: bool = False,
    exclude: list[str] | None = None,
) -> list[dict]:
    exclude = exclude or []
    return [
        item for item in items
        if within_since_window(item, since_hours, since_date)
        and passes_exclude(item, exclude)
        and matches_keyword(item, keyword, exact=exact, contains_all=contains_all)
    ]


def resolve_feed(name: str) -> dict | None:
    lower = name.lower()
    exact = next((f for f in FEEDS if f["id"] == lower or f["name"].lower() == lower), None)
    if exact:
        return exact
    partial = [f for f in FEEDS if f["id"].startswith(lower) or lower in f["name"].lower()]
    return partial[0] if len(partial) == 1 else None


def resolve_sources(raw_sources: list[str] | None) -> list[dict]:
    if not raw_sources:
        return [f for f in FEEDS if f["id"] in PRIMARY_FEED_IDS]
    resolved = []
    for raw in raw_sources:
        feed = resolve_feed(raw)
        if not feed:
            die(f'Unknown source: "{raw}". Run "nz-news sources" to see available sources.')
        if not any(f["id"] == feed["id"] for f in resolved):
            resolved.append(feed)
    return resolved


def render_items(items: list[dict], limit: int) -> str:
    lines = []
    for i, item in enumerate(items[:limit], 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   {item['source']} · {format_date(item['published'])}")
        lines.append(f"   {item['url']}")
    return "\n".join(lines)


def feed_errors(results: list[dict]) -> str:
    failed = [r for r in results if not r["ok"]]
    if not failed:
        return ""
    return "\nFailed feeds: " + ", ".join(f"{r['feed']['name']} ({r['error']})" for r in failed)


def items_to_json(items: list[dict]) -> list[dict]:
    return [
        {
            "title": item["title"],
            "url": item["url"],
            "published": item["published"].isoformat(),
            "source": item["source"],
            "sourceId": item["sourceId"],
            "summary": item.get("summary"),
        }
        for item in items
    ]


def emit(data: Any, as_json: bool, render_fn) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        print(render_fn())


# --- Commands ---

def cmd_headlines(args: argparse.Namespace) -> None:
    limit = args.limit or 10
    results = fetch_feeds()
    items = collect_items(results)
    shown = items[:limit]

    output = {
        "fetchedAt": now_utc(),
        "sourcesQueried": len(results),
        "sourcesOk": sum(1 for r in results if r["ok"]),
        "totalItems": len(items),
        "returnedCount": len(shown),
        "items": items_to_json(shown),
        "errors": [{"source": r["feed"]["name"], "error": r["error"]} for r in results if not r["ok"]],
    }

    def render() -> str:
        lines = [f"NZ Headlines -- {len(shown)} of {len(items)} stories from {output['sourcesOk']} sources", ""]
        lines.append(render_items(items, limit))
        lines.append(feed_errors(results))
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_source(args: argparse.Namespace) -> None:
    feed = resolve_feed(args.name)
    if not feed:
        die(f'Unknown source: "{args.name}". Run "nz-news sources" to see available sources.')
    limit = args.limit or 10
    result = fetch_feed(feed)
    if not result["ok"]:
        die(f"Failed to fetch {feed['name']}: {result['error']}")
    items = sort_by_date(result["items"])[:limit]

    output = {
        "fetchedAt": now_utc(),
        "source": feed["name"],
        "sourceId": feed["id"],
        "totalItems": len(result["items"]),
        "returnedCount": len(items),
        "items": items_to_json(items),
    }

    def render() -> str:
        lines = [f"{feed['name']} -- {len(items)} of {len(result['items'])} stories", ""]
        lines.append(render_items(items, limit))
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_search(args: argparse.Namespace) -> None:
    # Validate flags
    if getattr(args, "contains_all", False) and getattr(args, "exact", False):
        die("Use either --contains-all or --exact, not both.")
    if getattr(args, "since_hours", None) is not None and getattr(args, "since_date", None):
        die("Use either --since-hours or --since-date, not both.")

    keyword_parts = getattr(args, "keyword_parts", []) or []
    keyword_flag = getattr(args, "keyword", None) or ""
    positional_kw = " ".join(keyword_parts).strip()

    if positional_kw and keyword_flag:
        die("Use either a positional search term or --keyword, not both.")
    keyword = positional_kw or keyword_flag
    if not keyword:
        die('A search keyword is required. Try "nz-news search cyclone" or "nz-news search --keyword cyclone".')

    feeds = resolve_sources(getattr(args, "source", None))
    limit = args.limit or 10
    feed_ids = [f["id"] for f in feeds]

    results = fetch_feeds(feed_ids)
    all_items = collect_items(results)
    filtered = apply_search_filters(
        all_items,
        keyword=keyword,
        since_hours=getattr(args, "since_hours", None),
        since_date=getattr(args, "since_date", None),
        exact=bool(getattr(args, "exact", False)),
        contains_all=bool(getattr(args, "contains_all", False)),
        exclude=getattr(args, "exclude", None) or [],
    )
    shown = filtered[:limit]

    exact = bool(getattr(args, "exact", False))
    contains_all = bool(getattr(args, "contains_all", False))
    match_mode = "exact" if exact else "contains-all" if contains_all else "substring"

    output = {
        "fetchedAt": now_utc(),
        "keyword": keyword,
        "matchMode": match_mode,
        "sourcesQueried": len(results),
        "sourcesOk": sum(1 for r in results if r["ok"]),
        "filters": {
            "sourceIds": feed_ids,
            "sinceHours": getattr(args, "since_hours", None),
            "sinceDate": getattr(args, "since_date", None),
            "exclude": getattr(args, "exclude", None) or [],
            "limit": limit,
        },
        "totalMatching": len(filtered),
        "returnedCount": len(shown),
        "items": items_to_json(shown),
        "errors": [{"source": r["feed"]["name"], "error": r["error"]} for r in results if not r["ok"]],
    }

    def render() -> str:
        lines = [f'NZ News search: "{keyword}" -- {len(filtered)} matching stories']
        if len(feeds) != len([f for f in FEEDS if f["id"] in PRIMARY_FEED_IDS]):
            lines.append(f"Sources: {', '.join(f['id'] for f in feeds)}")
        since_hours = getattr(args, "since_hours", None)
        since_date = getattr(args, "since_date", None)
        if since_hours is not None:
            lines.append(f"Since: last {since_hours} hour{'s' if since_hours != 1 else ''}")
        if since_date:
            lines.append(f"Since date: {since_date}")
        if contains_all:
            lines.append("Match mode: all search terms must appear")
        if exact:
            lines.append("Match mode: exact phrase")
        excl = getattr(args, "exclude", None) or []
        if excl:
            lines.append(f"Exclude: {', '.join(excl)}")
        lines.append("")
        if not shown:
            lines.append("No stories matched those filters.")
        else:
            lines.append(render_items(filtered, limit))
        lines.append(feed_errors(results))
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_sources(args: argparse.Namespace) -> None:
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_feed, feed): feed for feed in FEEDS}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda r: next((i for i, f in enumerate(FEEDS) if f["id"] == r["feed"]["id"]), 999))

    source_list = [
        {
            "id": r["feed"]["id"],
            "name": r["feed"]["name"],
            "url": r["feed"]["url"],
            "format": r["feed"].get("format"),
            "category": r["feed"].get("category"),
            "primary": r["feed"]["id"] in PRIMARY_FEED_IDS,
            "status": "ok" if r["ok"] else "error",
            "itemCount": len(r["items"]),
            "error": r["error"],
            "durationMs": r["durationMs"],
        }
        for r in results
    ]

    output = {
        "fetchedAt": now_utc(),
        "totalSources": len(source_list),
        "working": sum(1 for s in source_list if s["status"] == "ok"),
        "failed": sum(1 for s in source_list if s["status"] == "error"),
        "sources": source_list,
    }

    def render() -> str:
        lines = [f"NZ News Sources -- {output['working']}/{output['totalSources']} working", ""]
        for s in source_list:
            if s["status"] == "ok":
                status = f"ok {s['itemCount']} items"
            else:
                status = f"ERROR {s['error']}"
            primary = "" if s["primary"] else " (category feed)"
            lines.append(f"  {s['id']:<18} {s['name']:<20} {status}{primary}")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_summary(args: argparse.Namespace) -> None:
    results = fetch_feeds()
    items = collect_items(results)
    top5 = items[:5]
    ok_sources = [r for r in results if r["ok"]]

    output = {
        "fetchedAt": now_utc(),
        "sourcesQueried": len(results),
        "sourcesOk": len(ok_sources),
        "totalStories": len(items),
        "top5": items_to_json(top5),
        "errors": [{"source": r["feed"]["name"], "error": r["error"]} for r in results if not r["ok"]],
    }

    def render() -> str:
        lines = [
            f"NZ News Summary -- {len(items)} stories from {len(ok_sources)} sources",
            "",
            "Top 5 headlines:",
        ]
        for i, item in enumerate(top5, 1):
            lines.append(f"  {i}. {item['title']} ({item['source']})")
        lines.append(feed_errors(results))
        return "\n".join(lines)

    emit(output, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Aggregate RSS feeds from New Zealand news websites."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("headlines", help="top headlines across all primary sources, deduplicated and sorted by date")
    sp.add_argument("--limit", type=positive_int, default=10, help="number of items to show (default 10)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_headlines)

    sp = sub.add_parser("source", help="news from a specific source")
    sp.add_argument("name", help="source ID or name (e.g. rnz, herald, stuff)")
    sp.add_argument("--limit", type=positive_int, default=10, help="number of items to show (default 10)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_source)

    sp = sub.add_parser("search", help="search headlines and summaries across NZ sources")
    sp.add_argument("keyword_parts", nargs="*", metavar="keyword",
                    help="search term (positional)")
    sp.add_argument("--keyword", help="search phrase (flag form)")
    sp.add_argument("--source", type=parse_csv_list, metavar="IDS",
                    help="comma-separated source IDs or names, e.g. rnz,herald")
    sp.add_argument("--since-hours", type=positive_number, dest="since_hours",
                    help="only include stories from the last N hours")
    sp.add_argument("--since-date", type=parse_since_date, dest="since_date",
                    help="only include stories on or after this ISO date")
    sp.add_argument("--contains-all", action="store_true", dest="contains_all",
                    help="require every search term to appear (multi-word searches)")
    sp.add_argument("--exact", action="store_true",
                    help="match the exact phrase")
    sp.add_argument("--exclude", type=parse_csv_list,
                    help="comma-separated terms to exclude from title or summary")
    sp.add_argument("--limit", type=positive_int, default=10, help="number of items to show (default 10)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    # topic is an alias for search
    sp2 = sub.add_parser("topic", help="alias for search")
    sp2.add_argument("keyword_parts", nargs="*", metavar="keyword")
    sp2.add_argument("--keyword")
    sp2.add_argument("--source", type=parse_csv_list, metavar="IDS")
    sp2.add_argument("--since-hours", type=positive_number, dest="since_hours")
    sp2.add_argument("--since-date", type=parse_since_date, dest="since_date")
    sp2.add_argument("--contains-all", action="store_true", dest="contains_all")
    sp2.add_argument("--exact", action="store_true")
    sp2.add_argument("--exclude", type=parse_csv_list)
    sp2.add_argument("--limit", type=positive_int, default=10)
    sp2.add_argument("--json", action="store_true")
    sp2.set_defaults(func=cmd_search)

    sp = sub.add_parser("sources", help="list all available news sources with a live status check")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_sources)

    sp = sub.add_parser("summary", help="brief summary: story count, source count, and top 5 headlines")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_summary)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
