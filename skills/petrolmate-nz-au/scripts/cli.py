#!/usr/bin/env python3
"""PetrolMate CLI — AU & NZ fuel price lookup via petrolmate.com.au public API.

Self-contained stdlib wrapper around PetrolMate's public API.
Covers AU (state FuelCheck data) and NZ (Gaspy data). No auth required.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://petrolmate.com.au"
API_NEARBY = "/api/stations/nearby"
API_GEOIP = "/api/geoip"
API_GEOCODE = "/api/geocode/search"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0"

FUEL_TYPES: dict[str, str] = {
    "ULP": "Unleaded 91",
    "E10": "E10",
    "PULP95": "Premium 95",
    "PULP98": "Premium 98",
    "PREMIUM": "Premium (95+98)",
    "DIESEL": "Diesel",
    "PDIESEL": "Premium Diesel",
    "DIESEL_PREMIUM": "Premium Diesel",
    "LPG": "LPG",
    "E85": "E85",
    "B20": "Biodiesel B20",
}

FUEL_CODE_LABELS: dict[str, str] = {
    "Unleaded Petrol": "ULP 91",
    "Ethanol 10%": "E10",
    "Premium Unleaded 95": "PULP 95",
    "Premium Unleaded 98": "PULP 98",
    "Diesel": "Diesel",
    "Premium Diesel": "PDiesel",
    "LPG/Autogas": "LPG",
    "Ethanol 85%": "E85",
}

# Common AU + NZ locations (PetrolMate handles geocoding, these are fallbacks)
LOCATIONS: dict[str, tuple[float, float]] = {
    "auckland": (-36.8485, 174.7633),
    "auckland cbd": (-36.8485, 174.7633),
    "st heliers": (-36.85, 174.85),
    "wellington": (-41.2865, 174.7762),
    "christchurch": (-43.5321, 172.6362),
    "queenstown": (-45.0312, 168.6626),
    "hamilton": (-37.7870, 175.2793),
    "tauranga": (-37.6878, 176.1651),
    "dunedin": (-45.8788, 170.5028),
    "napier": (-39.4928, 176.9120),
    "palmerston north": (-40.3523, 175.6083),
    "rotorua": (-38.1368, 176.2497),
    "new plymouth": (-39.0556, 174.0752),
    "whangarei": (-35.7251, 174.3237),
    "nelson": (-41.2706, 173.2840),
    "invercargill": (-46.4132, 168.3538),
    "gisborne": (-38.6623, 178.0176),
    "sydney": (-33.8688, 151.2093),
    "melbourne": (-37.8136, 144.9631),
    "brisbane": (-27.4698, 153.0251),
    "perth": (-31.9505, 115.8605),
    "adelaide": (-34.9285, 138.6007),
    "hobart": (-42.8821, 147.3272),
    "canberra": (-35.2809, 149.1300),
    "darwin": (-12.4634, 130.8456),
    "gold coast": (-28.0167, 153.4000),
    "sunshine coast": (-26.6500, 153.0667),
    "newcastle": (-32.9283, 151.7817),
    "wollongong": (-34.4278, 150.8931),
    "geelong": (-38.1499, 144.3617),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(message: str, code: int = 1) -> None:
    print(f"petrolmate: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, params: dict[str, Any], timeout: int = 15) -> Any:
    """GET PetrolMate API and return parsed JSON."""
    qs = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    url = f"{API_BASE}{path}?{qs}"
    headers = {
        "Accept": "application/json",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def _safe_float(v: Any, default: float) -> float:
    return float(v) if v is not None else default


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_price(cents: str | float | None) -> str:
    """Format price in cents to dollars."""
    try:
        return f"${float(cents) / 100:.3f}"
    except (ValueError, TypeError):
        return "-"


def fmt_dist(meters: float | None) -> str:
    """Format distance in human-readable form."""
    if meters is None:
        return "?"
    if meters >= 1000:
        return f"{meters / 1000:.1f}km"
    return f"{int(meters)}m"


def fmt_age(hours_str: str | None) -> str:
    """Format hours_old as a friendly age string."""
    try:
        h = float(hours_str)
        if h < 1:
            return f"{int(h * 60)}m ago"
        elif h < 24:
            return f"{h:.0f}h ago"
        else:
            return f"{h / 24:.0f}d ago"
    except (ValueError, TypeError):
        return "?"


def fuel_label(fuel_name: str | None, fuel_code: str | None = None) -> str:
    """Map API fuel_name to a short label."""
    if fuel_name and fuel_name in FUEL_CODE_LABELS:
        return FUEL_CODE_LABELS[fuel_name]
    return fuel_code or "?"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def api_geoip() -> dict[str, Any]:
    """Get approximate location from IP."""
    data = request_json(API_GEOIP, {})
    if not data or not data.get("success"):
        die("geoip lookup failed")
    return data


def api_geocode(address: str) -> dict[str, Any]:
    """Geocode an address."""
    data = request_json(API_GEOCODE, {"q": address})
    if not data or not data.get("success") or not data.get("results"):
        die(f"could not geocode: {address}")
    return data["results"][0]


def api_stations(
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    fuel_type: str = "ULP",
    limit: int = 20,
    brand: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch stations within radius_km of (lat, lon)."""
    radius_m = int(min(radius_km, 50) * 1000)
    params: dict[str, Any] = {
        "lat": lat,
        "lng": lon,
        "radius": radius_m,
        "fuel_type": fuel_type,
        "limit": min(limit, 100),
    }
    data = request_json(API_NEARBY, params)
    if not data or not data.get("success"):
        msg = data.get("error", "unknown error") if data else "no response"
        die(f"station search failed: {msg}")

    stations = data.get("stations", [])

    # Add computed distance using haversine
    for s in stations:
        slat = _safe_float(s.get("latitude"), 0.0)
        slon = _safe_float(s.get("longitude"), 0.0)
        s["_distance_km"] = round(haversine_km(lat, lon, slat, slon), 2)

    # Filter by radius (API radius param is approximate)
    stations = [s for s in stations if s["_distance_km"] <= radius_km]

    # Brand filter (client-side, case-insensitive substring)
    if brand:
        brand_lower = brand.lower()
        stations = [
            s for s in stations
            if brand_lower in (s.get("brand") or "").lower()
            or brand_lower in (s.get("name") or "").lower()
        ]

    return stations


