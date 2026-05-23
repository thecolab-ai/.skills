#!/usr/bin/env python3
"""homes.co.nz lightweight property estimate CLI.

Self-contained stdlib wrapper around public homes.co.nz read-only endpoints.
No login, account state, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_WEB = "https://homes.co.nz"
BASE_GATEWAY = "https://gateway.homes.co.nz"
BASE_API = "https://api-gateway.homes.co.nz"
UA = os.environ.get(
    "HOMES_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

STATE_LABELS = {
    0: "for_sale",
    1: "recently_sold",
    2: "off_market",
    3: "for_rent",
}


def die(message: str, code: int = 1) -> None:
    print(f"homes-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_params(params: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (params or {}).items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            out[key] = str(value).lower()
        elif isinstance(value, (list, tuple)):
            out[key] = ",".join(str(x) for x in value if x is not None)
        else:
            out[key] = str(value)
    return out


def request_json(base: str, path: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = base + path
    clean = clean_params(params)
    if clean:
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("error") or payload.get("ErrorMessage") or payload.get("message") or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}".rstrip())
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def short_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


def source_url(card_url: Any) -> str | None:
    if not isinstance(card_url, str) or not card_url:
        return None
    if card_url.startswith("http"):
        return card_url
    return BASE_WEB + "/address" + card_url


def state_label(value: Any) -> str | None:
    if isinstance(value, int):
        return STATE_LABELS.get(value, str(value))
    return None


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def estimate_from_details(detail: dict[str, Any], pd: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": first_not_none(detail.get("estimated_value"), pd.get("estimated_value")),
        "display": first_not_none(detail.get("display_estimated_value"), pd.get("display_estimated_value")),
        "display_short": first_not_none(detail.get("display_estimated_value_short"), pd.get("display_estimated_value_short")),
        "lower": first_not_none(detail.get("estimated_lower_value"), pd.get("estimated_lower_value")),
        "upper": first_not_none(detail.get("estimated_upper_value"), pd.get("estimated_upper_value")),
        "lower_display_short": first_not_none(detail.get("display_estimated_lower_value_short"), pd.get("display_estimated_lower_value_short")),
        "upper_display_short": first_not_none(detail.get("display_estimated_upper_value_short"), pd.get("display_estimated_upper_value_short")),
        "revision_date": short_date(first_not_none(detail.get("estimated_value_revision_date"), pd.get("estimated_value_revision_date"))),
    }


def rent_from_details(detail: dict[str, Any], pd: dict[str, Any]) -> dict[str, Any]:
    return {
        "lower": first_not_none(detail.get("estimated_rental_lower_value"), pd.get("estimated_rental_lower_value")),
        "upper": first_not_none(detail.get("estimated_rental_upper_value"), pd.get("estimated_rental_upper_value")),
        "lower_display_short": first_not_none(detail.get("display_estimated_rental_lower_value_short"), pd.get("display_estimated_rental_lower_value_short")),
        "upper_display_short": first_not_none(detail.get("display_estimated_rental_upper_value_short"), pd.get("display_estimated_rental_upper_value_short")),
        "yield": first_not_none(detail.get("estimated_rental_yield"), pd.get("estimated_rental_yield")),
        "revision_date": short_date(first_not_none(detail.get("estimated_rental_revision_date"), pd.get("estimated_rental_revision_date"))),
    }


def parse_sale(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "property_id": item.get("property_id"),
        "listing_id": item.get("listing_id") or None,
        "date": short_date(item.get("price_on")),
        "price": item.get("price") if item.get("can_display_sale_price", True) else None,
        "display_price": item.get("display_price") if item.get("can_display_sale_price", True) else None,
        "sale_type": item.get("sale_type"),
        "council_confirmed": item.get("council_confirmed"),
    }


def parse_card(card: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    detail = detail or {}
    pd = card.get("property_details") or {}
    point = card.get("point") or {}
    prop_id = first_not_none(card.get("property_id"), card.get("id"), detail.get("property_id"))
    out = {
        "property_id": prop_id,
        "listing_id": card.get("listing_id") or None,
        "state": card.get("state"),
        "state_label": state_label(card.get("state")),
        "address": first_not_none(pd.get("display_address"), pd.get("address")),
        "suburb": first_not_none(detail.get("suburb_name"), pd.get("suburb")),
        "city": first_not_none(detail.get("city_name"), pd.get("city")),
        "suburb_id": first_not_none(detail.get("suburb_id"), pd.get("suburb_id")),
        "city_id": first_not_none(detail.get("city_id"), pd.get("city_id")),
        "homes_estimate": estimate_from_details(detail, pd),
        "rent_estimate": rent_from_details(detail, pd),
        "bedrooms": first_not_none(detail.get("bed_estimate"), pd.get("num_bedrooms"), pd.get("latest_bedrooms")),
        "bathrooms": first_not_none(detail.get("bath_estimate"), pd.get("num_bathrooms"), pd.get("latest_bathrooms")),
        "car_spaces": first_not_none(detail.get("num_car_spaces"), pd.get("num_car_spaces"), pd.get("latest_car_spaces")),
        "floor_area": first_not_none(detail.get("floor_area"), pd.get("floor_area")),
        "land_area": first_not_none(detail.get("land_area"), pd.get("land_area")),
        "decade_built": first_not_none(detail.get("decade_built"), pd.get("decade_built")),
        "ownership": first_not_none(detail.get("ownership"), pd.get("ownership_type")),
        "capital_value": first_not_none(detail.get("capital_value_digit"), pd.get("capital_value")),
        "land_value": first_not_none(detail.get("land_value_digit"), pd.get("land_value")),
        "improvement_value": first_not_none(detail.get("improvement_value_digit"), pd.get("improvement_value")),
        "display_capital_value_short": first_not_none(detail.get("display_capital_value_short"), pd.get("display_capital_value_short")),
        "display_land_value_short": first_not_none(detail.get("display_land_value_short"), pd.get("display_land_value_short")),
        "display_improvement_value_short": first_not_none(detail.get("display_improvement_value_short"), pd.get("display_improvement_value_short")),
        "last_seen_sale_date": short_date(card.get("date")),
        "sales_count": card.get("sales_count"),
        "lat": point.get("lat"),
        "long": point.get("long"),
        "distance_m": card.get("distance_to_point"),
        "url": source_url(card.get("url")),
    }
    if out["homes_estimate"].get("value") is None and card.get("state") == 2:
        out["homes_estimate"]["value"] = card.get("price")
    return out


def parse_map_item(item: dict[str, Any], origin: tuple[float, float] | None = None) -> dict[str, Any]:
    point = item.get("point") or {}
    lat = as_float(point.get("lat"))
    lon = as_float(point.get("long"))
    distance = item.get("distance_to_point")
    if distance is None and origin and lat is not None and lon is not None:
        distance = distance_m(origin[0], origin[1], lat, lon)
    return {
        "property_id": item.get("id") or item.get("item_id"),
        "state": item.get("state"),
        "state_label": state_label(item.get("state")),
        "address": (item.get("property_details") or {}).get("address"),
        "price": item.get("price"),
        "display_price": item.get("display_price") or item.get("display_price_short"),
        "date": short_date(item.get("date")),
        "lat": lat,
        "long": lon,
        "distance_m": round(distance, 1) if isinstance(distance, (int, float)) else distance,
        "url": source_url(item.get("url")),
    }


def compact_card(card: dict[str, Any], origin: tuple[float, float] | None = None) -> dict[str, Any]:
    parsed = parse_card(card)
    if parsed.get("distance_m") is None and origin and parsed.get("lat") is not None and parsed.get("long") is not None:
        parsed["distance_m"] = round(distance_m(origin[0], origin[1], parsed["lat"], parsed["long"]), 1)
    return {
        "property_id": parsed.get("property_id"),
        "state": parsed.get("state"),
        "state_label": parsed.get("state_label"),
        "address": parsed.get("address"),
        "homes_estimate": parsed.get("homes_estimate"),
        "bedrooms": parsed.get("bedrooms"),
        "bathrooms": parsed.get("bathrooms"),
        "floor_area": parsed.get("floor_area"),
        "land_area": parsed.get("land_area"),
        "last_seen_sale_date": parsed.get("last_seen_sale_date"),
        "sales_count": parsed.get("sales_count"),
        "distance_m": parsed.get("distance_m"),
        "url": parsed.get("url"),
    }


def get_cards(property_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [x for x in property_ids if x]
    if not ids:
        return {}
    payload = request_json(BASE_GATEWAY, "/properties", {"property_ids": ",".join(ids)})
    out: dict[str, dict[str, Any]] = {}
    for card in (payload or {}).get("cards") or []:
        if not isinstance(card, dict):
            continue
        prop_id = card.get("property_id") or card.get("id")
        if prop_id:
            out[str(prop_id)] = card
    return out


def get_sales(property_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    ids = [x for x in property_ids if x]
    if not ids:
        return {}
    payload = request_json(BASE_GATEWAY, "/properties/sales", {"property_ids": ",".join(ids)})
    out: dict[str, list[dict[str, Any]]] = {}
    for row in (payload or {}).get("properties") or []:
        if not isinstance(row, dict):
            continue
        prop_id = row.get("id")
        sales = [parse_sale(x) for x in row.get("sales") or [] if isinstance(x, dict)]
        if prop_id:
            out[str(prop_id)] = sales
    return out


def get_detail(property_id: str) -> dict[str, Any]:
    payload = request_json(BASE_API, "/details", {"property_id": property_id})
    return (payload or {}).get("property") or {}


def first_sale_for(prop_id: str | None, sales_by_id: dict[str, list[dict[str, Any]]], card: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if prop_id and sales_by_id.get(prop_id):
        return sales_by_id[prop_id][0]
    if card and card.get("date"):
        return {"date": short_date(card.get("date")), "price": None, "display_price": card.get("display_price")}
    return None


def _address_search(query: str) -> list[dict[str, Any]]:
    """Return raw address/search Results list for *query*, stripping empty items."""
    payload = request_json(BASE_GATEWAY, "/address/search", {"Address": query})
    return [x for x in (payload or {}).get("Results") or [] if isinstance(x, dict)]


def _all_type1(results: list[dict[str, Any]]) -> bool:
    """Return True when every result is a city-level (Type=1) fallback row."""
    return bool(results) and all(r.get("Type") == 1 for r in results)


def _resolve_property_from_map(lat: float, lon: float, street_number: Any, radius_m: int = 150) -> str | None:
    """Try to find a property_id near *lat*/*lon* using the map/items viewport endpoint.

    Looks for a map item or card whose ``display_street_number`` contains
    ``str(street_number)`` within *radius_m* metres.  Returns the first matching
    property_id, or None if nothing suitable is found.
    """
    if lat is None or lon is None:
        return None
    lat_delta = radius_m / 111320.0
    lon_delta = radius_m / (111320.0 * max(0.1, math.cos(math.radians(lat))))
    params: dict[str, Any] = {
        "nw_lat": lat + lat_delta,
        "nw_long": lon - lon_delta,
        "se_lat": lat - lat_delta,
        "se_long": lon + lon_delta,
        "limit": 50,
        "display_rentals": False,
    }
    payload = request_json(BASE_GATEWAY, "/map/items", params)
    if not payload:
        return None
    snum = str(street_number).strip() if street_number is not None else ""

    # Prefer cards (richer data) first – check property_details.address for street number.
    for card in (payload.get("cards") or []):
        if not isinstance(card, dict):
            continue
        prop_id = card.get("property_id") or card.get("id")
        if not prop_id:
            continue
        pd = card.get("property_details") or {}
        addr = pd.get("address") or pd.get("display_address") or ""
        # Match when the address starts with the street number (handles "7/1", "1", etc.)
        if snum and addr:
            # "42/1 Queen Street…" → split on space, first token is "42/1"
            first_token = addr.split()[0] if addr.split() else ""
            # Accept exact number or unit/number where right side equals snum
            parts = first_token.split("/")
            if snum in parts or first_token == snum:
                return str(prop_id)
        # Fallback: return first valid card property_id when no number hint
        if not snum:
            return str(prop_id)

    # Fall through to map_items (lighter, just lat/lon + short URL)
    for item in (payload.get("map_items") or []):
        if not isinstance(item, dict):
            continue
        prop_id = item.get("id") or item.get("item_id")
        if not prop_id:
            continue
        display = str(item.get("display_street_number") or "").strip()
        if snum and display:
            parts = display.split("/")
            if snum in parts or display == snum:
                return str(prop_id)
        if not snum:
            return str(prop_id)
    return None


def address(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()

    # ── Step 1: primary address/search ──────────────────────────────────────
    results = _address_search(args.query)

    # ── Step 2: city-level fallback recovery ────────────────────────────────
    # When the API returns only Type=1 (city rows) the query likely included a
    # suburb or city suffix that confused the search engine.  Retry by dropping
    # the last word iteratively until we get address-level (Type=3 or Type=4)
    # results or run out of words to drop.
    retry_query = args.query
    if _all_type1(results):
        words = args.query.split()
        while len(words) > 2 and _all_type1(results):
            words = words[:-1]
            retry_query = " ".join(words)
            results = _address_search(retry_query)

    # Limit to the requested number of matches.
    results = results[: max(1, args.limit)]

    # ── Step 3: property-ID resolve for null-PropertyID address rows ─────────
    # Since mid-2025 the address/search endpoint omits PropertyID for many
    # Type=4 (address-level) results when the query includes a city qualifier.
    # For those rows we attempt a secondary resolve via the map/items viewport
    # endpoint, matching by the street number embedded in the address result.
    for item in results:
        if item.get("PropertyID"):
            continue  # already have an ID – nothing to do
        if item.get("Type") != 4:
            continue  # only attempt resolve for address-level rows
        lat = as_float(item.get("Lat"))
        lon = as_float(item.get("Long"))
        street_number = item.get("StreetNumber") or item.get("UnitIdentifier") or None
        resolved = _resolve_property_from_map(lat, lon, street_number)
        if resolved:
            item["PropertyID"] = resolved

    # ── Step 4: bulk-fetch cards / sales for resolved IDs ───────────────────
    prop_ids = [str(x.get("PropertyID")) for x in results if x.get("PropertyID")]
    cards = get_cards(prop_ids)
    sales = get_sales(prop_ids)

    matches = []
    for item in results:
        prop_id = str(item.get("PropertyID")) if item.get("PropertyID") else None
        card = cards.get(prop_id or "")
        parsed_card = parse_card(card) if card else {}
        last_sale = first_sale_for(prop_id, sales, card)
        matches.append(
            {
                "title": item.get("Title"),
                "type": item.get("Type"),
                "score": item.get("Score"),
                "property_id": prop_id,
                "lat": item.get("Lat"),
                "long": item.get("Long"),
                "suburb_id": item.get("SuburbID"),
                "city_id": item.get("CityID"),
                "suburb": item.get("Suburb") or None,
                "city": item.get("City") or None,
                "homes_estimate": parsed_card.get("homes_estimate"),
                "bedrooms": parsed_card.get("bedrooms"),
                "bathrooms": parsed_card.get("bathrooms"),
                "floor_area": parsed_card.get("floor_area"),
                "land_area": parsed_card.get("land_area"),
                "last_sale": last_sale,
                "sales_count": parsed_card.get("sales_count"),
                "url": parsed_card.get("url"),
            }
        )
    return {
        "query": args.query,
        "count": len(matches),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "matches": matches,
        "error": None,
    }


def cmd_address(args: argparse.Namespace) -> None:
    emit(address(args), args.json, print_address)


def property_detail(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    cards = get_cards([args.property_id])
    card = cards.get(args.property_id) or {}
    detail = get_detail(args.property_id)
    if not card and not detail:
        die(f"no public property detail found for {args.property_id}")
    sales_history = get_sales([args.property_id]).get(args.property_id, [])
    summary = parse_card(card, detail)
    if not summary.get("property_id"):
        summary["property_id"] = args.property_id
    summary["last_sale"] = sales_history[0] if sales_history else first_sale_for(args.property_id, {}, card)
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "property": summary,
        "sales_history_count": len(sales_history),
        "sales_history": sales_history,
    }


def cmd_property(args: argparse.Namespace) -> None:
    emit(property_detail(args), args.json, print_property)


def resolve_suburb(value: str) -> dict[str, Any]:
    if value.isdigit():
        return {"SuburbID": int(value), "Title": value}
    payload = request_json(BASE_GATEWAY, "/address/search", {"Address": value})
    results = [x for x in (payload or {}).get("Results") or [] if isinstance(x, dict)]
    for item in results:
        if item.get("Type") == 2 and item.get("SuburbID"):
            return item
    for item in results:
        if item.get("SuburbID"):
            return item
    die(f"no suburb id found for {value!r}")


def suburb(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    resolved = resolve_suburb(args.name_or_id)
    suburb_id = str(resolved.get("SuburbID"))
    history_payload = request_json(BASE_GATEWAY, "/suburb/estimate_history", {"id": suburb_id})
    rent_payload = request_json(BASE_GATEWAY, "/median_suburb_rent_estimate", {"id": suburb_id})
    history = [x for x in (history_payload or {}).get("estimate_history") or [] if isinstance(x, dict)]
    history = sorted(history, key=lambda x: x.get("date") or "")
    latest = history[-1] if history else None
    rows = history[-max(1, args.history_limit) :]
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "suburb": {
            "suburb_id": int(suburb_id) if suburb_id.isdigit() else suburb_id,
            "title": resolved.get("Title"),
            "suburb": resolved.get("Suburb") or None,
            "city": resolved.get("City") or None,
            "property_count": resolved.get("Size"),
            "lat": resolved.get("Lat"),
            "long": resolved.get("Long"),
        },
        "latest_median_estimate": {
            "date": short_date(latest.get("date")) if latest else None,
            "estimate": latest.get("estimate") if latest else None,
            "display_estimate": latest.get("display_estimate") if latest else None,
        },
        "median_rent_estimate": {
            "date": short_date((rent_payload or {}).get("date")),
            "estimate": (rent_payload or {}).get("estimate"),
        },
        "history_count": len(history),
        "history": [
            {
                "date": short_date(row.get("date")),
                "estimate": row.get("estimate"),
                "display_estimate": row.get("display_estimate"),
            }
            for row in rows
        ],
        "sales_volume": None,
        "sales_volume_note": "No no-login suburb sales-volume aggregate was verified; use property sales history for known property ids.",
    }


def cmd_suburb(args: argparse.Namespace) -> None:
    emit(suburb(args), args.json, print_suburb)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bounding_box(lat: float, lon: float, radius_m: int) -> dict[str, float]:
    lat_delta = radius_m / 111320.0
    lon_delta = radius_m / (111320.0 * max(0.1, math.cos(math.radians(lat))))
    return {
        "nw_lat": lat + lat_delta,
        "nw_long": lon - lon_delta,
        "se_lat": lat - lat_delta,
        "se_long": lon + lon_delta,
    }


def nearby(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    source_cards = get_cards([args.property_id])
    source_card = source_cards.get(args.property_id)
    if not source_card:
        die(f"no public property card found for {args.property_id}")
    source = parse_card(source_card)
    lat = as_float(source.get("lat"))
    lon = as_float(source.get("long"))
    if lat is None or lon is None:
        die(f"property {args.property_id} has no public map point")
    box = bounding_box(lat, lon, max(25, args.radius))
    params: dict[str, Any] = {
        **box,
        "limit": min(max(args.limit * 4, 20), 100),
        "display_rentals": False,
    }
    payload = request_json(BASE_GATEWAY, "/map/items", params)
    origin = (lat, lon)
    seen = {args.property_id}
    rows: list[dict[str, Any]] = []
    for card in (payload or {}).get("cards") or []:
        if not isinstance(card, dict):
            continue
        prop_id = str(card.get("property_id") or card.get("id") or "")
        if not prop_id or prop_id in seen:
            continue
        seen.add(prop_id)
        rows.append(compact_card(card, origin))
    for item in (payload or {}).get("map_items") or []:
        if len(rows) >= args.limit * 2:
            break
        if not isinstance(item, dict):
            continue
        prop_id = str(item.get("id") or item.get("item_id") or "")
        if not prop_id or prop_id in seen:
            continue
        seen.add(prop_id)
        rows.append(parse_map_item(item, origin))
    rows = sorted(rows, key=lambda x: (x.get("distance_m") is None, x.get("distance_m") or 0))[: args.limit]
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "property_id": args.property_id,
        "radius_m": args.radius,
        "source_property": source,
        "count": len(rows),
        "comparables": rows,
    }


def cmd_nearby(args: argparse.Namespace) -> None:
    emit(nearby(args), args.json, print_nearby)


def fmt_estimate(value: dict[str, Any] | None) -> str:
    if not value:
        return "-"
    display = value.get("display_short") or value.get("display")
    lower = value.get("lower_display_short")
    upper = value.get("upper_display_short")
    if display and lower and upper:
        return f"{display} ({lower}-{upper})"
    return str(display or value.get("value") or "-")


def fmt_sale(value: dict[str, Any] | None) -> str:
    if not value:
        return "-"
    bits = [value.get("date"), value.get("display_price")]
    return " ".join(str(x) for x in bits if x) or "-"


def print_address(data: dict[str, Any]) -> None:
    print(f"Homes NZ address: {data.get('count')} matches for {data.get('query')!r} ({data.get('elapsed_ms')} ms)")
    print()
    for item in data.get("matches") or []:
        print(f"{item.get('property_id') or '-'}  {item.get('title')}")
        bits = [
            "HEV " + fmt_estimate(item.get("homes_estimate")),
            f"{item.get('bedrooms') or '-'} bed",
            f"{item.get('bathrooms') or '-'} bath",
            f"last sale {fmt_sale(item.get('last_sale'))}",
        ]
        print("  " + " | ".join(bits))
        if item.get("url"):
            print(f"  {item.get('url')}")
        print()


def print_property(data: dict[str, Any]) -> None:
    prop = data.get("property") or {}
    print(f"{prop.get('property_id')}  {prop.get('address') or ''}")
    print(f"HEV: {fmt_estimate(prop.get('homes_estimate'))}")
    print(f"Beds/baths/cars: {prop.get('bedrooms') or '-'} / {prop.get('bathrooms') or '-'} / {prop.get('car_spaces') or '-'}")
    print(f"Area: floor {prop.get('floor_area') or '-'} sqm | land {prop.get('land_area') or '-'} sqm")
    print(f"CV/LV/IV: {prop.get('display_capital_value_short') or '-'} / {prop.get('display_land_value_short') or '-'} / {prop.get('display_improvement_value_short') or '-'}")
    print(f"Last sale: {fmt_sale(prop.get('last_sale'))}")
    if prop.get("url"):
        print(prop["url"])
    print()
    print(f"Sales history: {data.get('sales_history_count')} records")
    for sale in data.get("sales_history") or []:
        print(f"  {sale.get('date') or '-'}  {sale.get('display_price') or '-'}  {sale.get('sale_type') or ''}".rstrip())


def print_suburb(data: dict[str, Any]) -> None:
    suburb = data.get("suburb") or {}
    latest = data.get("latest_median_estimate") or {}
    rent = data.get("median_rent_estimate") or {}
    print(f"{suburb.get('suburb_id')}  {suburb.get('title')}")
    print(f"Latest median HomesEstimate: {latest.get('display_estimate') or latest.get('estimate') or '-'} ({latest.get('date') or '-'})")
    print(f"Median rent estimate: {rent.get('estimate') or '-'} ({rent.get('date') or '-'})")
    if suburb.get("property_count") is not None:
        print(f"Typeahead property count: {suburb.get('property_count')}")
    print(f"History points: {data.get('history_count')}")
    print(data.get("sales_volume_note"))


def print_nearby(data: dict[str, Any]) -> None:
    source = data.get("source_property") or {}
    print(f"Nearby properties around {source.get('address') or data.get('property_id')} within {data.get('radius_m')}m ({data.get('elapsed_ms')} ms)")
    print()
    for item in data.get("comparables") or []:
        dist = item.get("distance_m")
        dist_label = f"{dist:.0f}m" if isinstance(dist, (int, float)) else "-"
        estimate = fmt_estimate(item.get("homes_estimate")) if item.get("homes_estimate") else item.get("display_price") or "-"
        print(f"{item.get('property_id')}  {item.get('address') or ''}")
        print(f"  {dist_label} | {item.get('state_label') or item.get('state')} | {estimate}")
        if item.get("url"):
            print(f"  {item.get('url')}")
        print()


def emit(data: dict[str, Any], as_json: bool, printer: Any) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        printer(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight homes.co.nz public read-only property estimate CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("address", help="search homes.co.nz address/typeahead results")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_address)

    sp = sub.add_parser("property", help="fetch public property detail and sales history")
    sp.add_argument("property_id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_property)

    sp = sub.add_parser("suburb", help="fetch suburb estimate trend and rent estimate")
    sp.add_argument("name_or_id")
    sp.add_argument("--history-limit", type=int, default=12)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_suburb)

    sp = sub.add_parser("nearby", help="fetch nearby comparable property snapshots")
    sp.add_argument("property_id")
    sp.add_argument("--radius", type=int, default=150, help="radius in metres")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_nearby)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
