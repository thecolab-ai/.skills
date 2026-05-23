#!/usr/bin/env python3
"""Eventfinda NZ public website lookup CLI.

Self-contained stdlib wrapper around public Eventfinda NZ pages. It does not
use account login, cookies, or the Basic-auth Eventfinda developer API.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://www.eventfinda.co.nz"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146 Safari/537.36"
EVENT_TYPES = {"Event", "BusinessEvent", "ChildrensEvent", "ComedyEvent", "CourseInstance", "DanceEvent", "DeliveryEvent", "EducationEvent", "ExhibitionEvent", "Festival", "FoodEvent", "LiteraryEvent", "MusicEvent", "PublicationEvent", "SaleEvent", "ScreeningEvent", "SocialEvent", "SportsEvent", "TheaterEvent", "VisualArtsEvent"}


def die(message: str, code: int = 1) -> None:
    print(f"eventfinda-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def get(url_or_path: str, timeout: int = 30) -> tuple[str, str, int]:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        url = url_or_path
    else:
        url = BASE + (url_or_path if url_or_path.startswith("/") else "/" + url_or_path)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return body, resp.geturl(), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {strip_tags(raw)[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", " | ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip(" |\t\r\n")


def absolutize(url: str | None) -> str | None:
    if not url:
        return None
    return urllib.parse.urljoin(BASE, html.unescape(url))


def attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}=['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return html.unescape(m.group(1)) if m else None


def event_cards(page_html: str, limit: int) -> list[dict[str, Any]]:
    starts = [m.start() for m in re.finditer(r'<div\s+class="card\s+h-event\b', page_html, flags=re.I)]
    cards: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 9000)
        block = page_html[start:end]
        title_m = re.search(r'<h2[^>]*class="[^"]*p-summary[^"]*"[^>]*>\s*<a\s+([^>]+)>(.*?)</a>', block, flags=re.I | re.S)
        if not title_m:
            continue
        href = attr(title_m.group(1), "href")
        title = strip_tags(title_m.group(2))
        if not href or not title:
            continue
        id_m = re.search(r'_efC\(\s*\d+\s*,\s*(\d+)\s*\)', block)
        loc_m = re.search(r'<p[^>]*class="[^"]*meta-location[^"]*"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        date_title_m = re.search(r'<span\s+class="value-title"\s+title="([^"]+)"', block, flags=re.I)
        date_display_m = re.search(r'<span\s+class="value-title"\s+title="[^"]+"\s*>\s*(.*?)\s*</span>', block, flags=re.I | re.S)
        category_m = re.search(r'<span\s+class="category"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        img_m = re.search(r'<img\s+([^>]+)>', block, flags=re.I | re.S)
        badge_texts = [strip_tags(x) for x in re.findall(r'<span[^>]*class="[^"]*badge[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)]
        item = {
            "id": id_m.group(1) if id_m else None,
            "title": title,
            "url": absolutize(href),
            "path": href,
            "location": strip_tags(loc_m.group(1)) if loc_m else None,
            "start": html.unescape(date_title_m.group(1)) if date_title_m else None,
            "date_text": strip_tags(date_display_m.group(1)) if date_display_m else None,
            "category": strip_tags(category_m.group(1)) if category_m else None,
            "image": absolutize(attr(img_m.group(1), "src") or attr(img_m.group(1), "data-src")) if img_m else None,
            "badges": [b for b in badge_texts if b],
        }
        cards.append(item)
        if len(cards) >= limit:
            break
    return cards


def list_path(location: str | None, category: str | None, page: int) -> str:
    loc = (location or "new-zealand").strip("/")
    if loc in ("", "nz", "all"):
        loc = "new-zealand"
    if category:
        # Eventfinda category pages use /{category}/events/{location}, e.g.
        # /concerts-gig-guide/events/auckland rather than /whatson/{category}/...
        bits = [urllib.parse.quote(category.strip("/")), "events", urllib.parse.quote(loc)]
    else:
        bits = ["whatson", "events", urllib.parse.quote(loc)]
    path = "/" + "/".join(bits)
    if page > 1:
        path += "?page=" + str(page)
    return path


def cmd_upcoming(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    body, final_url, status = get(list_path(args.location, args.category, args.page))
    data = {
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "location": args.location or "new-zealand",
        "category": args.category,
        "page": args.page,
        "events": event_cards(body, args.limit),
    }
    emit_events(data, args.json)


def cmd_search(args: argparse.Namespace) -> None:
    if not args.query.strip():
        die("search query is required")
    started = time.perf_counter()
    qs = urllib.parse.urlencode({"q": args.query, **({"page": args.page} if args.page > 1 else {})})
    body, final_url, status = get(f"/search?{qs}")
    data = {
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "query": args.query,
        "page": args.page,
        "events": event_cards(body, args.limit),
    }
    emit_events(data, args.json)


def json_ld_objects(page_html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, flags=re.I | re.S):
        raw = html.unescape(m.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            out.extend(x for x in parsed if isinstance(x, dict))
        elif isinstance(parsed, dict):
            out.append(parsed)
    return out


def simplify_offer(offer: dict[str, Any]) -> dict[str, Any]:
    return {k: offer.get(k) for k in ("@id", "name", "price", "priceCurrency", "availability", "url") if offer.get(k) is not None}


def cmd_event(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    body, final_url, status = get(args.url_or_path)
    objs = json_ld_objects(body)
    by_id = {o.get("@id"): o for o in objs if o.get("@id")}
    places = {o.get("@id"): o for o in objs if o.get("@type") == "Place" and o.get("@id")}
    offers = {o.get("@id"): o for o in objs if o.get("@type") == "Offer" and o.get("@id")}
    events = [o for o in objs if str(o.get("@type", "")).split("/")[-1] in EVENT_TYPES or str(o.get("@type", "")).endswith("Event")]
    if not events:
        die("no event JSON-LD found on page")
    first = events[0]
    loc_ref = first.get("location") if isinstance(first.get("location"), dict) else {}
    place = places.get(loc_ref.get("@id")) or (loc_ref if isinstance(loc_ref, dict) else {})
    resolved_offers: list[dict[str, Any]] = []
    for ref in first.get("offers") or []:
        if isinstance(ref, dict) and ref.get("@id") in offers:
            resolved_offers.append(simplify_offer(offers[ref["@id"]]))
        elif isinstance(ref, dict):
            resolved_offers.append(simplify_offer(ref))
    sessions = []
    seen = set()
    for e in events:
        key = (e.get("startDate"), e.get("endDate"))
        if key in seen:
            continue
        seen.add(key)
        sessions.append({"start": e.get("startDate"), "end": e.get("endDate")})
    address = place.get("address") if isinstance(place.get("address"), dict) else {}
    event = {
        "title": first.get("name"),
        "type": first.get("@type"),
        "url": first.get("url") or final_url,
        "description": first.get("description"),
        "image": first.get("image"),
        "venue": place.get("name"),
        "venue_url": place.get("url") or place.get("@id"),
        "address": {
            "street": address.get("streetAddress"),
            "locality": address.get("addressLocality"),
            "country": address.get("addressCountry"),
        },
        "geo": place.get("geo") if isinstance(place.get("geo"), dict) else None,
        "sessions": sessions,
        "offers": resolved_offers,
    }
    data = {
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "event": event,
        "raw_json_ld": objs if args.raw else None,
    }
    emit_detail(data, args.json)


def emit_events(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    print(f"Eventfinda events: showing {len(data['events'])} from {data['source_url']} ({data['elapsed_ms']} ms)")
    print()
    for item in data["events"]:
        print(f"{item.get('title')}")
        bits = [item.get("date_text") or item.get("start"), item.get("location"), item.get("category")]
        print("  " + " | ".join(str(x) for x in bits if x))
        if item.get("badges"):
            print("  " + "; ".join(item["badges"][:3]))
        print(f"  {item.get('url')}")
        print()


def emit_detail(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    e = data["event"]
    print(e.get("title"))
    print(f"  {e.get('type')} | {e.get('venue') or ''}")
    addr = e.get("address") or {}
    addr_text = ", ".join(str(x) for x in [addr.get("street"), addr.get("locality"), addr.get("country")] if x)
    if addr_text:
        print(f"  {addr_text}")
    for s in e.get("sessions")[:8]:
        print(f"  {s.get('start')} – {s.get('end')}")
    if len(e.get("sessions") or []) > 8:
        print(f"  ... {len(e['sessions']) - 8} more sessions")
    if e.get("offers"):
        prices = [f"{o.get('name')}: ${o.get('price')}" for o in e["offers"][:5] if o.get("price")]
        if prices:
            print("  offers: " + "; ".join(prices))
    print(f"  {e.get('url') or data.get('source_url')}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Search and inspect public Eventfinda NZ event listings")
    sub = p.add_subparsers(dest="command", required=True)

    u = sub.add_parser("upcoming", help="list upcoming Eventfinda events by location/category page")
    u.add_argument("--location", default="new-zealand", help="location slug, e.g. new-zealand, auckland, wellington, christchurch")
    u.add_argument("--category", help="optional category path segment, e.g. concerts-gig-guide, festivals-lifestyle")
    u.add_argument("--page", type=int, default=1, help="one-based Eventfinda page number")
    u.add_argument("--limit", type=int, default=10, help="max event cards to emit")
    u.add_argument("--json", action="store_true", help="emit JSON")
    u.set_defaults(func=cmd_upcoming)

    s = sub.add_parser("search", help="search public Eventfinda pages")
    s.add_argument("query", help="search text")
    s.add_argument("--page", type=int, default=1, help="one-based Eventfinda page number")
    s.add_argument("--limit", type=int, default=10, help="max event cards to emit")
    s.add_argument("--json", action="store_true", help="emit JSON")
    s.set_defaults(func=cmd_search)

    e = sub.add_parser("event", help="inspect an event detail page URL/path using JSON-LD")
    e.add_argument("url_or_path", help="Eventfinda event URL or path")
    e.add_argument("--json", action="store_true", help="emit JSON")
    e.add_argument("--raw", action="store_true", help="include raw JSON-LD objects in JSON output")
    e.set_defaults(func=cmd_event)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "limit"):
        args.limit = min(max(1, args.limit), 50)
    if hasattr(args, "page"):
        args.page = max(1, args.page)
    args.func(args)


if __name__ == "__main__":
    main()
