#!/usr/bin/env python3
"""NZ Post CLI -- track parcels, find locations, and look up addresses via public NZ Post APIs.

Self-contained stdlib wrapper. No authentication required.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://tools.nzpost.co.nz/tracking/api"
API_PARCELS = "/parceltrack/parcels"

LOCATIONS_API_BASE = "https://api.nzpost.co.nz/digital/postshop-locations/v2"
ADDRESS_API = "https://tools.nzpost.co.nz/legacy/api/suggest"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"
REFERER = "https://www.nzpost.co.nz/tools/tracking"
ADDRESS_REFERER = "https://www.nzpost.co.nz/tools/address-postcode-finder"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "nzpost-skill/1.0 (mail@adamholt.co.nz)"

# Simplified regex covering common NZ Post domestic and international formats.
# Full pattern is available from the tracking-masks endpoint; this covers typical use.
TRACKING_RE = re.compile(
    r"^("
    r"\d{5,6}"                       # 5-6 digit domestic short codes
    r"|\d{8}"                        # 8 digit
    r"|[A-Z0-9]{10}"                 # 10-char alphanumeric
    r"|[A-Z]{2}\d{9}[A-Z]{2}"       # UPU international (e.g. EA123456789NZ)
    r"|[A-Z0-9]{20}"                 # 20-char alphanumeric
    r"|[A-Z0-9]{3}\d{7}"            # 3-letter prefix + 7 digits
    r"|[A-Z0-9]{5}\d{7}"            # 5-char prefix + 7 digits
    r"|[A-Z0-9]{24}"                 # 24-char
    r"|\d{10,14}"                    # 10-14 digits
    r"|\d{18}"                       # 18 digits
    r"|\d{20}"                       # 20 digits
    r"|\d{22}"                       # 22 digits
    r"|\d{30}"                       # 30 digits
    r"|[A-Z]{3}\d{8}"               # 3-letter + 8 digits
    r"|[A-Z]{2}\d{11}"              # 2-letter + 11 digits
    r"|TP[A-Z0-9]{16}"              # TP prefix 18-char
    r"|TPW\d{10}"                    # TPW + 10 digits
    r"|(RMA|RMC|RMP)\d{10}"         # RMA/RMC/RMP + 10 digits
    r"|CTC\d{8}"                     # CTC + 8 digits
    r"|SUN\d{10}"                    # SUN + 10 digits
    r"|MFB\d{17}[A-Z]{2}"           # MFB + 17 digits + 2 letters
    r")",
    re.IGNORECASE,
)

# Location type filter mapping (CLI value -> API type string fragment).
# The filter uses case-insensitive substring matching so "Postbox" matches
# both "Postbox" and "Postbox Lobby" from the real API.
LOCATION_TYPES = {
    "postshop": "PostShop",
    "parcel-collect": "Third Party Partner",
    "postbox": "Postbox",
    "all": None,
}

MAX_TRACKING_REFS = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(message: str, code: int = 1) -> None:
    print(f"nzpost: {message}", file=sys.stderr)
    raise SystemExit(code)


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Safely convert value to float, returning default if None or invalid."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_str(v: Any, default: str = "") -> str:
    """Safely convert value to str, returning default if None."""
    if v is None:
        return default
    return str(v)


def strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)


def clean_text(text: Any) -> str:
    """Sanitise an untrusted string field before display.

    Strips HTML tags, decodes HTML entities, removes terminal control
    characters that could spoof output, and trims whitespace.
    """
    if text is None:
        return ""
    s = strip_html(str(text))
    s = html.unescape(s)
    s = _CONTROL_CHARS_RE.sub("", s)
    return s.strip()


def validate_tracking_number(tn: str) -> str:
    """Validate and normalise a tracking number. Returns cleaned string or exits."""
    cleaned = tn.strip().upper()
    if not cleaned:
        die("tracking number cannot be empty")
    if not TRACKING_RE.fullmatch(cleaned):
        die(
            f"unrecognised tracking number format: {tn!r}\n"
            "  NZ Post tracking numbers are typically numeric references or alphanumeric codes."
        )
    return cleaned


def _http_get(url: str, headers: dict[str, str], timeout: int = 15) -> str:
    """Perform a GET request and return decoded body, or call die() on error."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


# ---------------------------------------------------------------------------
# Tracking API
# ---------------------------------------------------------------------------

