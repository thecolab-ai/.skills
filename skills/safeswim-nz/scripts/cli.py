#!/usr/bin/env python3
"""safeswim.org.nz lightweight beach water quality CLI.

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
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 2.0  # seconds


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
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ, Δλ = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


QUALITY_RANK = {"GREEN": 0, "AMBER": 1, "RED": 2, "RED+": 2, "BLACK": 3}


def quality_matches(actual: str, minimum: str) -> bool:
    """True when `actual` quality is at least as bad as `minimum` (for filtering)."""
    a = QUALITY_RANK.get(actual.upper(), 99)
    m = QUALITY_RANK.get(minimum.upper(), 99)
    return a >= m  # RED+ (2) >= RED (2), GREEN (0) < RED (2) → excluded


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    payload = fetch("/locations")
    locations = (payload or {}).get("locations") or []
    results = []
    query = (args.search or "").lower()

    for loc in locations:
        if not isinstance(loc, dict):
            continue
        state = loc.get("state") or {}
        quality = (state.get("quality") or "UNKNOWN").upper()
        # Filter by search text against name, slug, or alternative name
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

    results = results[: args.limit or len(results)]

    if args.json:
        print(json.dumps({"kind": "list", "count": len(results), "total": len(locations), "beaches": results}, indent=2, ensure_ascii=False))
    else:
        print(f"SafeSwim Auckland beaches: {len(results)} shown (of {len(locations)} total)")
        for b in results:
            pos = b.get("position") or []
            latlon = f" ({pos[0]:.4f}, {pos[1]:.4f})" if len(pos) >= 2 else ""
            patrol_icon = "🛟" if b.get("patrolled") else "  "
            print(f"  {patrol_icon} {b['quality']:6s} {b['name']}{latlon}")


def cmd_detail(args: argparse.Namespace) -> None:
    slug = args.slug
    payload = fetch(f"/locations/{slug}")
    if not payload:
        die(f"no data returned for beach '{slug}'")

    forecasts = payload.get("forecasts") or {}
    tags = payload.get("tags") or []
    alerts = payload.get("alerts") or []

    detail = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "slug": payload.get("slug") or slug,
        "description": payload.get("description"),
        "patrolled": bool(payload.get("patrolled")),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "forecast_hours": len(forecasts.get("ATMOSPHERIC_TEMPERATURE") or []),
        "alerts": alerts,
        "facilities": [t.get("name") for t in tags if isinstance(t, dict) and t.get("type") == "LOCATION_FACILITY"],
        "hazards": [t.get("name") for t in tags if isinstance(t, dict) and t.get("type") == "LOCATION_HAZARD"],
        # Sample first 6 forecast hours
        "forecast_sample": {
            "hour_0_to_5": {
                "water_quality": (forecasts.get("WATER_QUALITY") or [])[:6],
                "air_temp_c": (forecasts.get("ATMOSPHERIC_TEMPERATURE") or [])[:6],
                "water_temp_c": (forecasts.get("WATER_TEMPERATURE") or [])[:6],
                "wind_speed": (forecasts.get("WIND_SPEED") or [])[:6],
                "wind_direction": (forecasts.get("WIND_DIRECTION") or [])[:6],
                "uv_index": (forecasts.get("UV_INDEX") or [])[:6],
                "weather": (forecasts.get("WEATHER_CONDITIONS") or [])[:6],
                "tide_height_m": (forecasts.get("TIDE") or [])[:6],
            },
            "total_forecast_hours": len(forecasts.get("ATMOSPHERIC_TEMPERATURE") or []),
        },
        "cam_id": payload.get("camId"),
        "images": payload.get("images") or [],
    }

    if args.json:
        print(json.dumps({"kind": "detail", "beach": detail}, indent=2, ensure_ascii=False))
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
            print(f"  ⚠️  Alerts:")
            for a in detail["alerts"]:
                title = a.get("title") or a.get("message") or str(a)
                print(f"    - {title[:120]}")
        if detail["cam_id"]:
            print(f"  📷 Live cam: https://safeswim.org.nz/location/{slug}")
        print(f"  Forecast sample (first 6 hours):")
        for i in range(min(6, detail["forecast_hours"])):
            f = detail["forecast_sample"]["hour_0_to_5"]
            print(f"    +{i}h: "
                  f"air={f['air_temp_c'][i] or '?'}°C, "
                  f"water={f['water_temp_c'][i] or '?'}°C, "
                  f"wind={f['wind_speed'][i] or '?'}, "
                  f"UV={f['uv_index'][i] or '?'}, "
                  f"quality={f['water_quality'][i] or '?'}, "
                  f"weather={f['weather'][i] or '?'}")


def cmd_nearby(args: argparse.Namespace) -> None:
    lat, lon = float(args.lat), float(args.lon)
    radius = args.radius or 10
    min_quality = (args.min_quality or "").upper()

    payload = fetch("/locations")
    locations = (payload or {}).get("locations") or []

    results = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        pos = loc.get("position")
        if not pos or len(pos) < 2:
            continue
        dist = haversine_km(lat, lon, pos[0], pos[1])
        if dist > radius:
            continue
        state = loc.get("state") or {}
        quality = (state.get("quality") or "UNKNOWN").upper()
        if min_quality and not quality_matches(quality, min_quality):
            continue
        results.append({
            "name": loc.get("name"),
            "slug": loc.get("slug"),
            "distance_km": round(dist, 1),
            "quality": quality,
            "patrolled": bool(loc.get("patrolled")),
        })

    results.sort(key=lambda x: x["distance_km"])
    results = results[: args.limit or 20]

    if args.json:
        print(json.dumps({
            "kind": "nearby",
            "center": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "min_quality": min_quality or None,
            "count": len(results),
            "beaches": results,
        }, indent=2, ensure_ascii=False))
    else:
        q_filter = f" (quality ≥ {min_quality})" if min_quality else ""
        print(f"SafeSwim beaches within {radius}km of {lat:.4f}, {lon:.4f}{q_filter}: {len(results)} found")
        for b in results:
            patrol_icon = "🛟" if b["patrolled"] else "  "
            print(f"  {patrol_icon} {b['quality']:6s} {b['distance_km']:5.1f}km  {b['name']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Query SafeSwim Auckland beach water quality")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="List beaches with quality status")
    s.add_argument("--search", help="Filter by name/slug")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("detail", help="Full forecast detail for a beach")
    s.add_argument("slug", help="Beach slug (e.g. takapunabeach)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_detail)

    s = sub.add_parser("nearby", help="Beaches near a coordinate")
    s.add_argument("lat", help="Latitude")
    s.add_argument("lon", help="Longitude")
    s.add_argument("--radius", type=float, default=10, help="Search radius in km (default: 10)")
    s.add_argument("--min-quality", help="Minimum water quality: GREEN, AMBER, RED")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_nearby)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
