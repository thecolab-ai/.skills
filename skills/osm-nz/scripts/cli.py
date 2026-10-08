#!/usr/bin/env python3
"""OpenStreetMap Overpass API - nearby POI search CLI.

Self-contained stdlib wrapper around the public Overpass API.
No login, API key, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys
import time
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
UA = "osm-nz-cli/1.0 (https://github.com/thecolab-ai/.skills)"
DEFAULT_RADIUS_M = 2000
MAX_RADIUS_M = 10000
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
TIMEOUT = 10
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
NZ_LAT_MIN = -48.5
NZ_LAT_MAX = -33.0
NZ_LON_MIN = 166.0
NZ_LON_MAX = 180.0
NZ_CHATHAM_LON_MIN = -180.0
NZ_CHATHAM_LON_MAX = -175.0


def die(message: str, code: int = 1) -> None:
    print(f"osm-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# Category definitions - OSM key=value pairs per named filter
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "food": [
        ("amenity", "restaurant"), ("amenity", "cafe"), ("amenity", "bar"),
        ("amenity", "pub"), ("amenity", "fast_food"), ("amenity", "food_court"),
        ("amenity", "ice_cream"),
    ],
    "grocery": [
        ("shop", "supermarket"), ("shop", "convenience"), ("shop", "grocery"),
        ("shop", "greengrocer"), ("shop", "butcher"), ("shop", "bakery"),
        ("shop", "deli"),
    ],
    "outdoors": [
        ("leisure", "park"), ("leisure", "garden"), ("natural", "beach"),
        ("leisure", "nature_reserve"),
    ],
    "culture": [
        ("tourism", "museum"), ("tourism", "gallery"), ("amenity", "theatre"),
        ("amenity", "cinema"), ("amenity", "library"), ("amenity", "arts_centre"),
    ],
    "attractions": [
        ("tourism", "attraction"), ("tourism", "viewpoint"), ("historic", "monument"),
        ("historic", "memorial"), ("tourism", "zoo"), ("tourism", "aquarium"),
        ("historic", "castle"), ("historic", "ruins"),
    ],
    "sports": [
        ("leisure", "sports_centre"), ("leisure", "swimming_pool"),
        ("leisure", "stadium"), ("leisure", "fitness_centre"),
        ("leisure", "sports_hall"),
    ],
    "shopping": [
        ("amenity", "marketplace"), ("shop", "mall"), ("shop", "department_store"),
        ("shop", "clothes"),
    ],
    "transport": [
        ("highway", "bus_stop"), ("railway", "station"), ("railway", "tram_stop"),
        ("amenity", "ferry_terminal"), ("public_transport", "stop_area"),
        ("amenity", "bus_station"),
    ],
    "worship": [
        ("amenity", "place_of_worship"),
    ],
}

CATEGORY_DISPLAY: dict[str, str] = {
    "amenity": "Amenity", "shop": "Shop", "tourism": "Attraction",
    "leisure": "Leisure", "historic": "Historic", "natural": "Natural",
    "highway": "Transport", "railway": "Transport", "public_transport": "Transport",
}

VALUE_DISPLAY: dict[str, str] = {
    "restaurant": "Restaurant", "cafe": "Cafe", "bar": "Bar", "pub": "Pub",
    "fast_food": "Fast Food", "food_court": "Food Court", "ice_cream": "Ice Cream",
    "supermarket": "Supermarket", "convenience": "Convenience Store",
    "grocery": "Grocery", "greengrocer": "Greengrocer", "butcher": "Butcher",
    "bakery": "Bakery", "deli": "Deli",
    "park": "Park", "garden": "Garden", "beach": "Beach", "nature_reserve": "Nature Reserve",
    "museum": "Museum", "gallery": "Art Gallery", "theatre": "Theatre",
    "cinema": "Cinema", "library": "Library", "arts_centre": "Arts Centre",
    "attraction": "Attraction", "viewpoint": "Viewpoint", "monument": "Monument",
    "memorial": "Memorial", "zoo": "Zoo", "aquarium": "Aquarium",
    "castle": "Castle", "ruins": "Ruins",
    "sports_centre": "Sports Centre", "swimming_pool": "Swimming Pool",
    "stadium": "Stadium", "fitness_centre": "Fitness Centre",
    "sports_hall": "Sports Hall",
    "marketplace": "Market", "mall": "Shopping Mall",
    "department_store": "Department Store", "clothes": "Clothing",
    "bus_stop": "Bus Stop", "station": "Train Station", "tram_stop": "Tram Stop",
    "ferry_terminal": "Ferry Terminal", "stop_area": "Transit Hub",
    "bus_station": "Bus Station",
    "place_of_worship": "Place of Worship",
}


def human_category(cat: str) -> str:
    return CATEGORY_DISPLAY.get(cat, cat)


def human_value(val: str) -> str:
    return VALUE_DISPLAY.get(val, val.replace("_", " ").title())


def finite_float(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be a number") from exc
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{label} must be finite")
    return value


def nz_latitude(raw: str) -> float:
    value = finite_float(raw, "latitude")
    if not NZ_LAT_MIN <= value <= NZ_LAT_MAX:
        raise argparse.ArgumentTypeError(
            f"latitude must be within New Zealand bounds ({NZ_LAT_MIN} to {NZ_LAT_MAX})"
        )
    return value


def nz_longitude(raw: str) -> float:
    value = finite_float(raw, "longitude")
    if not (
        NZ_LON_MIN <= value <= NZ_LON_MAX
        or NZ_CHATHAM_LON_MIN <= value <= NZ_CHATHAM_LON_MAX
    ):
        raise argparse.ArgumentTypeError(
            "longitude must be within New Zealand bounds "
            f"({NZ_LON_MIN} to {NZ_LON_MAX}, or {NZ_CHATHAM_LON_MIN} to {NZ_CHATHAM_LON_MAX})"
        )
    return value


def bounded_int(raw: str, label: str, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from exc
    if value < minimum or value > maximum:
        raise argparse.ArgumentTypeError(f"{label} must be between {minimum} and {maximum}")
    return value


def radius_m(raw: str) -> int:
    return bounded_int(raw, "radius", 1, MAX_RADIUS_M)


def result_limit(raw: str) -> int:
    return bounded_int(raw, "limit", 1, MAX_LIMIT)


def category_name(raw: str) -> str:
    value = raw.lower()
    if value not in CATEGORIES:
        raise argparse.ArgumentTypeError(
            f"unknown category '{value}'. Use 'categories' command to list available filters."
        )
    return value


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_query(lat: float, lon: float, radius_m: int, pairs: list[tuple[str, str]]) -> str:
    """Build an Overpass QL query for the given tag pairs and radius."""
    lines = ["[out:json][timeout:8][maxsize:8388608];", "("]

    for key, value in pairs:
        tag = f'["{key}"="{value}"]'
        lines.append(f"  node{tag}(around:{radius_m},{lat},{lon});")
        lines.append(f"  way{tag}(around:{radius_m},{lat},{lon});")

    lines.append(");")
    lines.append("out center tags;")
    return "\n".join(lines)


def fetch_overpass(query: str) -> Any:
    """POST an Overpass QL query and return parsed JSON."""
    data = urllib.parse.urlencode({"data": query}).encode("ascii")
    try:
        # The Overpass API usage policy asks for an identifying User-Agent, so
        # keep the custom UA and pass browser_headers=False so nzfetch doesn't
        # add contradictory Chrome Client-Hints on top of it.
        result = nzfetch.fetch_json(
            OVERPASS_URL,
            data=data,
            method="POST",
            timeout=TIMEOUT,
            max_bytes=MAX_RESPONSE_BYTES,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UA,
                "Accept": "application/json",
            },
            browser_headers=False,
        )
        if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
            die("invalid Overpass response: expected elements array")
        if result.get("remark"):
            die(f"upstream Overpass query incomplete: {result['remark']}")
        return result
    except nzfetch.Blocked as e:
        die(f"network error calling Overpass: {e}")
    except nzfetch.FetchError as e:
        die(f"Overpass fetch failed: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def category_payload() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "count": len(pairs),
            "tag_pairs": [
                {"key": key, "value": value, "label": human_value(value)}
                for key, value in pairs
            ],
        }
        for name, pairs in CATEGORIES.items()
    ]


def cmd_categories(args: argparse.Namespace) -> None:
    payload = category_payload()
    if args.json:
        print(json.dumps({
            "kind": "categories",
            "count": len(payload),
            "categories": payload,
            **provenance(),
        }, indent=2))
        return

    print("Available category filters for `osm-nz nearby --category <name>`:\n")
    for name, pairs in CATEGORIES.items():
        count = len(pairs)
        kinds = sorted(set(v for _, v in pairs))
        sample = ", ".join(human_value(v) for v in kinds[:5])
        if len(kinds) > 5:
            sample += f" (+{len(kinds) - 5} more)"
        print(f"  {name:14s} ({count} tag pairs) - {sample}")


def cmd_nearby(args: argparse.Namespace) -> None:
    lat, lon = args.lat, args.lon
    radius = args.radius

    if args.category:
        pairs = CATEGORIES[args.category]
    else:
        pairs = []
        for ps in CATEGORIES.values():
            pairs.extend(ps)

    query = build_query(lat, lon, radius, pairs)
    started = time.perf_counter()
    raw = fetch_overpass(query)

    elements = raw.get("elements") or []
    seen = set()
    results = []

    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue

        center = el.get("center")
        el_lat = center.get("lat") if center else el.get("lat")
        el_lon = center.get("lon") if center else el.get("lon")
        if el_lat is None or el_lon is None:
            continue
        try:
            el_lat = float(el_lat)
            el_lon = float(el_lon)
        except (TypeError, ValueError):
            continue

        dist_m = haversine_m(lat, lon, el_lat, el_lon)

        osm_cat = ""
        osm_val = ""
        for key in [
            "amenity", "shop", "tourism", "leisure", "historic", "natural",
            "highway", "railway", "public_transport",
        ]:
            if tags.get(key):
                osm_cat = key
                osm_val = tags[key]
                break

        dedup_key = (
            name.casefold(),
            osm_cat,
            osm_val,
            round(el_lat, 5),
            round(el_lon, 5),
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        walk_min = round(dist_m / 83)          # 5 km/h
        drive_min = max(1, round(dist_m / 500))  # 30 km/h
        travel = "walk" if dist_m < 1500 else "drive"
        el_type = el.get("type")
        el_id = el.get("id")
        osm_url = (
            f"https://www.openstreetmap.org/{el_type}/{el_id}"
            if el_type in {"node", "way", "relation"} and el_id is not None
            else None
        )

        results.append({
            "name": name,
            "category": human_category(osm_cat) if osm_cat else "Other",
            "type": human_value(osm_val) if osm_val else None,
            "osm_type": el_type,
            "osm_id": el_id,
            "osm_url": osm_url,
            "distance_m": round(dist_m),
            "walking_min": walk_min,
            "driving_min": drive_min,
            "travel_mode": travel,
            "lat": round(el_lat, 6),
            "lon": round(el_lon, 6),
            "address": ", ".join(filter(None, [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city"),
            ])) or None,
            "website": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
        })

    results.sort(key=lambda x: x["distance_m"])
    results = results[: args.limit]

    elapsed = round((time.perf_counter() - started) * 1000)

    if args.json:
        print(json.dumps({
            "kind": "nearby",
            "center": {"lat": lat, "lon": lon},
            "radius_m": radius,
            "category": args.category or "all",
            "count": len(results),
            "elapsed_ms": elapsed,
            "results": results,
            **provenance(raw),
        }, indent=2, ensure_ascii=False))
    else:
        cat_label = args.category or "all categories"
        print(f"OSM nearby ({cat_label}): {len(results)} results within {radius}m (took {elapsed}ms)\n")
        for r in results:
            dist_label = f"{r['distance_m']}m" if r["distance_m"] < 1000 else f"{r['distance_m']/1000:.1f}km"
            type_str = f" - {r['type']}" if r.get("type") else ""
            print(f"  {dist_label:>6s} {r['travel_mode']:5s}  {r['name']}{type_str}")


def provenance(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"source_url": OVERPASS_URL, "publisher": "OpenStreetMap contributors",
              "licence": "ODbL 1.0",
              "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")}
    latest = ((raw or {}).get("osm3s") or {}).get("timestamp_osm_base")
    if latest:
        result["latest_data"] = latest
    return result


def tag_filter(raw: str) -> tuple[str, str]:
    key, sep, value = raw.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z0-9_:-]{1,100}", key) or not value or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError("--tag requires key=value (use key=* for any value)")
    return key, value


def bbox_value(raw: str) -> tuple[float, float, float, float]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--bbox requires minLon,minLat,maxLon,maxLat")
    west, south, east, north = nz_longitude(parts[0]), nz_latitude(parts[1]), nz_longitude(parts[2]), nz_latitude(parts[3])
    if west >= east or south >= north or east - west > 1 or north - south > 1:
        raise argparse.ArgumentTypeError("--bbox must be ordered and at most 1 degree wide/high; split larger areas")
    return west, south, east, north


def build_tag_query(tags: list[tuple[str, str]], bbox: tuple[float, ...] | None,
                    area: int | None, limit: int) -> str:
    if len(tags) > 10:
        die("at most 10 --tag filters may be combined", 2)
    # JSON quoting escapes values safely as Overpass string literals; no raw QL.
    selector = "".join(f"[{json.dumps(k)}]" if v == "*" else f"[{json.dumps(k)}={json.dumps(v, ensure_ascii=False)}]" for k, v in tags)
    lines = ["[out:json][timeout:8][maxsize:8388608];"]
    if bbox:
        west, south, east, north = bbox
        lines.append(f"nwr{selector}({south},{west},{north},{east});")
    else:
        lines.append(f"area({area})->.searchArea;")
        lines.append(f"(nwr{selector}(area.searchArea)({NZ_LAT_MIN},{NZ_LON_MIN},{NZ_LAT_MAX},{NZ_LON_MAX});")
        lines.append(f"nwr{selector}(area.searchArea)({NZ_LAT_MIN},{NZ_CHATHAM_LON_MIN},{NZ_LAT_MAX},{NZ_CHATHAM_LON_MAX}););")
    lines.append(f"out center tags {limit + 1};")
    return "\n".join(lines)


def raw_records(raw: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for el in raw["elements"]:
        if not isinstance(el, dict) or el.get("type") not in {"node", "way", "relation"} or not isinstance(el.get("id"), int) or not isinstance(el.get("tags", {}), dict):
            die("invalid Overpass response: malformed OSM element")
        center = el.get("center") or el
        if not isinstance(center, dict):
            die("invalid Overpass response: malformed element centre")
        lat, lon = center.get("lat"), center.get("lon")
        records.append({"osm_type": el["type"], "osm_id": el["id"],
                        "osm_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                        "tags": el.get("tags") or {}, "lat": lat, "lon": lon})
    return records


def cmd_query(args: argparse.Namespace) -> None:
    query = build_tag_query(args.tag, args.bbox, args.area, args.limit)
    raw = fetch_overpass(query)
    records = raw_records(raw)
    payload = {"kind": "query", "bbox": args.bbox, "area": args.area,
               "tags": [{"key": k, "value": v} for k, v in args.tag],
               "count": min(len(records), args.limit), "limit": args.limit,
               "truncated": len(records) > args.limit, **provenance(raw),
               "geometry_note": "Ways and relations use bounding-box centres, not footprints or fence lines."}
    records = records[:args.limit]
    context = {k: payload[k] for k in ("source_url", "publisher", "licence", "retrieved_at", "latest_data") if k in payload}
    for record in records:
        record.update(context)
    if args.format == "geojson":
        payload["query_bbox"] = payload.pop("bbox")
        payload.update({"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": f"{r['osm_type']}/{r['osm_id']}",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]} if r["lon"] is not None and r["lat"] is not None else None,
             "properties": r} for r in records]})
    else:
        payload["records"] = records
    if args.json or args.format == "geojson":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"OSM tag query: {len(records)} results (truncated: {payload['truncated']})")
        for r in records:
            print(f"- {r['osm_type']}/{r['osm_id']}: {json.dumps(r['tags'], ensure_ascii=False)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Search OpenStreetMap for nearby points of interest")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("nearby", help="Find POIs near a coordinate")
    s.add_argument("lat", type=nz_latitude, help="Latitude within New Zealand bounds")
    s.add_argument("lon", type=nz_longitude, help="Longitude within New Zealand bounds")
    s.add_argument(
        "--radius",
        type=radius_m,
        default=DEFAULT_RADIUS_M,
        help=f"Search radius in metres, 1-{MAX_RADIUS_M} (default: {DEFAULT_RADIUS_M})",
    )
    s.add_argument("--category", type=category_name, help="Category filter (use 'categories' command to list)")
    s.add_argument("--limit", type=result_limit, default=DEFAULT_LIMIT, help=f"Maximum results, 1-{MAX_LIMIT}")
    s.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    s.set_defaults(func=cmd_nearby)

    s = sub.add_parser("categories", help="List available category filters")
    s.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    s.set_defaults(func=cmd_categories)

    s = sub.add_parser("query", help="Query raw OSM tags, including unnamed nodes, ways and relations")
    scope = s.add_mutually_exclusive_group(required=True)
    scope.add_argument("--bbox", type=bbox_value, help="WGS84 minLon,minLat,maxLon,maxLat, at most 1 degree wide/high")
    scope.add_argument("--area", type=lambda s: bounded_int(s, "Overpass area ID", 2400000000, 4294967295), help="numeric Overpass area ID; results restricted to NZ bounds")
    s.add_argument("--tag", type=tag_filter, action="append", required=True, help="key=value, repeat for AND; key=* means key exists")
    s.add_argument("--limit", type=result_limit, default=DEFAULT_LIMIT, help=f"maximum returned elements, 1-{MAX_LIMIT}")
    s.add_argument("--format", choices=("json", "geojson"), default="json", help="GeoJSON uses centre points for ways and relations")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_query)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
