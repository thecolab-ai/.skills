#!/usr/bin/env python3
"""Department of Conservation NZ lightweight read-only CLI.

Self-contained stdlib wrapper around public DOC booking, Great Walk, alert, and
track information endpoints. No login, booking mutation, payment, browser
automation, or third-party dependencies.
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
from typing import Any

BOOKING_API = "https://prod-nz-rdr.recreation-management.tylerapp.com/nzrdr/rdr/"
BOOKING_WEB = "https://bookings.doc.govt.nz/Web/"
DOC_SITE = "https://www.doc.govt.nz"
ALERTS_INDEX = DOC_SITE + "/parks-and-recreation/know-before-you-go/alerts/"
UA = os.environ.get(
    "DOC_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(message: str, code: int = 1) -> None:
    print(f"doc-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|li|div|h[1-6]|tr)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"<[^>]*$", " ", text)
    text = html.unescape(text)
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(value: str, length: int = 160) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= length:
        return value
    return value[: length - 1].rstrip() + "..."


def coalesce(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return default


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def date_only(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) >= 10:
        return text[:10]
    return text


def parse_date(value: str, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        die(f"{label} must be an ISO date like 2026-11-01")


def tomorrow() -> dt.date:
    return dt.date.today() + dt.timedelta(days=1)


def abs_doc_url(value: str | None) -> str | None:
    if not value:
        return None
    url = html.unescape(value.strip())
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return DOC_SITE + url
    if url.startswith("http://www.doc.govt.nz"):
        return "https://" + url[len("http://") :]
    if url.startswith("http://doc.govt.nz"):
        return "https://www." + url[len("http://") :]
    return url


def attr_value(attrs: str, name: str) -> str | None:
    pattern = rf"""{re.escape(name)}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
    match = re.search(pattern, attrs, flags=re.I)
    if not match:
        return None
    return html.unescape(next(group for group in match.groups() if group is not None))


def extract_doc_link(fragment: str | None) -> str | None:
    if not fragment:
        return None
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", str(fragment), flags=re.I):
        href = html.unescape(href)
        absolute = abs_doc_url(href)
        if absolute and "doc.govt.nz" in absolute:
            return absolute
    return None


def booking_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://bookings.doc.govt.nz",
        "Referer": BOOKING_WEB,
        "User-Agent": UA,
    }


def request_booking_json(path: str, payload: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = BOOKING_API + path.lstrip("/")
    headers = booking_headers()
    data = None
    method = "GET"
    if payload is not None:
        method = "POST"
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            if resp.status == 202 and resp.headers.get("x-amzn-waf-action") == "challenge":
                die("DOC booking API returned a WAF challenge; retry later or use a browser-sniffed session")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = raw[:300]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                detail = str(parsed.get("Message") or parsed.get("message") or parsed.get("error") or detail)
        except Exception:
            pass
        die(f"HTTP {e.code} from DOC booking API {url}: {detail or e.reason}")
    except urllib.error.URLError as e:
        die(f"network error calling DOC booking API {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from DOC booking API {url}: {e}")


def request_doc_json(path: str, timeout: int = 25) -> Any:
    url = DOC_SITE + "/api/" + path.lstrip("/")
    headers = {"Accept": "application/json, text/plain, */*", "Referer": DOC_SITE + "/", "User-Agent": UA}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from DOC API {url}: {raw[:300] or e.reason}")
    except urllib.error.URLError as e:
        die(f"network error calling DOC API {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from DOC API {url}: {e}")


def request_text(url: str, timeout: int = 25) -> tuple[str, str]:
    headers = {"Accept": "text/html,application/xhtml+xml", "User-Agent": UA}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:300] or e.reason}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def emit(data: dict[str, Any], as_json: bool, printer: Any) -> None:
    if as_json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        printer(data)


def get_great_walk_payload() -> dict[str, Any]:
    payload = request_booking_json("search/getgreatwalkplaces/false/isCashier")
    if not isinstance(payload, dict):
        die("unexpected Great Walk list response from DOC booking API")
    return payload


