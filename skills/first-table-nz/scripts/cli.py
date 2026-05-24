#!/usr/bin/env python3
"""First Table NZ public read-only restaurant/deal lookup CLI.

Uses the public First Table website SSR JSON and unauthenticated GraphQL calls
observed from the browser frontend. Read-only: no login, cart, booking, payment,
or account actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SITE = "https://www.firsttable.co.nz"
GRAPHQL_URL = "https://stellate.firsttable.net/graphql"
USER_AGENT = "Mozilla/5.0 (compatible; thecolab-first-table-nz-skill/1.0)"
DEFAULT_CITY = "auckland"
DEFAULT_PEOPLE = 2

CITY_HINTS = [
    "auckland", "wellington", "christchurch", "queenstown-lakes", "wanaka",
    "waikato", "bay-of-plenty", "hawkes-bay", "nelson", "northland",
    "whangarei", "rotorua", "taupo", "taranaki", "otago", "canterbury",
    "manawatu", "wairarapa", "marlborough", "southland", "west-coast",
    "kapiti-coast", "gisborne", "ohakune", "whanganui", "timaru-district",
]

ALL_RESTAURANT_IDS_QUERY = """
query AllRestaurantIds(
  $regionId: Int
  $suburbs: [Int]
  $tags: [Int]
  $sort: RestaurantSortTypes
  $sessions: [SessionTypes]
  $dates: [String]
  $nearTo: NearToInput
  $ids: [Int]
  $sortSeed: String
  $offersSession: [SessionTypes]
  $offersFirstTableSession: [SessionTypes]
  $people: Int
) {
  allRestaurants(
    input: {
      prioritiseByAvailability: { forSession: $sessions, onDate: $dates }
      status: [LIVE, ON_HOLD]
      regionId: $regionId
      suburbs: $suburbs
      tags: $tags
      sort: $sort
      nearTo: $nearTo
      id: $ids
      sortSeed: $sortSeed
      offersSession: $offersSession
      offersFirstTableSession: $offersFirstTableSession
      people: $people
    }
  ) { id __typename }
}
"""

RESTAURANT_DETAILS_QUERY = """
query RestaurantDetails($id: Int!) {
  Restaurant(id: $id) {
    __typename
    id
    title
    menuTitle
    rating
    approvedReviewsCount
    reviewSummary
    offersFirstTable
    offersRegularTable
    slug
    lat
    lng
    minDiners
    maxDiners
    dinerOptions
    firstTableSessionTypes
    regularTableSessionTypes
    sessionTypes
    bookingPricesBySession {
      title
      price
      rrp
      isSpecial
      dinerPrices { pax price rrp }
    }
    region { id menuTitle slug }
    suburb { id menuTitle slug }
    tags { nodes { id title category } }
    cuisines { edges { node { id title } } }
    images { edges { node { url } } }
    specialConditions
    isNew
    featuredText
  }
}
"""

AVAILABILITY_QUERY = """
fragment AvailabilitySearchFragment on AvailabilitySearch {
  __typename
  id
  restaurantId
  available
  dataStatus
  syncExpires
  availableTimes {
    __typename
    time
    date
    session
    available
    cutOffTime
    leaveTime
    options
    deal
    dealDescription
  }
}
query AllAvailabilitySearch($restaurantIds: [Int]!, $date: String!, $people: Int!) {
  allAvailabilitySearch(restaurantIds: $restaurantIds, date: $date, people: $people) {
    ...AvailabilitySearchFragment
  }
}
"""


def die(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def http_json_or_text(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[Any, str, int]:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            text = body.decode("utf-8", "replace")
            ctype = response.headers.get("content-type", "")
            if "json" in ctype:
                return json.loads(text), text, response.status
            return None, text, response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        die(f"HTTP {exc.code} for {url}: {detail}")
    except urllib.error.URLError as exc:
        die(f"network error for {url}: {exc.reason}")
    raise AssertionError("unreachable")


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    data, text, _ = http_json_or_text(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "stage": "Live",
            "origin": SITE + "/",
            "referer": SITE + "/",
            "x-graphql-client-name": "Website",
            "x-graphql-client-version": SITE + "/",
        },
    )
    if data is None:
        die(f"GraphQL returned non-JSON response: {text[:200]}")
    assert data is not None
    if data.get("errors") and not data.get("data"):
        die("GraphQL error: " + "; ".join(e.get("message", str(e)) for e in data["errors"]))
    return data.get("data") or {}


def city_slug(value: str) -> str:
    value = (value or DEFAULT_CITY).strip().strip("/")
    if value.startswith("http"):
        parsed = urllib.parse.urlparse(value)
        value = parsed.path.strip("/")
    return value or DEFAULT_CITY


def page_url(slug: str) -> str:
    return SITE + "/" + city_slug(slug)


def next_data(url: str) -> dict[str, Any]:
    _, text, _ = http_json_or_text(url)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        die(f"could not find __NEXT_DATA__ on {url}")
    assert match is not None
    return json.loads(html.unescape(match.group(1)))


def city_page(slug: str) -> dict[str, Any]:
    data = next_data(page_url(slug))
    page = data.get("props", {}).get("pageProps", {}).get("page") or {}
    if page.get("className") != "City" and page.get("__typename") != "City":
        die(f"{slug!r} did not resolve to a First Table city/region page")
    return page


def simple_city(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": page.get("id"),
        "title": page.get("title") or page.get("menuTitle"),
        "slug": page.get("slug"),
        "restaurant_count": page.get("restaurantCount"),
        "timezone": page.get("timeZone"),
        "latitude": page.get("latitude"),
        "longitude": page.get("longitude"),
        "sessions": page.get("sessions") or [],
        "min_diners": page.get("minDiners"),
        "max_diners": page.get("maxDiners"),
    }


def discover_cities() -> list[dict[str, Any]]:
    data = next_data(SITE + "/")
    page = data.get("props", {}).get("pageProps", {}).get("page") or {}
    content = json.dumps(page)
    slugs = set(CITY_HINTS)
    for match in re.finditer(r'"/(?!_next|auth|magazine|restaurants)([a-z0-9-]+(?:/[a-z0-9-]+)?)"', content):
        first = match.group(1).split("/")[0]
        if first not in {"about-us", "contact-us", "frequently-asked-questions", "gift-vouchers", "privacy-policy", "our-story", "partnerships", "competitions", "frequent-foodies", "our-community"}:
            slugs.add(first)
    rows = []
    for slug in sorted(slugs):
        try:
            page = city_page(slug)
            row = simple_city(page)
            if row.get("id"):
                rows.append(row)
        except SystemExit:
            continue
        except Exception:
            continue
    return rows


def flatten_restaurant(raw: dict[str, Any]) -> dict[str, Any]:
    tags = (raw.get("tags") or {}).get("nodes") or []
    cuisines_edges = (raw.get("cuisines") or {}).get("edges") or []
    images_edges = (raw.get("images") or {}).get("edges") or []
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or raw.get("menuTitle"),
        "slug": raw.get("slug"),
        "url": SITE + (raw.get("slug") or ""),
        "rating": raw.get("rating"),
        "reviews": raw.get("approvedReviewsCount"),
        "summary": raw.get("reviewSummary"),
        "offers_first_table": raw.get("offersFirstTable"),
        "offers_regular_table": raw.get("offersRegularTable"),
        "region": (raw.get("region") or {}).get("menuTitle"),
        "region_id": (raw.get("region") or {}).get("id"),
        "suburb": (raw.get("suburb") or {}).get("menuTitle"),
        "suburb_id": (raw.get("suburb") or {}).get("id"),
        "cuisines": [((e or {}).get("node") or {}).get("title") for e in cuisines_edges if ((e or {}).get("node") or {}).get("title")],
        "tags": [{"id": t.get("id"), "title": t.get("title"), "category": t.get("category")} for t in tags],
        "sessions": raw.get("sessionTypes") or [],
        "first_table_sessions": raw.get("firstTableSessionTypes") or [],
        "regular_table_sessions": raw.get("regularTableSessionTypes") or [],
        "min_diners": raw.get("minDiners"),
        "max_diners": raw.get("maxDiners"),
        "booking_prices": raw.get("bookingPricesBySession") or [],
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "is_new": raw.get("isNew"),
        "featured_text": raw.get("featuredText"),
        "image": (((images_edges[0] or {}).get("node") or {}).get("url") if images_edges else None),
        "special_conditions": raw.get("specialConditions"),
    }


def restaurant_detail(restaurant_id: int) -> dict[str, Any]:
    data = graphql(RESTAURANT_DETAILS_QUERY, {"id": int(restaurant_id)})
    restaurant = data.get("Restaurant")
    if not restaurant:
        die(f"restaurant #{restaurant_id} not found")
    assert isinstance(restaurant, dict)
    return flatten_restaurant(restaurant)


def restaurant_ids(region_id: int | None = None, *, people: int = DEFAULT_PEOPLE, sessions: list[str] | None = None, tags: list[int] | None = None, suburbs: list[int] | None = None, dates: list[str] | None = None, ids: list[int] | None = None) -> list[int]:
    variables: dict[str, Any] = {"people": people}
    if region_id is not None:
        variables["regionId"] = region_id
    if sessions:
        variables["sessions"] = [s.upper() for s in sessions]
    if tags:
        variables["tags"] = tags
    if suburbs:
        variables["suburbs"] = suburbs
    if dates:
        variables["dates"] = dates
    if ids:
        variables["ids"] = ids
    data = graphql(ALL_RESTAURANT_IDS_QUERY, variables)
    return [int(row["id"]) for row in data.get("allRestaurants") or [] if row and row.get("id")]


def text_match(row: dict[str, Any], query: str | None) -> bool:
    if not query:
        return True
    q = query.lower()
    hay = " ".join(str(x or "") for x in [row.get("title"), row.get("suburb"), row.get("region"), " ".join(row.get("cuisines") or []), row.get("summary")]).lower()
    return q in hay


def session_match(row: dict[str, Any], session: str | None) -> bool:
    if not session:
        return True
    s = session.lower()
    return any(str(x).lower() == s for x in row.get("sessions") or [])


def format_restaurant(row: dict[str, Any]) -> str:
    bits = [f"#{row['id']} {row['title']}"]
    loc = ", ".join(x for x in [row.get("suburb"), row.get("region")] if x)
    if loc:
        bits.append(loc)
    if row.get("rating"):
        bits.append(f"rating {float(row['rating']):.2f} ({row.get('reviews') or 0} reviews)")
    if row.get("cuisines"):
        bits.append("cuisine: " + ", ".join(row["cuisines"][:4]))
    if row.get("sessions"):
        bits.append("sessions: " + ", ".join(row["sessions"]))
    bits.append(row.get("url") or "")
    return " | ".join(bits)


def print_rows(rows: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("title") and row.get("id"):
                print(format_restaurant(row))
            else:
                print(row)
    elif isinstance(rows, dict):
        for key, value in rows.items():
            print(f"{key}: {value}")
    else:
        print(rows)


def cmd_cities(args: argparse.Namespace) -> None:
    rows = discover_cities()
    print_rows(rows, as_json=args.json)


def cmd_city(args: argparse.Namespace) -> None:
    page = city_page(args.city)
    row = simple_city(page)
    row["subcities"] = [
        {"id": c.get("id"), "title": c.get("menuTitle"), "slug": c.get("slug"), "restaurant_count": c.get("hasOwnRestaurants")}
        for c in (page.get("subCities") or [])
    ]
    row["tags"] = page.get("tags") or []
    print_rows(row, as_json=args.json)


def cmd_search(args: argparse.Namespace) -> None:
    page = city_page(args.city)
    ids = restaurant_ids(page.get("id"), people=args.people, sessions=[args.session] if args.session else None, dates=[args.date] if args.date else None)
    rows: list[dict[str, Any]] = []
    for rid in ids[: args.fetch_limit]:
        row = restaurant_detail(rid)
        if not text_match(row, args.query):
            continue
        if not session_match(row, args.session):
            continue
        rows.append(row)
        if len(rows) >= args.limit:
            break
    if args.json:
        print(json.dumps({"city": simple_city(page), "count": len(rows), "restaurants": rows}, indent=2, ensure_ascii=False))
    else:
        if not rows:
            print("No matching restaurants found.")
        for row in rows:
            print(format_restaurant(row))


def cmd_detail(args: argparse.Namespace) -> None:
    row = restaurant_detail(args.id)
    print_rows(row, as_json=args.json)


def cmd_availability(args: argparse.Namespace) -> None:
    restaurant_ids_arg = [int(x) for part in args.ids for x in part.split(",") if x.strip()]
    date = args.date or dt.date.today().isoformat()
    data = graphql(AVAILABILITY_QUERY, {"restaurantIds": restaurant_ids_arg, "date": date, "people": args.people})
    rows = []
    for item in data.get("allAvailabilitySearch") or []:
        if not item:
            continue
        slots = [slot for slot in item.get("availableTimes") or [] if slot and (not args.available_only or slot.get("available"))]
        rows.append({
            "restaurant_id": item.get("restaurantId"),
            "available": item.get("available"),
            "data_status": item.get("dataStatus"),
            "sync_expires": item.get("syncExpires"),
            "slots": slots,
        })
    if args.json:
        print(json.dumps({"date": date, "people": args.people, "results": rows}, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(f"#{row['restaurant_id']} available={row['available']} status={row['data_status']}")
            for slot in row["slots"][: args.limit]:
                marker = "✓" if slot.get("available") else "×"
                print(f"  {marker} {slot.get('date')} {slot.get('time')} {slot.get('session') or ''} {slot.get('deal') or ''}".rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(description="First Table NZ public read-only restaurant/deal lookup.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cities", help="List First Table NZ city/region pages")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cities)

    p = sub.add_parser("city", help="Inspect a city/region page, suburbs, tags, and metadata")
    p.add_argument("city", nargs="?", default=DEFAULT_CITY)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_city)

    p = sub.add_parser("search", help="Search restaurants in a city by text/cuisine/suburb")
    p.add_argument("query", nargs="?", help="Case-insensitive text filter over title, suburb, cuisine, and summary")
    p.add_argument("--city", default=DEFAULT_CITY, help="City slug, e.g. auckland, wellington, christchurch")
    p.add_argument("--people", type=int, default=DEFAULT_PEOPLE)
    p.add_argument("--session", choices=["breakfast", "lunch", "dinner", "dinner2", "lasttable"], help="Filter/session availability hint")
    p.add_argument("--date", help="YYYY-MM-DD availability-prioritisation date")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--fetch-limit", type=int, default=60, help="Max restaurant details to fetch before filtering")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("detail", help="Fetch restaurant details by First Table restaurant id")
    p.add_argument("id", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_detail)

    p = sub.add_parser("availability", help="Fetch public availability slots for restaurant ids")
    p.add_argument("ids", nargs="+", help="One or more ids, comma-separated accepted")
    p.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    p.add_argument("--people", type=int, default=DEFAULT_PEOPLE)
    p.add_argument("--available-only", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_availability)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
