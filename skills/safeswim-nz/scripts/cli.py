#!/usr/bin/env python3
"""safeswim.org.nz lightweight swimming-location water quality CLI.

Self-contained stdlib wrapper around the public SafeSwim REST API.
No login, account state, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "https://safeswim.org.nz/api"
UA = "thecolab-ai-skills/safeswim-nz (+https://github.com/thecolab-ai/.skills)"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 2.0  # seconds

QUALITY_RANK = {"GREEN": 0, "AMBER": 1, "RED": 2, "RED+": 3, "BLACK": 4}
QUALITY_STATUSES = tuple(QUALITY_RANK)


def die(message: str, code: int = 1) -> None:
    print(f"safeswim-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch(path: str) -> Any:
    """Fetch JSON from the SafeSwim API with brief in-process caching."""
    now = time.time()
    if path in _CACHE:
        ts, data = _CACHE[path]
        if now - ts < _CACHE_TTL:
            return data
    url = BASE + path
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            _CACHE[path] = (time.time(), data)
            return data
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:300]
        die(f"HTTP {e.code} from {url}: {raw}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def status_at_or_above_risk(actual: str, minimum: str) -> bool:
    """True when actual status is at least as risky as minimum."""
    actual_rank = QUALITY_RANK.get(actual.upper())
    minimum_rank = QUALITY_RANK[minimum]
    return actual_rank is not None and actual_rank >= minimum_rank


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def latitude(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not -90 <= parsed <= 90:
        raise argparse.ArgumentTypeError("must be between -90 and 90")
    return parsed


def longitude(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not -180 <= parsed <= 180:
        raise argparse.ArgumentTypeError("must be between -180 and 180")
    return parsed


def quality_status(value: str) -> str:
    status = value.upper()
    if status not in QUALITY_RANK:
        raise argparse.ArgumentTypeError(
            f"must be one of: {', '.join(QUALITY_STATUSES)}"
        )
    return status


def forecast_series(forecasts: dict[str, Any], key: str) -> list[Any]:
    series = forecasts.get(key)
    return series if isinstance(series, list) else []


def forecast_value(series: list[Any], index: int) -> Any:
    return series[index] if index < len(series) else None


def display_value(value: Any) -> Any:
    return "?" if value is None or value == "" else value


def get_locations(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        die("unexpected /locations response shape")
    locations = payload.get("locations") or []
    if not isinstance(locations, list):
        die("unexpected /locations.locations response shape")
    return [loc for loc in locations if isinstance(loc, dict)]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    payload = fetch("/locations")
    locations = get_locations(payload)
    results = []
    query = (args.search or "").lower()

    for loc in locations:
        state = loc.get("state") or {}
        quality = (state.get("quality") or "UNKNOWN").upper()
        if query:
            name = (loc.get("name") or "").lower()
            alt = (loc.get("alternative_name") or "").lower()
            slug = (loc.get("slug") or "").lower()
            if query not in name and query not in alt and query not in slug:
                continue
        results.append({
            "name": loc.get("name"),
            "slug": loc.get("slug"),
            "alternative_name": loc.get("alternative_name"),
            "quality": quality,
            "patrolled": bool(loc.get("patrolled")),
            "position": loc.get("position"),
            "safety": state.get("safety"),
            "patrol": state.get("patrol"),
        })

    results = results[:args.limit]

    if args.json:
        print(json.dumps({
            "kind": "list",
            "count": len(results),
            "total": len(locations),
            "locations": results,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"SafeSwim NZ locations: {len(results)} shown (of {len(locations)} total)")
        for item in results:
            pos = item.get("position") or []
            latlon = f" ({pos[0]:.4f}, {pos[1]:.4f})" if len(pos) >= 2 else ""
            patrol = "patrolled" if item.get("patrolled") else "unpatrolled"
            print(f"  {item['quality']:6s} {item['name']}{latlon} [{patrol}]")


def cmd_detail(args: argparse.Namespace) -> None:
    slug = args.slug
    payload = fetch(f"/locations/{slug}")
    if not isinstance(payload, dict) or not payload:
        die(f"no data returned for location '{slug}'")

    forecasts = payload.get("forecasts") or {}
    if not isinstance(forecasts, dict):
        forecasts = {}
    tags = payload.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    alerts = payload.get("alerts") or []
    if not isinstance(alerts, list):
        alerts = []

    forecast_sample = {
        "water_quality": forecast_series(forecasts, "WATER_QUALITY")[:6],
        "air_temp_c": forecast_series(forecasts, "ATMOSPHERIC_TEMPERATURE")[:6],
        "water_temp_c": forecast_series(forecasts, "WATER_TEMPERATURE")[:6],
        "wind_speed": forecast_series(forecasts, "WIND_SPEED")[:6],
        "wind_direction": forecast_series(forecasts, "WIND_DIRECTION")[:6],
        "uv_index": forecast_series(forecasts, "UV_INDEX")[:6],
        "weather": forecast_series(forecasts, "WEATHER_CONDITIONS")[:6],
        "tide_height_m": forecast_series(forecasts, "TIDE")[:6],
    }
    forecast_hours = max(
        (len(series) for series in forecasts.values() if isinstance(series, list)),
        default=0,
    )

    detail = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "slug": payload.get("slug") or slug,
        "description": payload.get("description"),
        "patrolled": bool(payload.get("patrolled")),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "forecast_hours": forecast_hours,
        "alerts": alerts,
        "facilities": [
            tag.get("name")
            for tag in tags
            if isinstance(tag, dict) and tag.get("type") == "LOCATION_FACILITY"
        ],
        "hazards": [
            tag.get("name")
            for tag in tags
            if isinstance(tag, dict) and tag.get("type") == "LOCATION_HAZARD"
        ],
        "forecast_sample": {
            "hour_0_to_5": forecast_sample,
            "total_forecast_hours": forecast_hours,
        },
        "cam_id": payload.get("camId"),
        "images": payload.get("images") or [],
    }

    if args.json:
        print(json.dumps({"kind": "detail", "location": detail}, indent=2, ensure_ascii=False))
    else:
        print(f"SafeSwim: {detail['name']}")
        print(f"  Patrolled: {'Yes' if detail['patrolled'] else 'No'}")
        print(f"  Forecast hours available: {detail['forecast_hours']}")
        if detail["description"]:
            print(f"  Description: {detail['description'][:200]}")
        if detail["facilities"]:
            print(f"  Facilities: {', '.join(detail['facilities'][:10])}")
        if detail["hazards"]:
            print(f"  Hazards: {', '.join(detail['hazards'][:10])}")
        if detail["alerts"]:
            print("  Alerts:")
            for alert in detail["alerts"]:
                title = alert.get("title") or alert.get("message") or str(alert)
                print(f"    - {title[:120]}")
        if detail["cam_id"]:
            print(f"  Live cam: https://safeswim.org.nz/locations/{slug}")
        print("  Forecast sample (first 6 hours):")
        for i in range(min(6, detail["forecast_hours"])):
            sample = detail["forecast_sample"]["hour_0_to_5"]
            print(
                f"    +{i}h: "
                f"air={display_value(forecast_value(sample['air_temp_c'], i))}C, "
                f"water={display_value(forecast_value(sample['water_temp_c'], i))}C, "
                f"wind={display_value(forecast_value(sample['wind_speed'], i))}, "
                f"UV={display_value(forecast_value(sample['uv_index'], i))}, "
                f"quality={display_value(forecast_value(sample['water_quality'], i))}, "
                f"weather={display_value(forecast_value(sample['weather'], i))}"
            )


def cmd_nearby(args: argparse.Namespace) -> None:
    lat, lon = args.lat, args.lon
    radius = args.radius
    min_risk = args.min_risk or ""

    payload = fetch("/locations")
    locations = get_locations(payload)

    results = []
    for loc in locations:
        pos = loc.get("position")
        if not pos or len(pos) < 2:
            continue
        dist = haversine_km(lat, lon, pos[0], pos[1])
        if dist > radius:
            continue
        state = loc.get("state") or {}
        quality = (state.get("quality") or "UNKNOWN").upper()
        if min_risk and not status_at_or_above_risk(quality, min_risk):
            continue
        results.append({
            "name": loc.get("name"),
            "slug": loc.get("slug"),
            "distance_km": round(dist, 1),
            "quality": quality,
            "patrolled": bool(loc.get("patrolled")),
        })

    results.sort(key=lambda x: x["distance_km"])
    results = results[:args.limit]

    if args.json:
        print(json.dumps({
            "kind": "nearby",
            "center": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "min_risk": min_risk or None,
            "count": len(results),
            "locations": results,
        }, indent=2, ensure_ascii=False))
    else:
        q_filter = f" (status at/above {min_risk})" if min_risk else ""
        print(f"SafeSwim locations within {radius}km of {lat:.4f}, {lon:.4f}{q_filter}: {len(results)} found")
        for item in results:
            patrol = "patrolled" if item["patrolled"] else "unpatrolled"
            print(f"  {item['quality']:6s} {item['distance_km']:5.1f}km  {item['name']} [{patrol}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query SafeSwim NZ swimming-location water quality")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list", help="List SafeSwim locations with quality status")
    list_parser.add_argument("--search", help="Filter by name/slug")
    list_parser.add_argument("--limit", type=positive_int, default=50)
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    detail_parser = sub.add_parser("detail", help="Full forecast detail for a SafeSwim location")
    detail_parser.add_argument("slug", help="Location slug (e.g. takapuna)")
    detail_parser.add_argument("--json", action="store_true")
    detail_parser.set_defaults(func=cmd_detail)

    nearby_parser = sub.add_parser("nearby", help="SafeSwim locations near a coordinate")
    nearby_parser.add_argument("lat", type=latitude, help="Latitude")
    nearby_parser.add_argument("lon", type=longitude, help="Longitude")
    nearby_parser.add_argument("--radius", type=positive_float, default=10, help="Search radius in km (default: 10)")
    nearby_parser.add_argument(
        "--min-risk",
        dest="min_risk",
        type=quality_status,
        metavar="STATUS",
        help="Minimum warning severity/status to include: GREEN, AMBER, RED, RED+, BLACK",
    )
    nearby_parser.add_argument(
        "--min-quality",
        dest="min_risk",
        type=quality_status,
        help=argparse.SUPPRESS,
    )
    nearby_parser.add_argument("--limit", type=positive_int, default=20)
    nearby_parser.add_argument("--json", action="store_true")
    nearby_parser.set_defaults(func=cmd_nearby)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