def normalize_great_walk(raw: dict[str, Any]) -> dict[str, Any]:
    fixed_min = int_or_none(raw.get("FixedGWMinNight"))
    fixed_max = int_or_none(raw.get("FixedGWMaxNight"))
    description = raw.get("Description") or ""
    allow_booking = boolish(raw.get("AllowWebBooking"))
    viewable = boolish(raw.get("IsWebViewable"))
    return {
        "place_id": raw.get("PlaceId"),
        "name": clean_text(coalesce(raw, "Name", "ShortName", default="")),
        "status": "open" if allow_booking and viewable else "closed",
        "allow_web_booking": allow_booking,
        "web_viewable": viewable,
        "great_walk_available": boolish(raw.get("IsAvailableForGreatwalk")),
        "fixed_itinerary": boolish(raw.get("IsAvailableForFixedgreatwalk")),
        "fixed_min_nights": fixed_min,
        "fixed_max_nights": fixed_max,
        "region_id": raw.get("RegionId"),
        "latitude": raw.get("Latitude"),
        "longitude": raw.get("Longitude"),
        "phone": raw.get("VoicePhone"),
        "doc_url": extract_doc_link(description),
    }


def resolve_great_walk(identifier: str, payload: dict[str, Any] | None = None, *, required: bool = True) -> dict[str, Any] | None:
    payload = payload or get_great_walk_payload()
    walks = payload.get("GWPlaceData") or []
    needle = identifier.strip().lower()
    numeric = int_or_none(identifier)
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for raw in walks:
        if not isinstance(raw, dict):
            continue
        name = clean_text(coalesce(raw, "Name", "ShortName", default=""))
        place_id = int_or_none(raw.get("PlaceId"))
        if numeric is not None and place_id == numeric:
            return raw
        lowered = name.lower()
        if lowered == needle:
            exact.append(raw)
        elif needle and (needle in lowered or lowered in needle):
            fuzzy.append(raw)
    if exact:
        return exact[0]
    if fuzzy:
        return fuzzy[0]
    if required:
        names = ", ".join(clean_text(coalesce(w, "Name", "ShortName", default="")) for w in walks if isinstance(w, dict))
        die(f"unknown Great Walk {identifier!r}; available: {names}")
    return None


def get_great_walk_meta(place_id: Any) -> dict[str, Any]:
    payload = request_booking_json(f"search/getgreatwalksearchdata/placeId/{urllib.parse.quote(str(place_id))}")
    if not isinstance(payload, dict):
        die(f"unexpected Great Walk metadata response for place {place_id}")
    return payload


def night_bounds(meta: dict[str, Any], place: dict[str, Any]) -> tuple[int, int, bool]:
    fixed = boolish(meta.get("IsAvailableForFixedGreatWalk")) or boolish(place.get("IsAvailableForFixedgreatwalk"))
    min_nights = int_or_none(meta.get("MinNoofNights")) or int_or_none(place.get("FixedGWMinNight")) or 1
    max_nights = int_or_none(meta.get("MaxNoofNights")) or int_or_none(place.get("FixedGWMaxNight")) or min_nights
    return min_nights, max_nights, fixed


def default_start_date(payload: dict[str, Any]) -> dt.date:
    start_text = payload.get("FutureBookingStartDate")
    start = parse_date(start_text[:10], "FutureBookingStartDate") if isinstance(start_text, str) and len(start_text) >= 10 else tomorrow()
    return max(tomorrow(), start)


def resolve_nights(args: argparse.Namespace, meta: dict[str, Any], place: dict[str, Any], start: dt.date) -> int:
    min_nights, max_nights, fixed = night_bounds(meta, place)
    if getattr(args, "to_date", None):
        end = parse_date(args.to_date, "--to")
        nights = (end - start).days
        if nights <= 0:
            die("--to must be after --from; it is treated as the checkout/end date")
    elif getattr(args, "nights", None):
        nights = args.nights
    else:
        nights = min_nights if fixed else 1
    if nights < min_nights:
        die(f"{clean_text(coalesce(place, 'Name', 'ShortName', default='Great Walk'))} requires at least {min_nights} nights")
    if max_nights and nights > max_nights:
        die(f"{clean_text(coalesce(place, 'Name', 'ShortName', default='Great Walk'))} allows at most {max_nights} nights")
    return nights