def fetch_tracking_multi(tracking_references: list[str], timeout: int = 15) -> dict[str, Any]:
    """Fetch tracking data for one or more tracking references. Returns parsed JSON."""
    params = "&".join(
        f"tracking_reference={urllib.parse.quote(ref)}" for ref in tracking_references
    )
    url = f"{API_BASE}{API_PARCELS}?{params}"
    headers = {
        "User-Agent": UA,
        "Referer": REFERER,
        "Content-Type": "application/json",
    }
    raw = _http_get(url, headers, timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from tracking API: {e}")


def extract_api_error(results: Any) -> str | None:
    """Return a concise API error from a results payload, if present."""
    if not isinstance(results, list):
        return None
    messages: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        errors = result.get("errors")
        if not isinstance(errors, list):
            continue
        for err in errors:
            if not isinstance(err, dict):
                continue
            message = err.get("details") or err.get("message") or err.get("code")
            if message is not None:
                messages.append(_safe_str(message))
    if messages:
        return "; ".join(messages)
    return None


# ---------------------------------------------------------------------------
# Locations API
# ---------------------------------------------------------------------------

def _geocode_via_keyword(query: str, timeout: int = 15) -> tuple[float, float] | None:
    """Try NZ Post locations KEYWORD API for geocoding. Returns (lat, lng) if found, else None."""
    params = urllib.parse.urlencode({"type": "KEYWORD", "value": query, "max": 1})
    url = f"{LOCATIONS_API_BASE}/locations?{params}"
    headers = {"User-Agent": UA, "Referer": REFERER}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        data = json.loads(raw)
    except Exception:
        return None

    locations = data.get("locations", []) if isinstance(data, dict) else []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is not None and lng is not None:
            try:
                return float(lat), float(lng)
            except (ValueError, TypeError):
                continue
    return None


def _geocode_via_nominatim(query: str, timeout: int = 15) -> tuple[float, float] | None:
    """Fall back to OpenStreetMap Nominatim for geocoding. Returns (lat, lng) or None."""
    params = urllib.parse.urlencode({
        "q": f"{query},New Zealand",
        "format": "json",
        "limit": 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    headers = {
        "User-Agent": NOMINATIM_UA,
        "Accept-Language": "en",
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        results = json.loads(raw)
    except Exception:
        return None

    if not results or not isinstance(results, list):
        return None
    first = results[0]
    try:
        return float(first["lat"]), float(first["lon"])
    except (KeyError, ValueError, TypeError):
        return None


def geocode_near(query: str, timeout: int = 15) -> tuple[float, float]:
    """Geocode a place-name query. Tries NZ Post KEYWORD first, then Nominatim."""
    coords = _geocode_via_keyword(query, timeout)
    if coords:
        return coords
    coords = _geocode_via_nominatim(query, timeout)
    if coords:
        return coords
    die(f"could not geocode location: {query!r}. Try --lat/--lon instead.")


def fetch_locations_by_coords(lat: float, lng: float, max_results: int = 10, timeout: int = 15) -> list[dict[str, Any]]:
    """Fetch NZ Post locations near lat/lng. Returns list of location dicts."""
    value = json.dumps({"latitude": lat, "longitude": lng})
    params = urllib.parse.urlencode({"type": "NEARBY", "value": value, "max": max_results})
    url = f"{LOCATIONS_API_BASE}/locations?{params}"
    headers = {"User-Agent": UA, "Referer": REFERER}
    raw = _http_get(url, headers, timeout)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from locations API: {e}")
    return data.get("locations", []) if isinstance(data, dict) else []


def fetch_locations_by_keyword(keyword: str, max_results: int = 10, timeout: int = 15) -> list[dict[str, Any]]:
    """Fetch NZ Post locations by keyword. Returns list of location dicts."""
    params = urllib.parse.urlencode({"type": "KEYWORD", "value": keyword, "max": max_results})
    url = f"{LOCATIONS_API_BASE}/locations?{params}"
    headers = {"User-Agent": UA, "Referer": REFERER}
    raw = _http_get(url, headers, timeout)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from locations API: {e}")
    return data.get("locations", []) if isinstance(data, dict) else []


def filter_locations_by_type(locations: list[dict[str, Any]], loc_type: str | None) -> list[dict[str, Any]]:
    """Filter location list by type string (case-insensitive substring match). None means all."""
    if not loc_type:
        return locations
    type_lower = loc_type.lower()
    return [
        loc for loc in locations
        if type_lower in _safe_str(loc.get("type", "")).lower()
    ]


def _today_hours(loc: dict[str, Any]) -> str:
    """Extract today's opening hours from a location dict."""
    now = datetime.now(ZoneInfo("Pacific/Auckland"))
    weekday = now.weekday()  # 0=Monday, 6=Sunday, matches API day field
    hours = loc.get("hours", [])
    if not isinstance(hours, list) or not hours:
        return "hours unknown"
    for entry in hours:
        if not isinstance(entry, dict):
            continue
        if entry.get("day") == weekday:
            if entry.get("closed"):
                return "closed today"
            open_t = entry.get("open")
            close_t = entry.get("close")
            if open_t and close_t:
                return f"{open_t} - {close_t}"
            return "hours unknown"
    return "closed today"


def fmt_distance(dist_m: float) -> str:
    """Format a distance in metres to human-readable string."""
    if dist_m >= 1000:
        return f"{dist_m / 1000:.1f} km"
    return f"{dist_m:.0f} m"


# ---------------------------------------------------------------------------
# Address API
# ---------------------------------------------------------------------------

def fetch_addresses(query: str, limit: int = 10, timeout: int = 15) -> list[dict[str, Any]]:
    """Fetch NZ Post address suggestions. Returns list of address dicts."""
    params = urllib.parse.urlencode({"q": query, "max": limit})
    url = f"{ADDRESS_API}?{params}"
    headers = {
        "User-Agent": UA,
        "Referer": ADDRESS_REFERER,
        "Accept": "application/json",
    }
    raw = _http_get(url, headers, timeout)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from address API: {e}")
    if not isinstance(data, dict):
        die("unexpected response from address API")
    if not data.get("success"):
        die(f"address API returned failure: {data}")
    return data.get("addresses", [])


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_banner() -> None:
    print("NZ Post Tracking")
    print("================")


def fmt_datetime(dt: str | None) -> str:
    """Format ISO datetime string to a human-readable local-style string."""
    if not dt:
        return "unknown"
    # dt is UTC e.g. "2026-03-12T20:34:07Z"
    try:
        d, t = dt.rstrip("Z").split("T")
        year, mon, day = d.split("-")
        hour, minute, _ = t.split(":")
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mon_name = months[int(mon) - 1]
        return f"{day} {mon_name} {year} {hour}:{minute} UTC"
    except Exception:
        return dt


def emit_human(tracking_reference: str, events: list[dict[str, Any]]) -> None:
    """Print human-readable tracking output."""
    print_banner()
    print(f"Tracking: {tracking_reference}")
    print()

    if not events:
        print("  No tracking events found.")
        return

    # Latest event = last in list
    latest = events[-1]
    latest_status = clean_text(latest.get("status")) or "Unknown"
    latest_dt = fmt_datetime(latest.get("date_time"))
    latest_desc = clean_text(latest.get("description"))
    latest_depot = clean_text(latest.get("depot_name"))

    print(f"Status:   {latest_status}")
    print(f"Updated:  {latest_dt}")
    if latest_depot:
        print(f"Location: {latest_depot}")
    if latest_desc:
        print(f"Detail:   {latest_desc}")
    print()
    print(f"Events ({len(events)} total):")
    print()

    for ev in events:
        dt = fmt_datetime(ev.get("date_time"))
        status = clean_text(ev.get("status"))
        depot = clean_text(ev.get("depot_name"))
        run = clean_text(ev.get("run_name"))
        loc_parts = [p for p in [depot, run] if p]
        loc_str = f"  [{', '.join(loc_parts)}]" if loc_parts else ""
        print(f"  {dt}  {status}{loc_str}")


def _parcel_record(tracking_reference: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a parcel JSON record from events list."""
    latest = events[-1] if events else {}
    return {
        "tracking_reference": tracking_reference,
        "status": clean_text(latest.get("status")),
        "last_updated": _safe_str(latest.get("date_time"), ""),
        "last_depot": clean_text(latest.get("depot_name")) or None,
        "event_count": len(events),
        "events": [
            {
                "date_time": ev.get("date_time"),
                "status": clean_text(ev.get("status")),
                "description": clean_text(ev.get("description")),
                "depot_name": clean_text(ev.get("depot_name")) or None,
                "run_name": clean_text(ev.get("run_name")) or None,
                "edifact_code": ev.get("edifact_code"),
                "seqref": ev.get("seqref"),
            }
            for ev in events
        ],
    }


def _error_parcel_record(tracking_reference: str, error: str) -> dict[str, Any]:
    """Build an error parcel JSON record."""
    return {
        "tracking_reference": tracking_reference,
        "status": "error",
        "last_updated": "",
        "last_depot": None,
        "event_count": 0,
        "error": error,
        "events": [],
    }


def _not_found_parcel_record(tracking_reference: str) -> dict[str, Any]:
    """Build a not-found parcel JSON record."""
    return {
        "tracking_reference": tracking_reference,
        "status": "not found",
        "last_updated": "",
        "last_depot": None,
        "event_count": 0,
        "events": [],
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_track(args: argparse.Namespace) -> None:
    """Track one or more parcels by tracking number."""
    # M4: dedup preserving first-seen order
    seen: set[str] = set()
    unique_raw: list[str] = []
    for n in args.numbers:
        if n not in seen:
            unique_raw.append(n)
            seen.add(n)
    if len(unique_raw) < len(args.numbers):
        duped = len(args.numbers) - len(unique_raw)
        print(f"nzpost: note: {duped} duplicate tracking number(s) removed", file=sys.stderr)

    refs = [validate_tracking_number(n) for n in unique_raw]

    # M7: cap at MAX_TRACKING_REFS after dedup
    if len(refs) > MAX_TRACKING_REFS:
        die(
            f"too many tracking numbers (got {len(refs)}, max {MAX_TRACKING_REFS})."
            " Run multiple commands instead."
        )

    data = fetch_tracking_multi(refs)

    if not isinstance(data, dict):
        die("unexpected tracking API response: top-level JSON is not an object")

    results = data.get("results")
    status_code = data.get("status_code")

    if not isinstance(results, list):
        if not args.json:
            print_banner()
        die("unexpected tracking API response: results is not a list")

    # M3: build ref -> (record, events, error) maps from API response
    ref_records: dict[str, dict[str, Any]] = {}
    ref_events: dict[str, list[dict[str, Any]]] = {}
    ref_errors: dict[str, str] = {}

    for parcel in results:
        if not isinstance(parcel, dict):
            continue
        ref = _safe_str(parcel.get("tracking_reference", ""))
        parcel_errors = parcel.get("errors")
        if parcel_errors and isinstance(parcel_errors, list) and len(parcel_errors) > 0:
            err_msg = None
            for e in parcel_errors:
                if isinstance(e, dict):
                    err_msg = _safe_str(e.get("details") or e.get("message") or e.get("code", "error"))
                    break
            err_msg = err_msg or "lookup failed"
            ref_errors[ref] = err_msg
            ref_records[ref] = _error_parcel_record(ref, err_msg)
            continue

        events = parcel.get("tracking_events")
        if not isinstance(events, list):
            events = []
        ref_events[ref] = events
        ref_records[ref] = _parcel_record(ref, events)

    # Single-ref path: check success/error before emitting
    if len(refs) == 1:
        ref = refs[0]
        if data.get("success") is not True or status_code != 1:
            api_error = extract_api_error(results)
            suffix = f": {api_error}" if api_error else ""
            if not args.json:
                print_banner()
            die(f"tracking lookup failed (status_code={status_code}){suffix}")

        if ref in ref_errors:
            if not args.json:
                print_banner()
            die(f"tracking lookup failed: {ref_errors[ref]}")

        events = ref_events.get(ref, [])

        if not events:
            if not args.json:
                print_banner()
            die(f"no tracking events found for: {ref}")

        # M5: single-ref JSON always emits {"parcels": [...]}
        if args.json:
            print(json.dumps({"parcels": [ref_records[ref]]}, indent=2, ensure_ascii=False))
        else:
            emit_human(ref, events)
        return

    # Multi-parcel path: emit in input order (M3), not API order
    parcel_records: list[dict[str, Any]] = []
    human_sections: list[tuple[str, list[dict[str, Any]], str | None]] = []

    for ref in refs:
        if ref in ref_errors:
            parcel_records.append(ref_records[ref])
            human_sections.append((ref, [], ref_errors[ref]))
        elif ref in ref_events:
            parcel_records.append(ref_records[ref])
            human_sections.append((ref, ref_events[ref], None))
        else:
            # Ref was not in API response -- emit explicit not-found slot
            parcel_records.append(_not_found_parcel_record(ref))
            human_sections.append((ref, [], "not found"))

    if args.json:
        print(json.dumps({"parcels": parcel_records}, indent=2, ensure_ascii=False))
    else:
        for i, (ref, events, error) in enumerate(human_sections):
            if i > 0:
                print()
                print("---")
                print()
            if error:
                print(f"Tracking: {ref}")
                print(f"Error:    {error}")
            else:
                emit_human(ref, events)


def cmd_locations(args: argparse.Namespace) -> None:
    """Find NZ Post locations near a place, coordinates, or by keyword."""
    limit = args.limit

    # When filtering by type, over-fetch so the filter has enough to work with.
    # PostShops and other types can be sparse near high-density urban areas.
    type_filter = None
    if args.type and args.type != "all":
        type_filter = LOCATION_TYPES.get(args.type)
    fetch_limit = limit if not type_filter else max(limit * 10, 100)

    if args.near:
        lat, lng = geocode_near(args.near)
        locations = fetch_locations_by_coords(lat, lng, max_results=fetch_limit)
    elif args.lat is not None and args.lon is not None:
        locations = fetch_locations_by_coords(args.lat, args.lon, max_results=fetch_limit)
    elif args.keyword:
        locations = fetch_locations_by_keyword(args.keyword, max_results=fetch_limit)
    else:
        die("specify one of --near, --lat/--lon, or --keyword")

    locations = filter_locations_by_type(locations, type_filter)

    # Sort by distance ascending, then truncate to requested limit
    locations = sorted(locations, key=lambda x: _safe_float(x.get("distance_in_m"), 0.0))
    locations = locations[:limit]

    if args.json:
        print(json.dumps({"locations": locations}, indent=2, ensure_ascii=False))
        return

    # Human output
    if not locations:
        print("No locations found.")
        return

    for i, loc in enumerate(locations, 1):
        name = clean_text(loc.get("name", ""))
        dist_m = _safe_float(loc.get("distance_in_m"), 0.0)
        dist_str = fmt_distance(dist_m) if dist_m > 0 else ""
        addr_details = loc.get("address_details", {})
        if isinstance(addr_details, dict):
            addr_parts = [
                addr_details.get("street_address", ""),
                addr_details.get("suburb", ""),
                addr_details.get("city", ""),
            ]
            address = ", ".join(clean_text(p) for p in addr_parts if p)
        else:
            address = clean_text(loc.get("address", ""))
        loc_type = clean_text(loc.get("type", ""))
        hours = _today_hours(loc)

        header = f"{i}. {name}"
        if dist_str:
            header += f" ({dist_str})"
        print(header)
        if address:
            print(f"   {address}")
        if loc_type:
            print(f"   Type: {loc_type}")
        print(f"   Today: {hours}")
        print()


def cmd_address(args: argparse.Namespace) -> None:
    """Look up NZ addresses and postcodes."""
    addresses = fetch_addresses(args.query, limit=args.limit)

    if args.json:
        print(json.dumps({"addresses": addresses}, indent=2, ensure_ascii=False))
        return

    if not addresses:
        print("No addresses found.")
        return

    for i, addr in enumerate(addresses, 1):
        full = clean_text(addr.get("FullAddress", ""))
        dpid = _safe_str(addr.get("DPID", ""))
        if dpid:
            print(f"{i}. {full}  (DPID: {dpid})")
        else:
            print(f"{i}. {full}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="NZ Post -- track parcels, find locations, and look up addresses via public NZ Post APIs"
    )
    sub = ap.add_subparsers(dest="command")

    # track
    sp_track = sub.add_parser("track", help="track one or more parcels by tracking number")
    sp_track.add_argument(
        "numbers",
        nargs="+",
        metavar="NUMBER",
        help="NZ Post tracking number(s) (e.g. 00794210392715622565)",
    )
    sp_track.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sp_track.set_defaults(func=cmd_track)

    # locations
    sp_loc = sub.add_parser("locations", help="find nearby NZ Post locations")
    loc_group = sp_loc.add_mutually_exclusive_group()
    loc_group.add_argument("--near", metavar="TEXT", help="place name to search near (geocoded)")
    loc_group.add_argument("--keyword", metavar="TEXT", help="keyword search for locations")
    sp_loc.add_argument("--lat", type=float, metavar="LAT", help="latitude (use with --lon)")
    sp_loc.add_argument("--lon", type=float, metavar="LON", help="longitude (use with --lat)")
    sp_loc.add_argument("--limit", type=int, default=10, help="max results (default 10)")
    sp_loc.add_argument(
        "--type",
        choices=list(LOCATION_TYPES.keys()),
        default="all",
        help="filter by location type",
    )
    sp_loc.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sp_loc.set_defaults(func=cmd_locations)

    # address
    sp_addr = sub.add_parser("address", help="look up NZ delivery addresses and postcodes")
    sp_addr.add_argument("query", help="address query string (e.g. 'Papakura')")
    sp_addr.add_argument("--limit", type=int, default=10, help="max results (default 10)")
    sp_addr.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sp_addr.set_defaults(func=cmd_address)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
