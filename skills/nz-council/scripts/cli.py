#!/usr/bin/env python3
"""Read-only NZ council events and recreation lookup CLI.

This is intentionally stdlib-only. It reads public pages and public JSON-like
attributes exposed by council/event websites; it never logs in, books, pays, or
submits forms.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

EVENTFINDA_BASE = "https://www.eventfinda.co.nz"
AKL_LEISURE_BASE = "https://www.aucklandleisure.co.nz"
AKL_LOCATION_ENDPOINT = AKL_LEISURE_BASE + "/umbraco/surface/LocationListing/RenderLocationListing"
WLG_BASE = "https://wellington.govt.nz"
ROT_BASE = "https://www.rotorualakescouncil.nz"
ROT_AQUATIC_BASE = "https://www.clmnz.co.nz/rotorua-aquatic-centre"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146 Safari/537.36"

COUNCIL_LOCATIONS = {
    "akl": "auckland",
    "wlg": "wellington",
    "chc": "christchurch",
    "rot": "rotorua",
}

COUNCIL_NAMES = {
    "akl": "Auckland",
    "wlg": "Wellington",
    "chc": "Christchurch",
    "rot": "Rotorua Lakes",
}

AKL_AREA_IDS = {
    "central": "1134",
    "east": "1138",
    "north": "1141",
    "south": "1144",
    "west": "1147",
}

AKL_FACILITY_IDS = {
    "pool": "1126",
    "gym": "1119",
}

ROT_RECREATION_SOURCE_URL = ROT_BASE + "/parks-lakes-recreation"
ROT_PARK_RESERVES_SOURCE_URL = ROT_BASE + "/parks-lakes-recreation/park-reserves"
ROT_FACILITIES: list[dict[str, Any]] = [
    {
        "name": "Rotorua Aquatic Centre",
        "id": "rotorua-aquatic-centre",
        "type": "pool",
        "facility_types": ["pool", "gym", "leisure-centre"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/recreational-venues/aquatic-centre",
        "operator_source_url": ROT_AQUATIC_BASE + "/",
        "pools_source_url": ROT_AQUATIC_BASE + "/pools/",
        "contact_source_url": ROT_AQUATIC_BASE + "/contact/",
        "listing_source_url": ROT_RECREATION_SOURCE_URL,
        "address": "Kuirau Park, 18 Tarewa Rd, Rotorua 3010",
        "operator": "Community Leisure Management (CLM)",
        "status": None,
        "description": (
            "Main Rotorua aquatic centre for aquatic sports, recreation, health, fitness, "
            "leisure programmes, swimming lessons, and community use."
        ),
        "hours": [{"label": "Opening hours", "text": "Monday - Sunday: 6:00am - 9:00pm"}],
        "hours_summary": "Monday - Sunday: 6:00am - 9:00pm",
        "phone": "07 348 8833",
        "email": "racr@clmnz.co.nz",
        "features": [
            "Outdoor 50m heated pool",
            "Indoor 25m heated pool",
            "Indoor learner pool",
            "Gym",
            "Fitness classes",
            "Swim programmes",
            "Birthday party spaces",
        ],
        "availability_urls": [
            {
                "label": "Outdoor Pool Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/6935ad313",
            },
            {
                "label": "Indoor Pool Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/d905956020",
            },
        ],
        "hours_note": "Use the linked operator pages for live lane availability and programme changes.",
    },
    {
        "name": "Butcher's Pool",
        "id": "butchers-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/park-reserves/butchers-pool",
        "listing_source_url": ROT_PARK_RESERVES_SOURCE_URL,
        "address": "Broadlands Road, 1.8km south of Reporoa Village",
        "operator": "Rotorua Lakes Council",
        "status": "Unsupervised",
        "description": "Free hot mineral pool with mineral water piped from an adjacent spring.",
        "hours": None,
        "hours_summary": None,
        "hours_note": "Free public hot mineral pool; no opening hours are published on the council page.",
        "phone": None,
        "email": None,
        "features": ["Hot mineral pool", "Changing rooms", "Toilets"],
        "safety_notes": [
            "Keep your head above water to avoid amoebic meningitis risk.",
            "Pool is unsupervised.",
        ],
    },
    {
        "name": "Kuirau Park foot pools and paddling pool",
        "id": "kuirau-park-foot-pools-paddling-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/park-reserves/kuirau-park",
        "listing_source_url": ROT_PARK_RESERVES_SOURCE_URL,
        "address": "Corner of Ranolf Street and Lake Road, Rotorua",
        "operator": "Rotorua Lakes Council",
        "status": None,
        "description": "Public park facilities include geothermal foot pools and a paddling pool.",
        "hours": None,
        "hours_summary": None,
        "hours_note": "Park page lists facilities but not pool opening hours; stay on tracks around geothermal features.",
        "phone": None,
        "email": None,
        "features": ["Foot pools", "Paddling pool", "BBQs", "Picnic tables", "Playground", "Public toilets"],
    },
]

EVENT_TYPES = {
    "Event",
    "BusinessEvent",
    "ChildrensEvent",
    "ComedyEvent",
    "CourseInstance",
    "DanceEvent",
    "DeliveryEvent",
    "EducationEvent",
    "ExhibitionEvent",
    "Festival",
    "FoodEvent",
    "LiteraryEvent",
    "MusicEvent",
    "PublicationEvent",
    "SaleEvent",
    "ScreeningEvent",
    "SocialEvent",
    "SportsEvent",
    "TheaterEvent",
    "VisualArtsEvent",
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-council: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_text(url_or_path: str, base: str = "", headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[str, str, int]:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        url = url_or_path
    elif base:
        url = urllib.parse.urljoin(base, url_or_path)
    else:
        die(f"relative URL without base: {url_or_path}")

    req_headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return body, resp.geturl(), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        message = strip_tags(raw)[:240] or e.reason
        die(f"HTTP {e.code} from {url}: {message}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def strip_tags(value: str, br: str = " ") -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", br, value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip(" |;\t\r\n")


def attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}=['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return html.unescape(m.group(1)) if m else None


def absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return None
    return urllib.parse.urljoin(base, html.unescape(url))


def slug_text(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_date_arg(value: str | None, label: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        die(f"{label} must be an ISO date like 2026-05-24")


def parse_event_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    cleaned = value.strip()
    # Eventfinda often uses +1200; fromisoformat expects +12:00.
    cleaned = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", cleaned)
    try:
        return dt.datetime.fromisoformat(cleaned).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(cleaned[:10])
        except ValueError:
            return None


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


def eventfinda_list_path(council: str | None, category: str | None, page: int) -> str:
    location = COUNCIL_LOCATIONS.get(council or "", "new-zealand")
    if category:
        bits = [urllib.parse.quote(category.strip("/")), "events", urllib.parse.quote(location)]
    else:
        bits = ["whatson", "events", urllib.parse.quote(location)]
    path = "/" + "/".join(bits)
    if page > 1:
        path += "?page=" + str(page)
    return path


def eventfinda_cards(page_html: str) -> list[dict[str, Any]]:
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
        cards.append(
            {
                "id": href,
                "eventfinda_id": id_m.group(1) if id_m else None,
                "title": title,
                "url": absolutize(href, EVENTFINDA_BASE),
                "location": strip_tags(loc_m.group(1)) if loc_m else None,
                "start": html.unescape(date_title_m.group(1)) if date_title_m else None,
                "date_text": strip_tags(date_display_m.group(1)) if date_display_m else None,
                "category": strip_tags(category_m.group(1)) if category_m else None,
                "image": absolutize(attr(img_m.group(1), "src") or attr(img_m.group(1), "data-src"), EVENTFINDA_BASE) if img_m else None,
                "badges": [b for b in badge_texts if b],
                "source": "eventfinda",
            }
        )
    return cards


def cmd_events(args: argparse.Namespace) -> None:
    date_from = parse_date_arg(args.date_from, "--from")
    date_to = parse_date_arg(args.date_to, "--to")
    if date_from and date_to and date_to < date_from:
        die("--to must be on or after --from")

    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    source_urls: list[str] = []
    max_pages = 8 if (date_from or date_to or args.free) else 1
    for page in range(1, max_pages + 1):
        body, final_url, _ = fetch_text(eventfinda_list_path(args.council, args.category, page), EVENTFINDA_BASE)
        source_urls.append(final_url)
        page_cards = eventfinda_cards(body)
        if not page_cards:
            break
        for item in page_cards:
            event_date = parse_event_date(item.get("start"))
            if date_from and (not event_date or event_date < date_from):
                continue
            if date_to and (not event_date or event_date > date_to):
                continue
            if args.free:
                haystack = " ".join(
                    str(x or "")
                    for x in [item.get("title"), item.get("category"), item.get("location"), " ".join(item.get("badges") or [])]
                ).lower()
                if "free" not in haystack:
                    continue
            item["council"] = args.council
            item["council_name"] = COUNCIL_NAMES.get(args.council or "", "NZ")
            events.append(item)
            if len(events) >= args.limit:
                break
        if len(events) >= args.limit:
            break

    data = {
        "query": {
            "council": args.council,
            "council_name": COUNCIL_NAMES.get(args.council or "", "NZ"),
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
            "category": args.category,
            "free": args.free,
            "limit": args.limit,
        },
        "source": "eventfinda-public-pages",
        "source_urls": source_urls,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "events": events,
    }
    emit_event_list(data, args.json)


def simplify_offer(offer: dict[str, Any]) -> dict[str, Any]:
    return {k: offer.get(k) for k in ("@id", "name", "price", "priceCurrency", "availability", "url") if offer.get(k) is not None}


def cmd_event(args: argparse.Namespace) -> None:
    if re.fullmatch(r"\d+", args.id_or_url):
        die("event id must be a URL or path from `events --json`; numeric Eventfinda ids are not stable enough by themselves")

    started = time.perf_counter()
    body, final_url, status = fetch_text(args.id_or_url, EVENTFINDA_BASE)
    objs = json_ld_objects(body)
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

    sessions: list[dict[str, Any]] = []
    seen = set()
    for event_obj in events:
        key = (event_obj.get("startDate"), event_obj.get("endDate"))
        if key in seen:
            continue
        seen.add(key)
        sessions.append({"start": event_obj.get("startDate"), "end": event_obj.get("endDate")})

    address = place.get("address") if isinstance(place.get("address"), dict) else {}
    data = {
        "source": "eventfinda-public-pages",
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "event": {
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
        },
    }
    emit_event_detail(data, args.json)


def akl_location_listing(kind: str | None = None, region: str | None = None) -> tuple[list[dict[str, Any]], str]:
    params: dict[str, str] = {}
    if kind in AKL_FACILITY_IDS:
        params["facilitiesFilters"] = AKL_FACILITY_IDS[kind]
    if region:
        if region not in AKL_AREA_IDS:
            die(f"unknown Auckland region {region!r}; use one of: {', '.join(sorted(AKL_AREA_IDS))}")
        params["areaFilters"] = AKL_AREA_IDS[region]
    url = AKL_LOCATION_ENDPOINT
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body, final_url, _ = fetch_text(
        url,
        AKL_LEISURE_BASE,
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": AKL_LEISURE_BASE + "/locations/"},
    )
    cards = parse_akl_location_cards(body, final_url)
    if kind == "leisure-centre":
        cards = [c for c in cards if "leisure" in c["name"].lower() or "recreation" in c["name"].lower()]
    elif kind == "library":
        cards = [c for c in cards if "library" in c["name"].lower()]
    return cards, final_url


def parse_akl_location_cards(page_html: str, source_url: str) -> list[dict[str, Any]]:
    starts = [m.start() for m in re.finditer(r'<div\s+class="card\s+card-shadow"', page_html, flags=re.I)]
    cards: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 9000)
        block = page_html[start:end]
        title_m = re.search(r'<h3[^>]*class="[^"]*card-title[^"]*"[^>]*>(.*?)</h3>', block, flags=re.I | re.S)
        link_m = re.search(r'<a\s+([^>]*class="[^"]*card-inner-wrap[^"]*"[^>]*)>', block, flags=re.I | re.S)
        if not title_m or not link_m:
            continue
        name = strip_tags(title_m.group(1))
        href = attr(link_m.group(1), "href")
        if not name or not href:
            continue
        paragraphs = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)]
        address = next((p for p in paragraphs if p and "View on map" not in p and "Operated by" not in p), None)
        operator = next((p.replace("Operated by ", "") for p in paragraphs if p.startswith("Operated by ")), None)
        status = None
        footer_m = re.search(r'<div[^>]*class="[^"]*card-footer[^"]*"[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        if footer_m:
            status = strip_tags(footer_m.group(1)) or None
        map_m = re.search(r'\bdata-target="([^"]+)"', block, flags=re.I)
        image_m = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", block, flags=re.I)
        cards.append(
            {
                "name": name,
                "id": slug_text(name),
                "council": "akl",
                "council_name": "Auckland",
                "source": "aucklandleisure",
                "source_url": absolutize(href, AKL_LEISURE_BASE),
                "listing_source_url": source_url,
                "address": address,
                "operator": operator,
                "status": status,
                "map_id": map_m.group(1) if map_m else None,
                "image": absolutize(image_m.group(1), AKL_LEISURE_BASE) if image_m else None,
            }
        )
    return cards


def text_between(page_html: str, start_pattern: str, end_patterns: list[str]) -> str:
    start = re.search(start_pattern, page_html, flags=re.I | re.S)
    if not start:
        return ""
    start_pos = start.end()
    end_pos = len(page_html)
    for pat in end_patterns:
        end = re.search(pat, page_html[start_pos:], flags=re.I | re.S)
        if end:
            end_pos = min(end_pos, start_pos + end.start())
    return page_html[start_pos:end_pos]


def parse_akl_detail(page_html: str, final_url: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    meta_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', page_html, flags=re.I)
    name = strip_tags(title_m.group(1)) if title_m else (card or {}).get("name")
    hours_section = text_between(page_html, r"<h3[^>]*>\s*Hours\s*</h3>", [r"<h3[^>]*>\s*Address\s*</h3>", r"<h3[^>]*>\s*Contact"])
    hours: list[dict[str, str]] = []
    for m in re.finditer(r'<h4[^>]*class="[^"]*page-link-with-description-title[^"]*"[^>]*>(.*?)</h4>\s*<p[^>]*>(.*?)</p>', hours_section, flags=re.I | re.S):
        label = strip_tags(m.group(1))
        text = strip_tags(m.group(2), br="; ")
        if label and text:
            hours.append({"label": label, "text": text})

    address = (card or {}).get("address")
    address_section = text_between(page_html, r"<h3[^>]*>\s*Address\s*</h3>", [r"<h3[^>]*>\s*Contact"])
    address_m = re.search(r"<p[^>]*>(.*?)</p>", address_section, flags=re.I | re.S)
    if address_m:
        parsed_address = strip_tags(address_m.group(1), br=", ")
        if parsed_address:
            address = parsed_address

    phones = [html.unescape(x).strip() for x in re.findall(r'href=["\']tel:([^"\']+)', page_html, flags=re.I)]
    emails = [html.unescape(x).strip() for x in re.findall(r'href=["\']mailto:([^"?\']+)', page_html, flags=re.I)]
    availability_m = re.search(r'href=["\'](https://portal\.aucklandleisure\.co\.nz/ResourceAvailability/\d+)["\']', page_html, flags=re.I)
    group_fitness_m = re.search(r'href=["\'](https://portal\.aucklandleisure\.co\.nz/Group\?[^"\']+)["\']', page_html, flags=re.I)

    feature_titles: list[str] = []
    pools_section = text_between(page_html, r'id=["\']collapsepools["\']', [r'id=["\']collapsegym["\']', r'id=["\']collapsegroup-fitness["\']', r'id=["\']collapsevenue-hire["\']'])
    noisy_feature_words = ("pdf download", "terms and conditions", "safe use", "what level", "how to enrol")
    for raw in re.findall(r'class=["\'][^"\']*card-title[^"\']*["\'][^>]*>(.*?)</h[34]>', pools_section or page_html, flags=re.I | re.S):
        title = strip_tags(raw)
        title_l = title.lower()
        if any(word in title_l for word in noisy_feature_words):
            continue
        if title and title not in feature_titles and title.lower() != (name or "").lower():
            feature_titles.append(title)

    return {
        "name": name,
        "id": slug_text(name or ""),
        "council": "akl",
        "council_name": "Auckland",
        "source": "aucklandleisure",
        "source_url": final_url,
        "description": html.unescape(meta_m.group(1)).strip() if meta_m else None,
        "address": address,
        "operator": (card or {}).get("operator"),
        "status": (card or {}).get("status") or None,
        "hours": hours,
        "hours_summary": hours[0]["text"] if hours else None,
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "features": feature_titles[:20],
        "resource_availability_url": availability_m.group(1) if availability_m else None,
        "group_fitness_url": html.unescape(group_fitness_m.group(1)) if group_fitness_m else None,
    }


def enrich_akl_hours(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def one(card: dict[str, Any]) -> dict[str, Any]:
        try:
            body, final_url, _ = fetch_text(card["source_url"], AKL_LEISURE_BASE)
            detail = parse_akl_detail(body, final_url, card)
            card["hours"] = detail.get("hours")
            card["hours_summary"] = detail.get("hours_summary")
            card["phone"] = detail.get("phone")
            card["email"] = detail.get("email")
            card["resource_availability_url"] = detail.get("resource_availability_url")
        except SystemExit as exc:
            card["detail_error"] = str(exc)
        return card

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, dict(card)): idx for idx, card in enumerate(cards)}
        out: list[dict[str, Any] | None] = [None] * len(cards)
        for future in concurrent.futures.as_completed(futures):
            out[futures[future]] = future.result()
    return [x for x in out if x is not None]


def fetch_wlg_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind == "pool":
        path = "/recreation/facilities-and-centres/swimming-pools"
        facility_type = "pool"
    elif kind == "leisure-centre":
        path = "/recreation/facilities-and-centres/recreation-centres"
        facility_type = "leisure-centre"
    else:
        return [], WLG_BASE
    body, final_url, _ = fetch_text(path, WLG_BASE)
    facilities: list[dict[str, Any]] = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", body, flags=re.I | re.S):
        tag, block = m.group(1), m.group(2)
        if "link-block" not in tag:
            continue
        title_m = re.search(r'<h2[^>]*class="[^"]*link-block__title[^"]*"[^>]*>(.*?)</h2>', block, flags=re.I | re.S)
        if not title_m:
            continue
        title = strip_tags(title_m.group(1))
        href = attr(tag, "href")
        if not title or not href:
            continue
        title_l = title.lower()
        if any(word in title_l for word in ("lessons", "classes", "rules", "membership")):
            continue
        if kind == "pool" and "pool" not in title_l and "aquatic centre" not in title_l:
            continue
        if kind == "leisure-centre" and "recreation centre" not in title_l:
            continue
        desc_m = re.search(r'<p[^>]*class="[^"]*link-block__content[^"]*"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        facilities.append(
            {
                "name": title,
                "id": slug_text(title),
                "type": facility_type,
                "council": "wlg",
                "council_name": "Wellington",
                "source": "wellington-city-council",
                "source_url": absolutize(href, WLG_BASE),
                "listing_source_url": final_url,
                "description": strip_tags(desc_m.group(1)) if desc_m else None,
                "hours": None,
                "hours_note": "Open times are published on the linked Wellington City Council detail page; v1 only lists WCC facilities.",
            }
        )
    return facilities, final_url


def fetch_rot_facilities(kind: str | None = "pool") -> tuple[list[dict[str, Any]], str]:
    facilities: list[dict[str, Any]] = []
    for facility in ROT_FACILITIES:
        if kind and kind not in facility.get("facility_types", []):
            continue
        facilities.append(dict(facility))
    return facilities, ROT_RECREATION_SOURCE_URL


def parse_time_label(value: str) -> dt.datetime | None:
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def add_minutes(label: str, minutes: int) -> str:
    parsed = parse_time_label(label)
    if not parsed:
        return label
    return (parsed + dt.timedelta(minutes=minutes)).strftime("%-I:%M %p")


def parse_akl_availability(url: str) -> dict[str, Any]:
    body, final_url, _ = fetch_text(url, AKL_LEISURE_BASE)
    items_m = re.search(r':items="([^"]+)"', body, flags=re.I | re.S)
    dates_m = re.search(r':date-strings="([^"]+)"', body, flags=re.I | re.S)
    if not items_m or not dates_m:
        return {"source_url": final_url, "date": None, "resources": [], "note": "No public availability payload found."}
    try:
        items = json.loads(html.unescape(items_m.group(1)))
        dates = json.loads(html.unescape(dates_m.group(1)))
    except json.JSONDecodeError as exc:
        return {"source_url": final_url, "date": None, "resources": [], "note": f"Could not parse availability payload: {exc}"}
    if not isinstance(items, dict) or not isinstance(dates, list) or not dates:
        return {"source_url": final_url, "date": None, "resources": [], "note": "Availability payload had an unexpected shape."}

    # The portal returns a rolling window with the local-current day first.
    date_index = 0
    date_value = dates[date_index]
    resources: list[dict[str, Any]] = []
    for resource_name, periods in items.items():
        slots: list[tuple[dt.datetime, str, int]] = []
        if not isinstance(periods, dict):
            continue
        for period_slots in periods.values():
            if not isinstance(period_slots, dict):
                continue
            for time_label, values in period_slots.items():
                if not isinstance(values, list) or date_index >= len(values):
                    continue
                lanes = values[date_index]
                if not isinstance(lanes, int) or lanes <= 0:
                    continue
                parsed_time = parse_time_label(time_label)
                if parsed_time:
                    slots.append((parsed_time, time_label, lanes))
        slots.sort(key=lambda x: x[0])
        intervals: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        previous_time: dt.datetime | None = None
        previous_label: str | None = None
        for parsed_time, label, lanes in slots:
            contiguous = previous_time is not None and parsed_time - previous_time == dt.timedelta(minutes=15)
            if current and contiguous and current["available_lanes"] == lanes:
                current["end"] = add_minutes(label, 15)
            else:
                if current:
                    intervals.append(current)
                current = {"start": label, "end": add_minutes(label, 15), "available_lanes": lanes}
            previous_time = parsed_time
            previous_label = label
        if current:
            intervals.append(current)
        resources.append({"name": resource_name, "intervals": intervals})
    retrieved_m = re.search(r'<time[^>]*datetime="([^"]+)"[^>]*>(.*?)</time>', body, flags=re.I | re.S)
    return {
        "source_url": final_url,
        "date": date_value,
        "retrieved": html.unescape(retrieved_m.group(1)) if retrieved_m else None,
        "resources": resources,
    }


def find_facility(cards: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    needle = slug_text(query)
    exact = [c for c in cards if c.get("id") == needle]
    if exact:
        return exact[0]
    contains = [c for c in cards if needle in c.get("id", "") or c.get("id", "") in needle]
    return contains[0] if contains else None


def cmd_pools(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    if args.council == "akl":
        pools, source_url = akl_location_listing("pool", args.region)
        pools = pools[: args.limit]
        pools = enrich_akl_hours(pools)
    elif args.council == "wlg":
        pools, source_url = fetch_wlg_facilities("pool")
        if args.region:
            die("--region is only supported for Auckland pools")
        pools = pools[: args.limit]
    elif args.council == "rot":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_rot_facilities("pool")
        pools = pools[: args.limit]
    else:
        die("Christchurch pools are not wired in v1 because the public council recreation source is JS/vendor-backed")

    data = {
        "query": {"council": args.council, "region": args.region, "limit": args.limit},
        "source_url": source_url,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "pools": pools,
    }
    emit_facility_list(data, "pools", args.json)


def pool_detail_for_council(council: str, name: str, started: float) -> tuple[dict[str, Any] | None, str | None]:
    if council == "akl":
        cards, listing_url = akl_location_listing("pool", None)
        card = find_facility(cards, name)
        if not card:
            suggestions = ", ".join(c["name"] for c in cards[:10])
            return None, f"Auckland: {suggestions}"
        body, final_url, _ = fetch_text(card["source_url"], AKL_LEISURE_BASE)
        facility = parse_akl_detail(body, final_url, card)
        availability = None
        if facility.get("resource_availability_url"):
            availability = parse_akl_availability(facility["resource_availability_url"])
        return {
            "query": {"council": council, "name": name},
            "listing_source_url": listing_url,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "facility": facility,
            "lane_availability_today": availability,
        }, None
    if council == "wlg":
        cards, listing_url = fetch_wlg_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            suggestions = ", ".join(c["name"] for c in cards[:10])
            return None, f"Wellington: {suggestions}"
        return {
            "query": {"council": council, "name": name},
            "listing_source_url": listing_url,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "facility": card,
            "lane_availability_today": None,
        }, None
    if council == "rot":
        cards, listing_url = fetch_rot_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            suggestions = ", ".join(c["name"] for c in cards[:10])
            return None, f"Rotorua Lakes: {suggestions}"
        return {
            "query": {"council": council, "name": name},
            "listing_source_url": listing_url,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "facility": card,
            "lane_availability_today": None,
        }, None
    die("Christchurch pool detail is not wired in v1")


def cmd_pool(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    councils = [args.council] if args.council else ["rot", "akl", "wlg"]
    misses: list[str] = []
    for council in councils:
        data, miss = pool_detail_for_council(council, args.name, started)
        if data:
            emit_pool_detail(data, args.json)
            return
        if miss:
            misses.append(miss)
    if args.council:
        council_name = COUNCIL_NAMES.get(args.council, args.council)
        suggestion = misses[0] if misses else "no suggestions available"
        die(f"no {council_name} pool matched {args.name!r}. Try one of: {suggestion}")
    suggestion_text = " | ".join(misses) if misses else "use --council akl, wlg, or rot"
    die(f"no pool matched {args.name!r}. Try one of: {suggestion_text}")


def cmd_facilities(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    if args.council == "akl":
        lookup_type = args.type
        cards, source_url = akl_location_listing(lookup_type if lookup_type in ("pool", "gym", "leisure-centre", "library") else None, args.region)
        facilities = cards[: args.limit]
        note = None
        if args.type == "library":
            note = "Auckland Leisure does not list libraries; v1 is scoped to recreation facilities."
    elif args.council == "wlg":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "gym":
            facilities, source_url = [], WLG_BASE
            note = "Wellington gym listings are not wired in v1."
        elif args.type == "library":
            facilities, source_url = [], WLG_BASE
            note = "Libraries are outside this skill's recreation-focused v1 data source."
        else:
            facilities, source_url = fetch_wlg_facilities(args.type)
            note = None
        facilities = facilities[: args.limit]
    elif args.council == "rot":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "library":
            facilities, source_url = [], ROT_RECREATION_SOURCE_URL
            note = "Libraries are outside this skill's recreation-focused v1 data source."
        else:
            facilities, source_url = fetch_rot_facilities(args.type)
            note = None
            if args.type == "gym":
                note = "Rotorua Aquatic Centre includes a gym; linked operator pages have current programme details."
        facilities = facilities[: args.limit]
    else:
        facilities, source_url = [], "https://recandsport.ccc.govt.nz/"
        note = "Christchurch recreation uses a vendor-backed source that is documented in references but not wired in v1."

    data = {
        "query": {"council": args.council, "type": args.type, "region": args.region, "limit": args.limit},
        "source_url": source_url,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "note": note,
        "facilities": facilities,
    }
    emit_facility_list(data, "facilities", args.json)


def emit_event_list(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    print(f"Events: showing {len(data['events'])} from {data['source']} ({data['elapsed_ms']} ms)")
    for source_url in data["source_urls"][:3]:
        print(f"Source: {source_url}")
    print()
    for item in data["events"]:
        print(item.get("title"))
        bits = [item.get("date_text") or item.get("start"), item.get("location"), item.get("category")]
        print("  " + " | ".join(str(x) for x in bits if x))
        if item.get("badges"):
            print("  " + "; ".join(item["badges"][:3]))
        print(f"  id: {item.get('id')}")
        print(f"  {item.get('url')}")
        print()


def emit_event_detail(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    event = data["event"]
    print(event.get("title"))
    print(f"  {event.get('venue') or ''}")
    address = event.get("address") or {}
    address_text = ", ".join(str(x) for x in [address.get("street"), address.get("locality"), address.get("country")] if x)
    if address_text:
        print(f"  {address_text}")
    for session in event.get("sessions", [])[:8]:
        print(f"  {session.get('start')} - {session.get('end')}")
    if event.get("offers"):
        prices = [f"{o.get('name')}: ${o.get('price')}" for o in event["offers"][:5] if o.get("price")]
        if prices:
            print("  " + "; ".join(prices))
    print(f"  {event.get('url') or data.get('source_url')}")


def emit_facility_list(data: dict[str, Any], key: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    rows = data[key]
    print(f"{key.title()}: showing {len(rows)} ({data['elapsed_ms']} ms)")
    print(f"Source: {data.get('source_url')}")
    if data.get("note"):
        print(f"Note: {data['note']}")
    print()
    for item in rows:
        print(item.get("name"))
        bits = [item.get("address"), item.get("hours_summary") or item.get("hours_note"), item.get("status")]
        for bit in bits:
            if bit:
                print(f"  {bit}")
        print(f"  {item.get('source_url')}")
        print()


def emit_pool_detail(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    facility = data["facility"]
    print(facility.get("name"))
    for bit in [facility.get("address"), facility.get("hours_summary"), facility.get("phone"), facility.get("email")]:
        if bit:
            print(f"  {bit}")
    if facility.get("features"):
        print("  features: " + ", ".join(facility["features"][:10]))
    availability = data.get("lane_availability_today")
    if availability and availability.get("resources"):
        print(f"  lane availability date: {availability.get('date')}")
        for resource in availability["resources"][:3]:
            intervals = resource.get("intervals") or []
            if intervals:
                first = intervals[0]
                print(f"  {resource['name']}: {first['start']}-{first['end']} ({first['available_lanes']} lanes)")
    print(f"  {facility.get('source_url')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only NZ council events, pools, and recreation facilities")
    sub = parser.add_subparsers(dest="command", required=True)

    events = sub.add_parser("events", help="list council-area public events")
    events.add_argument("--council", choices=sorted(COUNCIL_LOCATIONS), help="council area: akl, wlg, chc, or rot")
    events.add_argument("--from", dest="date_from", help="start date filter, ISO yyyy-mm-dd")
    events.add_argument("--to", dest="date_to", help="end date filter, ISO yyyy-mm-dd")
    events.add_argument("--category", help="Eventfinda category slug, e.g. concerts-gig-guide")
    events.add_argument("--free", action="store_true", help="only include events with a visible free badge/text match")
    events.add_argument("--limit", type=int, default=10, help="maximum events to emit")
    events.add_argument("--json", action="store_true", help="emit JSON")
    events.set_defaults(func=cmd_events)

    event = sub.add_parser("event", help="show one event detail from an Eventfinda URL/path id")
    event.add_argument("id_or_url", help="event id/path from events output, or a full Eventfinda event URL")
    event.add_argument("--json", action="store_true", help="emit JSON")
    event.set_defaults(func=cmd_event)

    pools = sub.add_parser("pools", help="list public pools with available hours where supported")
    pools.add_argument("--council", choices=["akl", "wlg", "chc", "rot"], default="akl", help="council recreation source")
    pools.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    pools.add_argument("--limit", type=int, default=50, help="maximum pools to emit")
    pools.add_argument("--json", action="store_true", help="emit JSON")
    pools.set_defaults(func=cmd_pools)

    pool = sub.add_parser("pool", help="show one pool detail and lane availability where supported")
    pool.add_argument("name", help="pool name or slug, e.g. Tepid Baths")
    pool.add_argument("--council", choices=["akl", "wlg", "chc", "rot"], help="council recreation source; default searches supported pool sources")
    pool.add_argument("--json", action="store_true", help="emit JSON")
    pool.set_defaults(func=cmd_pool)

    facilities = sub.add_parser("facilities", help="list recreation facilities")
    facilities.add_argument("--council", choices=["akl", "wlg", "chc", "rot"], default="akl", help="council recreation source")
    facilities.add_argument("--type", choices=["pool", "gym", "leisure-centre", "library"], default="pool", help="facility type")
    facilities.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    facilities.add_argument("--limit", type=int, default=50, help="maximum facilities to emit")
    facilities.add_argument("--json", action="store_true", help="emit JSON")
    facilities.set_defaults(func=cmd_facilities)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "limit"):
        args.limit = min(max(1, args.limit), 100)
    args.func(args)


if __name__ == "__main__":
    main()