def resolve_nights_or_none(args: argparse.Namespace, meta: dict[str, Any], place: dict[str, Any], start: dt.date) -> int | None:
    min_nights, max_nights, fixed = night_bounds(meta, place)
    if getattr(args, "to_date", None):
        end = parse_date(args.to_date, "--to")
        nights = (end - start).days
        if nights <= 0:
            die("--to must be after --from; it is treated as the checkout/end date")
    elif getattr(args, "nights", None):
        nights = args.nights
    else:
        nights = min_nights if fixed else 1
    if nights < min_nights:
        return None
    if max_nights and nights > max_nights:
        return None
    return nights


def choose_accommodation(meta: dict[str, Any], requested: str | None = None) -> dict[str, Any]:
    options = meta.get("GWAccomodationData") or []
    if not isinstance(options, list) or not options:
        if requested:
            return {"AccomodationName": requested, "AccomodationId": None}
        return {"AccomodationName": "Hut", "AccomodationId": None}
    if requested:
        needle = requested.lower()
        for option in options:
            name = str(option.get("AccomodationName") or "")
            if needle == name.lower() or needle in name.lower():
                return option
        names = ", ".join(str(o.get("AccomodationName")) for o in options)
        die(f"unknown accommodation {requested!r}; available: {names}")
    for option in options:
        if str(option.get("AccomodationName") or "").lower() == "hut":
            return option
    return options[0]


def choose_direction(meta: dict[str, Any], requested: str | None = None) -> dict[str, Any] | None:
    directions = meta.get("GWPlaceDirection") or []
    if not isinstance(directions, list) or not directions:
        return None
    if requested:
        needle = requested.lower()
        numeric = int_or_none(requested)
        for direction in directions:
            direction_id = int_or_none(direction.get("PlaceDirectionId"))
            name = str(direction.get("PlaceDirectionName") or "")
            if numeric is not None and direction_id == numeric:
                return direction
            if needle == name.lower() or needle in name.lower():
                return direction
        names = ", ".join(f"{d.get('PlaceDirectionId')} {d.get('PlaceDirectionName')}" for d in directions)
        die(f"unknown direction {requested!r}; available: {names}")
    if boolish(meta.get("IsDirectionVisible")):
        return directions[0]
    return None