# ---------------------------------------------------------------------------
# Output emitters
# ---------------------------------------------------------------------------

def emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def emit_stations(
    stations: list[dict[str, Any]],
    fuel_type: str,
    sort_by: str,
    limit: int,
    as_json: bool,
    lat: float,
    lon: float,
    radius: float,
) -> None:
    """Print station results."""
    if as_json:
        emit_json({
            "filters": {
                "lat": lat,
                "lon": lon,
                "radius_km": radius,
                "fuel": fuel_type,
                "sort": sort_by,
            },
            "count": len(stations),
            "stations": [
                {
                    "name": s.get("name"),
                    "brand": s.get("brand"),
                    "address": s.get("address"),
                    "suburb": s.get("suburb"),
                    "state": s.get("state"),
                    "distance_km": s.get("_distance_km"),
                    "price": s.get("price"),
                    "fuel_code": s.get("fuel_code"),
                    "fuel_name": s.get("fuel_name"),
                    "hours_old": s.get("hours_old"),
                    "source": s.get("source"),
                    "timestamp": s.get("timestamp"),
                }
                for s in stations[:limit]
            ],
        })
        return

    fuel_name = FUEL_TYPES.get(fuel_type, fuel_type)
    source_hint = ""
    if stations:
        sources = {s.get("source", "") for s in stations}
        source_hint = f" | Source: {', '.join(sorted(sources))}"

    print(f"PetrolMate — {fuel_name} within {radius}km of ({lat}, {lon})")
    if sort_by == "price":
        print(f"Sorted by price (cheapest first) | Found: {len(stations)} | Showing: {min(limit, len(stations))}{source_hint}")
    else:
        print(f"Sorted by distance (closest first) | Found: {len(stations)} | Showing: {min(limit, len(stations))}{source_hint}")
    print()

    if not stations:
        print("  (no stations found in this area — try a larger radius or different fuel type)")
        return

    shown = 0
    for s in stations:
        if shown >= limit:
            break
        shown += 1

        name = s.get("name", "Unknown")
        brand = s.get("brand", "")
        price = fmt_price(s.get("price"))
        fuel = fuel_label(s.get("fuel_name"), s.get("fuel_code"))
        raw_m = s.get("distance_meters")
        dist = fmt_dist(raw_m if raw_m is not None else s["_distance_km"] * 1000)
        age = fmt_age(s.get("hours_old"))
        addr = s.get("address", "")

        brand_str = f" [{brand}]" if brand else ""
        dist_str = f" ({dist})" if dist else ""
        addr_str = f" — {addr}" if addr else ""

        print(f"  {shown:>2}. {name}{brand_str}{dist_str}")
        print(f"      {price} {fuel}  •  {age}{addr_str}")

    # Cheapest summary
    if stations:
        cheapest = min(stations, key=lambda s: _safe_float(s.get("price"), 99999))
        print()
        print(
            f"  🏆 Cheapest: {cheapest.get('name')} — "
            f"{fmt_price(cheapest.get('price'))} "
            f"({fuel_label(cheapest.get('fuel_name'), cheapest.get('fuel_code'))})"
        )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    """Search for stations near a location or coordinates."""
    # Resolve coordinates
    if args.location:
        loc_name = args.location.lower()
        if loc_name in LOCATIONS:
            lat, lon = LOCATIONS[loc_name]
            if not args.json:
                print(f"📍 {args.location} ({lat}, {lon})")
        else:
            # Try PetrolMate geocoding
            geo = api_geocode(args.location)
            lat = float(geo["lat"])
            lon = float(geo["lon"])
            if not args.json:
                print(f"📍 {geo.get('address') or geo.get('name') or args.location}")
    elif args.lat is not None and args.lon is not None:
        lat, lon = args.lat, args.lon
        if not args.json:
            print(f"📍 ({lat}, {lon})")
    elif args.geoip:
        loc = api_geoip()
        lat, lon = loc["latitude"], loc["longitude"]
        if not args.json:
            print(f"📍 {loc.get('city', 'Unknown')}, {loc.get('country')} (from IP)")
    else:
        die("Either --location, --lat/--lon, or --geoip is required.")

    fuel = args.fuel or "ULP"
    radius = args.radius

    started = time.perf_counter()
    fetch_limit = 100 if args.sort == "price" or args.brand else args.limit
    stations = api_stations(
        lat=lat,
        lon=lon,
        radius_km=radius,
        fuel_type=fuel,
        limit=fetch_limit,
        brand=args.brand,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    # Sort
    if args.sort == "price":
        stations.sort(key=lambda s: _safe_float(s.get("price"), 99999))
    else:
        stations.sort(key=lambda s: s.get("_distance_km", 999))

    if not args.json:
        print()  # blank line after coordinate info
    emit_stations(
        stations=stations,
        fuel_type=fuel,
        sort_by=args.sort,
        limit=args.limit,
        as_json=args.json,
        lat=lat,
        lon=lon,
        radius=radius,
    )


def cmd_locations(_args: argparse.Namespace) -> None:
    """List known location names."""
    print("Known locations (AU + NZ):")
    nz = {k: v for k, v in LOCATIONS.items() if k in {
        "auckland", "auckland cbd", "st heliers", "wellington", "christchurch",
        "queenstown", "hamilton", "tauranga", "dunedin", "napier",
        "palmerston north", "rotorua", "new plymouth", "whangarei", "nelson",
        "invercargill", "gisborne",
    }}
    au = {k: v for k, v in LOCATIONS.items() if k not in nz}

    print("\nNZ:")
    for name in sorted(nz):
        lat, lon = nz[name]
        print(f"  {name:20s}  {lat:8.4f}, {lon:8.4f}")
    print("\nAU:")
    for name in sorted(au):
        lat, lon = au[name]
        print(f"  {name:20s}  {lat:8.4f}, {lon:8.4f}")


def cmd_fuel_types(_args: argparse.Namespace) -> None:
    """List fuel types."""
    print("Fuel types:")
    for code, label in FUEL_TYPES.items():
        print(f"  {code:<15} {label}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="PetrolMate — AU & NZ fuel price lookup via petrolmate.com.au"
    )
    sub = ap.add_subparsers(dest="command")

    # search
    sp = sub.add_parser("search", help="search stations near a location")
    sp.add_argument("--location", help="named location or address (e.g. 'st heliers', 'Sydney', 'Brisbane QLD')")
    sp.add_argument("--lat", type=float, help="latitude")
    sp.add_argument("--lon", type=float, help="longitude")
    sp.add_argument("--geoip", action="store_true", help="use IP-based location")
    sp.add_argument(
        "--fuel",
        choices=sorted(FUEL_TYPES.keys()),
        default="ULP",
        help="fuel type (default: ULP)",
    )
    sp.add_argument("--radius", type=float, default=5.0, help="search radius in km (default: 5, max: 50)")
    sp.add_argument("--brand", help="filter by brand (case-insensitive substring, e.g. 'Shell', 'BP')")
    sp.add_argument(
        "--sort",
        choices=["price", "distance"],
        default="price",
        help="sort by (default: price)",
    )
    sp.add_argument("--limit", type=int, default=15, help="max results (default: 15, max: 100)")
    sp.add_argument("--json", action="store_true", help="JSON output")
    sp.set_defaults(func=cmd_search)

    # locations
    sp = sub.add_parser("locations", help="list known location names")
    sp.set_defaults(func=cmd_locations)

    # fuel-types
    sp = sub.add_parser("fuel-types", help="list available fuel types")
    sp.set_defaults(func=cmd_fuel_types)

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