def get_great_walk_facilities(
    place: dict[str, Any],
    meta: dict[str, Any],
    start: dt.date,
    nights: int,
    accommodation: dict[str, Any],
    direction: dict[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "accomodation": accommodation.get("AccomodationName"),
        "placeId": place.get("PlaceId"),
        "customerClassificationId": 0,
        "arrivalDate": start.isoformat(),
        "startDate": start.isoformat(),
        "nights": nights,
    }
    if direction:
        body["direction"] = direction.get("PlaceDirectionId")
    payload = request_booking_json("search/greatwalkplacefacility", payload=body)
    if not isinstance(payload, dict):
        die("unexpected Great Walk availability response from DOC booking API")
    return payload


def normalize_facility(facility: dict[str, Any]) -> dict[str, Any]:
    dates = []
    for item in facility.get("GreatWalkFacilityDateData") or []:
        if not isinstance(item, dict):
            continue
        dates.append(
            {
                "date": date_only(item.get("ArrivalDate")),
                "total_available": item.get("TotalAvailable"),
                "is_available": boolish(item.get("IsAvailable")),
                "is_season_available": boolish(item.get("IsSeasonAvailable")),
                "allocated_seats": item.get("AllocationSeats"),
                "allocated_seats_reserved": item.get("AllocatedSeatsReservationCount"),
            }
        )
    return {
        "facility_id": facility.get("FacilityId"),
        "name": clean_text(facility.get("FacilityName")),
        "category": facility.get("FacilityCategory"),
        "facility_type": facility.get("FacilityType"),
        "capacity": facility.get("MasterMaxOccupancy"),
        "available_for_patron": boolish(facility.get("IsAvailableForPatron")),
        "available_for_group": boolish(facility.get("IsAvailableForGroup")),
        "dates": dates,
    }


def normalize_availability(
    place: dict[str, Any],
    meta: dict[str, Any],
    start: dt.date,
    nights: int,
    accommodation: dict[str, Any],
    direction: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    facility_id: int | None = None,
) -> dict[str, Any]:
    facilities = [normalize_facility(item) for item in payload.get("GreatWalkFacilityData") or [] if isinstance(item, dict)]
    if facility_id is not None:
        facilities = [facility for facility in facilities if int_or_none(facility.get("facility_id")) == facility_id]
    headers = []
    for item in payload.get("GreatWalkFacilityHeaderData") or []:
        if isinstance(item, dict):
            headers.append({"date": date_only(item.get("FullDate")), "day": item.get("Day"), "month": item.get("Month"), "day_of_week": item.get("DayOfWeek")})
    return {
        "source": "Department of Conservation booking availability",
        "place": normalize_great_walk(place),
        "start_date": start.isoformat(),
        "nights": nights,
        "accommodation": {
            "id": accommodation.get("AccomodationId"),
            "name": accommodation.get("AccomodationName"),
        },
        "direction": None
        if not direction
        else {
            "id": direction.get("PlaceDirectionId"),
            "name": direction.get("PlaceDirectionName"),
            "type": direction.get("PlaceDirectionType"),
        },
        "date_headers": headers,
        "facility_count": len(facilities),
        "facilities": facilities,
        "booking_url": BOOKING_WEB,
    }


def availability_for_place(place: dict[str, Any], args: argparse.Namespace, payload: dict[str, Any], *, facility_id: int | None = None) -> dict[str, Any]:
    meta = get_great_walk_meta(place.get("PlaceId"))
    start = parse_date(args.from_date, "--from") if args.from_date else default_start_date(payload)
    nights = resolve_nights(args, meta, place, start)
    accommodation = choose_accommodation(meta, args.accommodation)
    direction = choose_direction(meta, args.direction)
    raw = get_great_walk_facilities(place, meta, start, nights, accommodation, direction)
    data = normalize_availability(place, meta, start, nights, accommodation, direction, raw, facility_id=facility_id)
    if facility_id is not None and not data["facilities"]:
        die(f"facility id {facility_id} was not present in the returned Great Walk availability grid")
    return data


def find_facility_place(facility_id: int, args: argparse.Namespace, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dt.date, int]:
    for place in payload.get("GWPlaceData") or []:
        if not isinstance(place, dict):
            continue
        meta = get_great_walk_meta(place.get("PlaceId"))
        start = parse_date(args.from_date, "--from") if args.from_date else default_start_date(payload)
        nights = resolve_nights_or_none(args, meta, place, start)
        if nights is None:
            continue
        accommodations = meta.get("GWAccomodationData") or []
        if args.accommodation:
            accommodations = [choose_accommodation(meta, args.accommodation)]
        elif not accommodations:
            accommodations = [choose_accommodation(meta)]
        for accommodation in accommodations:
            if not isinstance(accommodation, dict):
                continue
            direction = choose_direction(meta, args.direction)
            raw = get_great_walk_facilities(place, meta, start, nights, accommodation, direction)
            for facility in raw.get("GreatWalkFacilityData") or []:
                if isinstance(facility, dict) and int_or_none(facility.get("FacilityId")) == facility_id:
                    return place, meta, accommodation, direction, start, nights
    die(f"could not find Great Walk facility id {facility_id}; run `huts --great-walk <name> --json` to list facility ids")


def popular_places() -> list[dict[str, Any]]:
    payload = request_booking_json("search/popular/places/")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("PlaceData", "places", "data", "items"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    die("unexpected popular places response from DOC booking API")


def normalize_place(raw: dict[str, Any]) -> dict[str, Any]:
    description_raw = coalesce(raw, "PlaceDescription", "Description", default="")
    return {
        "place_id": raw.get("PlaceId"),
        "name": clean_text(coalesce(raw, "PlaceName", "Name", default="")),
        "city_park_id": raw.get("CityParkId"),
        "entity_type": raw.get("EntityType"),
        "available_unit_count": raw.get("AvailableUnitCount"),
        "reservation_count": raw.get("ReservationCount"),
        "latitude": raw.get("Latitude"),
        "longitude": raw.get("Longitude"),
        "description": clean_text(description_raw),
        "doc_url": extract_doc_link(description_raw),
        "booking_url": BOOKING_WEB,
    }


def search_places(query: str) -> list[dict[str, Any]]:
    needle = query.lower()
    matches = []
    for raw in popular_places():
        place = normalize_place(raw)
        haystack = " ".join(str(place.get(key) or "") for key in ("name", "description", "entity_type")).lower()
        if needle in haystack:
            matches.append(place)
    return matches


def parse_alert_components(page_html: str) -> list[dict[str, str]]:
    components = []
    for match in re.finditer(r"<doc-alerts\b([^>]*)>", page_html, flags=re.I):
        attrs = match.group(1)
        guid = attr_value(attrs, "guid")
        if not guid:
            continue
        components.append(
            {
                "guid": guid,
                "type": attr_value(attrs, "type") or "unique",
                "title": attr_value(attrs, "alert-title") or attr_value(attrs, "title") or "Alerts",
            }
        )
    return components


def alert_endpoint(component: dict[str, str]) -> str:
    guid = urllib.parse.quote(component["guid"])
    alert_type = component.get("type") or "unique"
    if alert_type == "summary":
        return f"alerts/alertsummary/{guid}"
    if alert_type == "place":
        return f"alerts/alertregionsummary/{guid}"
    return f"alerts/guid/{guid}"


def normalize_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": clean_text(alert.get("summary")),
        "description": clean_text(alert.get("description")),
        "sub_text": clean_text(alert.get("subText")),
        "sort_date": alert.get("sortDate"),
        "display_date": alert.get("displayDate"),
        "associated_booking_ids": alert.get("associatedBookingIDs"),
    }


def normalize_alert_groups(payload: Any, *, title: str, url: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    groups = []
    if payload and isinstance(payload[0], dict) and "alerts" in payload[0]:
        for group in payload:
            if not isinstance(group, dict):
                continue
            alerts = [normalize_alert(alert) for alert in group.get("alerts") or [] if isinstance(alert, dict)]
            groups.append(
                {
                    "name": clean_text(group.get("name")) or title,
                    "url": abs_doc_url(group.get("staticLink")) or url,
                    "is_general": boolish(group.get("isGeneral")),
                    "alert_count": len(alerts),
                    "alerts": alerts,
                }
            )
    else:
        alerts = [normalize_alert(alert) for alert in payload if isinstance(alert, dict)]
        groups.append({"name": title, "url": url, "is_general": False, "alert_count": len(alerts), "alerts": alerts})
    return groups


def fetch_alert_groups_from_html(page_html: str, page_url: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for component in parse_alert_components(page_html):
        payload = request_doc_json(alert_endpoint(component))
        groups.extend(normalize_alert_groups(payload, title=component.get("title") or "Alerts", url=page_url))
    return groups


def fetch_alert_regions() -> list[dict[str, Any]]:
    page_html, final_url = request_text(ALERTS_INDEX)
    regions = []
    card_pattern = r"<(?:doc-summary-card|doc-standard-product-card)\b([^>]*)>"
    for match in re.finditer(card_pattern, page_html, flags=re.I):
        attrs = match.group(1)
        title = attr_value(attrs, "title")
        link = attr_value(attrs, "link")
        if not title or not link or "/alerts/" not in link:
            continue
        url = abs_doc_url(link)
        slug_match = re.search(r"/places-to-go/([^/]+)/alerts/?", link)
        slug = slug_match.group(1) if slug_match else title.lower().replace(" alerts", "").replace(" ", "-")
        regions.append({"name": clean_text(title).replace(" alerts", ""), "title": clean_text(title), "slug": slug, "url": url or final_url})
    if not regions:
        die("could not find DOC alert regions on the alerts index page")
    return regions


def resolve_region(region: str) -> dict[str, Any]:
    needle = region.strip().lower()
    regions = fetch_alert_regions()
    for item in regions:
        if needle in {item["slug"].lower(), item["name"].lower(), item["title"].lower()}:
            return item
    for item in regions:
        if needle in item["slug"].lower() or needle in item["name"].lower() or needle in item["title"].lower():
            return item
    names = ", ".join(item["slug"] for item in regions)
    die(f"unknown DOC alert region {region!r}; available: {names}")


def extract_meta_description(page_html: str) -> str:
    for match in re.finditer(r"<meta\b([^>]*)>", page_html, flags=re.I):
        attrs = match.group(1)
        name = (attr_value(attrs, "name") or attr_value(attrs, "property") or "").lower()
        if name in {"description", "og:description"}:
            return clean_text(attr_value(attrs, "content"))
    return ""


def extract_first_tag(page_html: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", page_html, flags=re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def extract_page_paragraphs(page_html: str, limit: int = 4) -> list[str]:
    main = page_html.split("<main", 1)[1] if "<main" in page_html else page_html
    paragraphs = []
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", main, flags=re.I | re.S):
        text = clean_text(match.group(1))
        if len(text) >= 40 and text not in paragraphs:
            paragraphs.append(text)
        if len(paragraphs) >= limit:
            break
    return paragraphs


def summarize_doc_page(url: str) -> dict[str, Any]:
    page_html, final_url = request_text(url)
    main_html = page_html.split("<main", 1)[1] if "<main" in page_html else page_html
    title = extract_first_tag(page_html, "title")
    h1 = extract_first_tag(main_html, "h1")
    meta_description = extract_meta_description(page_html)
    paragraphs = extract_page_paragraphs(page_html)
    alert_groups = fetch_alert_groups_from_html(page_html, final_url)
    return {
        "url": final_url,
        "title": title,
        "name": h1 or title,
        "description": meta_description or (paragraphs[0] if paragraphs else ""),
        "paragraphs": paragraphs,
        "alert_group_count": len(alert_groups),
        "alerts_count": sum(group.get("alert_count", 0) for group in alert_groups),
        "alert_groups": alert_groups,
    }


def resolve_track(query: str) -> dict[str, Any]:
    gw_payload = get_great_walk_payload()
    great_walk = resolve_great_walk(query, gw_payload, required=False)
    if great_walk:
        description = great_walk.get("Description") or ""
        return {
            "source": "great_walk",
            "match": normalize_great_walk(great_walk),
            "doc_url": extract_doc_link(description),
            "description": clean_text(description),
        }
    matches = search_places(query)
    if matches:
        match = matches[0]
        return {
            "source": "booking_place",
            "match": match,
            "doc_url": match.get("doc_url"),
            "description": match.get("description") or "",
        }
    die(f"could not resolve a DOC Great Walk or booking place matching {query!r}")


def cmd_great_walks(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = get_great_walk_payload()
    walks = [normalize_great_walk(item) for item in payload.get("GWPlaceData") or [] if isinstance(item, dict)]
    data = {
        "source": "Department of Conservation booking system",
        "booking_window": {
            "start": date_only(payload.get("FutureBookingStartDate")),
            "end": date_only(payload.get("FutureBookingEndDate")),
        },
        "count": len(walks),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "great_walks": walks,
        "booking_url": BOOKING_WEB,
    }
    emit(data, args.json, print_great_walks)


def cmd_huts(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    if args.great_walk:
        payload = get_great_walk_payload()
        place = resolve_great_walk(args.great_walk, payload)
        data = availability_for_place(place, args, payload)
        data["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        emit(data, args.json, print_availability)
        return
    places = [normalize_place(item) for item in popular_places()]
    if args.query:
        needle = args.query.lower()
        places = [p for p in places if needle in f"{p.get('name')} {p.get('description')} {p.get('entity_type')}".lower()]
    if args.region:
        needle = args.region.lower()
        places = [p for p in places if needle in f"{p.get('name')} {p.get('description')}".lower()]
    total = len(places)
    places = places[: args.limit]
    data = {
        "source": "Department of Conservation booking popular places",
        "query": args.query,
        "region_filter": args.region,
        "total_matches": total,
        "returned": len(places),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "places": places,
        "booking_url": BOOKING_WEB,
    }
    emit(data, args.json, print_places)


def cmd_availability(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = get_great_walk_payload()
    place = resolve_great_walk(args.target, payload, required=False)
    facility_id = None
    if place is None:
        facility_id = int_or_none(args.target)
        if facility_id is None:
            die("availability currently supports Great Walk names/place ids or Great Walk facility ids")
        found_place, _meta, accommodation, direction, start, nights = find_facility_place(facility_id, args, payload)
        raw = get_great_walk_facilities(found_place, get_great_walk_meta(found_place.get("PlaceId")), start, nights, accommodation, direction)
        data = normalize_availability(found_place, {}, start, nights, accommodation, direction, raw, facility_id=facility_id)
    else:
        data = availability_for_place(place, args, payload)
    data["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    emit(data, args.json, print_availability)


def cmd_alerts(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    if not args.region:
        regions = fetch_alert_regions()
        data = {
            "source": "Department of Conservation alerts index",
            "count": len(regions),
            "returned": min(len(regions), args.limit),
            "regions": regions[: args.limit],
            "note": "Pass --region <slug> to fetch current alert groups for a region.",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
        emit(data, args.json, print_alert_regions)
        return
    region = resolve_region(args.region)
    page_html, final_url = request_text(region["url"])
    groups = fetch_alert_groups_from_html(page_html, final_url)
    total_groups = len(groups)
    groups = groups[: args.limit]
    data = {
        "source": "Department of Conservation current alerts",
        "region": region,
        "url": final_url,
        "total_groups": total_groups,
        "returned_groups": len(groups),
        "alerts_count": sum(group.get("alert_count", 0) for group in groups),
        "groups": groups,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    emit(data, args.json, print_alerts)


def cmd_track(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    match = resolve_track(args.name)
    page = summarize_doc_page(match["doc_url"]) if match.get("doc_url") else None
    data = {
        "source": "Department of Conservation",
        "query": args.name,
        "match_source": match["source"],
        "match": match["match"],
        "doc_url": match.get("doc_url"),
        "description": match.get("description"),
        "page": page,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    emit(data, args.json, print_track)


def print_great_walks(data: dict[str, Any]) -> None:
    window = data.get("booking_window") or {}
    print(f"Great Walks booking window: {window.get('start')} to {window.get('end')}")
    print(f"{data.get('count', 0)} Great Walks ({data.get('elapsed_ms')} ms)")
    print()
    for walk in data.get("great_walks") or []:
        fixed = ""
        if walk.get("fixed_itinerary"):
            fixed = f" | fixed {walk.get('fixed_min_nights')}-{walk.get('fixed_max_nights')} nights"
        print(f"{walk.get('place_id'):>4}  {walk.get('name')} | {walk.get('status')}{fixed}")
        if walk.get("doc_url"):
            print(f"      {walk.get('doc_url')}")


def print_places(data: dict[str, Any]) -> None:
    print(f"DOC booking places: {data.get('returned')} of {data.get('total_matches')} matches ({data.get('elapsed_ms')} ms)")
    print()
    for place in data.get("places") or []:
        print(f"{place.get('place_id'):>4}  {place.get('name')}")
        bits = []
        if place.get("entity_type"):
            bits.append(str(place.get("entity_type")))
        if place.get("available_unit_count") is not None:
            bits.append(f"{place.get('available_unit_count')} available units")
        if bits:
            print("      " + " | ".join(bits))
        if place.get("description"):
            print(f"      {truncate(place.get('description'), 140)}")
        if place.get("doc_url"):
            print(f"      {place.get('doc_url')}")


def print_availability(data: dict[str, Any]) -> None:
    place = data.get("place") or {}
    accommodation = data.get("accommodation") or {}
    direction = data.get("direction") or {}
    print(f"{place.get('name')} availability: {accommodation.get('name')} from {data.get('start_date')} for {data.get('nights')} night(s)")
    if direction:
        print(f"Direction: {direction.get('name')}")
    print(f"{data.get('facility_count', 0)} facilities ({data.get('elapsed_ms', '?')} ms)")
    print()
    for facility in data.get("facilities") or []:
        print(f"{facility.get('facility_id'):>5}  {facility.get('name')} ({facility.get('category')}, capacity {facility.get('capacity')})")
        for item in facility.get("dates") or []:
            if not item.get("is_season_available"):
                status = "out of season"
            elif not item.get("is_available"):
                status = "closed"
            else:
                status = f"{item.get('total_available')} spaces"
            print(f"       {item.get('date')}: {status}")


def print_alert_regions(data: dict[str, Any]) -> None:
    print(f"DOC alert regions: {data.get('returned')} of {data.get('count')}")
    print()
    for region in data.get("regions") or []:
        print(f"{region.get('slug'):>24}  {region.get('title')}")
        print(f"                          {region.get('url')}")


def print_alerts(data: dict[str, Any]) -> None:
    region = data.get("region") or {}
    print(f"{region.get('title') or region.get('name')}: {data.get('returned_groups')} of {data.get('total_groups')} alert groups")
    print(f"{data.get('alerts_count')} alerts returned ({data.get('elapsed_ms')} ms)")
    print()
    for group in data.get("groups") or []:
        print(group.get("name"))
        if group.get("url"):
            print(f"  {group.get('url')}")
        for alert in group.get("alerts") or []:
            date = alert.get("display_date") or alert.get("sort_date") or ""
            suffix = f" ({date})" if date else ""
            print(f"  - {alert.get('summary')}{suffix}")
            if alert.get("description"):
                print(f"    {truncate(alert.get('description'), 180)}")


def print_track(data: dict[str, Any]) -> None:
    page = data.get("page") or {}
    match = data.get("match") or {}
    print(page.get("name") or match.get("name") or data.get("query"))
    if data.get("doc_url"):
        print(data.get("doc_url"))
    description = page.get("description") or data.get("description")
    if description:
        print()
        print(truncate(description, 300))
    if page:
        print()
        print(f"Alerts: {page.get('alerts_count', 0)} across {page.get('alert_group_count', 0)} group(s)")
        for group in page.get("alert_groups") or []:
            for alert in group.get("alerts") or []:
                date = alert.get("display_date") or alert.get("sort_date") or ""
                suffix = f" ({date})" if date else ""
                print(f"- {alert.get('summary')}{suffix}")


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def add_availability_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="from_date", help="arrival/start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="checkout/end date YYYY-MM-DD; converted to nights")
    parser.add_argument("--nights", type=int, help="number of nights when --to is not supplied")
    parser.add_argument("--accommodation", help="Great Walk accommodation name, usually Hut or campsite")
    parser.add_argument("--direction", help="Great Walk direction id or name when the walk supports directions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only DOC NZ huts, Great Walk availability, alerts, and track lookup CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    great_walks = sub.add_parser("great-walks", help="list Great Walks and current booking status")
    add_json(great_walks)
    great_walks.set_defaults(func=cmd_great_walks)

    huts = sub.add_parser("huts", help="list DOC bookable huts/campsites or Great Walk facilities")
    huts.add_argument("--region", help="client-side text filter over place descriptions")
    huts.add_argument("--query", help="client-side text filter over place names and descriptions")
    huts.add_argument("--great-walk", help="Great Walk name/place id; returns hut/campsite facility ids and availability")
    huts.add_argument("--limit", type=int, default=20, help="maximum places to return for listing mode")
    add_availability_flags(huts)
    add_json(huts)
    huts.set_defaults(func=cmd_huts)

    availability = sub.add_parser("availability", help="Great Walk availability by walk name/place id or facility id")
    availability.add_argument("target", help="Great Walk name/place id, or a facility id from `huts --great-walk`")
    add_availability_flags(availability)
    add_json(availability)
    availability.set_defaults(func=cmd_availability)

    alerts = sub.add_parser("alerts", help="current DOC alert regions or region alert groups")
    alerts.add_argument("--region", help="DOC alerts region slug/name, e.g. fiordland or canterbury")
    alerts.add_argument("--limit", type=int, default=20, help="maximum regions or alert groups to return")
    add_json(alerts)
    alerts.set_defaults(func=cmd_alerts)

    track = sub.add_parser("track", help="track description and page-level alerts")
    track.add_argument("name", help="Great Walk or DOC booking place name")
    add_json(track)
    track.set_defaults(func=cmd_track)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) is not None and getattr(args, "limit", 1) < 1:
        die("--limit must be at least 1")
    if getattr(args, "nights", None) is not None and args.nights < 1:
        die("--nights must be at least 1")
    args.func(args)


if __name__ == "__main__":
    main()
