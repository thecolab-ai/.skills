#!/usr/bin/env python3
"""NZ buses lightweight CLI.

Self-contained stdlib wrapper around Metlink Open Data for Wellington region
bus routes, stops, live arrivals, service alerts, and vehicle positions.
Read-only; no journey planning, account, ticketing, or mutation actions.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_API = os.environ.get("METLINK_API_BASE", "https://api.opendata.metlink.org.nz/v1").rstrip("/")
BASE_PORTAL = "https://opendata.metlink.org.nz/"

# Metlink uses standard GTFS bus route_type=3 and extended school-bus
# route_type=712. Rail (2), ferry (4), and cable car (5) are intentionally out
# of scope for this skill.
BUS_ROUTE_TYPES = {"3", "712"}

ROUTE_TYPE_LABELS = {
    "0": "tram/cable-car",
    "1": "metro",
    "2": "rail",
    "3": "bus",
    "4": "ferry",
    "5": "cable-car",
    "6": "gondola",
    "7": "funicular",
    "712": "school-bus",
}

_STOP_ROUTE_CACHE: dict[str, list[dict[str, Any]]] = {}


def die(message: str, code: int = 1) -> None:
    print(f"nz-buses: {message}", file=sys.stderr)
    raise SystemExit(code)


def api_key() -> str:
    key = os.environ.get("METLINK_API_KEY")
    if not key:
        die(
            "METLINK_API_KEY is not set. Create a free key at "
            f"{BASE_PORTAL} and run: export METLINK_API_KEY='...'"
        )
    return key


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = BASE_API + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v not in (None, "")}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "x-api-key": api_key(),
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            url, timeout=timeout, accept="application/json", headers=headers
        )
    except nzfetch.Blocked as e:
        die(f"network error calling Metlink: {e}")
    except nzfetch.FetchError as e:
        die(f"error calling Metlink: {e}")
    raw = body.decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as e:
        die(f"invalid JSON from Metlink: {e}")


def as_list(payload: Any, key: str | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if key and isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [x for x in payload[key] if isinstance(x, dict)]
    return []


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def value_name(value: Any) -> str:
    if isinstance(value, dict):
        return text(first(value, "name", "stop_name", "stopName", "text", "stop_id", "stopId"))
    return text(value)


def translation_text(data: dict[str, Any] | None) -> str:
    if not isinstance(data, dict):
        return ""
    translations = data.get("translation")
    if isinstance(translations, list):
        for row in translations:
            if isinstance(row, dict) and row.get("text"):
                return str(row["text"])
    return text(data.get("text"))


def epoch_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        return text(value)


def route_type_label(route_type: Any) -> str:
    value = text(route_type)
    return ROUTE_TYPE_LABELS.get(value, value or "-")


def is_bus_route_type(route_type: Any) -> bool:
    return text(route_type) in BUS_ROUTE_TYPES


def parse_stop(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_id": text(first(row, "stop_id", "stopId")),
        "stop_code": text(first(row, "stop_code", "stopCode")),
        "stop_name": text(first(row, "stop_name", "stopName")),
        "stop_desc": text(first(row, "stop_desc", "stopDescription", "stop_desc")),
        "stop_lat": first(row, "stop_lat", "lat", "latitude"),
        "stop_lon": first(row, "stop_lon", "lon", "longitude"),
        "location_type": first(row, "location_type", "locationType"),
        "parent_station": text(first(row, "parent_station", "parentStation")),
        "zone_id": text(first(row, "zone_id", "zoneId")),
    }


def parse_route(row: dict[str, Any]) -> dict[str, Any]:
    route_type = first(row, "route_type", "routeType")
    return {
        "route_id": text(first(row, "route_id", "routeId")),
        "route_short_name": text(first(row, "route_short_name", "routeShortName")),
        "route_long_name": text(first(row, "route_long_name", "routeLongName")),
        "route_desc": text(first(row, "route_desc", "routeDescription")),
        "route_type": text(route_type),
        "mode": route_type_label(route_type),
        "agency_id": text(first(row, "agency_id", "agencyId")),
        "route_color": text(first(row, "route_color", "routeColor")),
        "route_text_color": text(first(row, "route_text_color", "routeTextColor")),
    }


def parse_departure(row: dict[str, Any]) -> dict[str, Any]:
    arrival = row.get("arrival") if isinstance(row.get("arrival"), dict) else {}
    departure = row.get("departure") if isinstance(row.get("departure"), dict) else {}
    destination = value_name(first(row, "destination", "headsign", "trip_headsign", "tripHeadsign"))
    if not destination:
        destination = text(first(row, "trip_headsign", "tripHeadsign"))
    return {
        "service_id": text(first(row, "service_id", "serviceId", "route_id", "routeId")),
        "route_id": text(first(row, "route_id", "routeId")),
        "trip_id": text(first(row, "trip_id", "tripId")),
        "direction": text(first(row, "direction", "direction_id", "directionId")),
        "origin": value_name(row.get("origin")),
        "destination": destination,
        "status": text(first(row, "status", "departure_status", "departureStatus")),
        "platform": text(first(row, "platform", "platform_code", "platformCode")),
        "aimed_arrival": first(arrival, "aimed", "aimed_time", "aimedTime"),
        "expected_arrival": first(arrival, "expected", "expected_time", "expectedTime"),
        "aimed_departure": first(
            departure,
            "aimed",
            "aimed_time",
            "aimedTime",
            default=first(row, "aimed_departure_time", "scheduled_departure_time", "departure_time"),
        ),
        "expected_departure": first(
            departure,
            "expected",
            "expected_time",
            "expectedTime",
            default=first(row, "expected_departure_time", "estimated_departure_time", "departure_time"),
        ),
        "delay": text(first(row, "delay", "delay_seconds", "delaySeconds")),
        "vehicle_id": text(first(row, "vehicle_id", "vehicleId")),
        "monitored": row.get("monitored"),
        "wheelchair_accessible": row.get("wheelchair_accessible") or row.get("wheelchairAccessible"),
        "raw": row,
    }


def parse_alert_entity(entity: dict[str, Any]) -> dict[str, Any]:
    alert = entity.get("alert") if isinstance(entity.get("alert"), dict) else entity
    informed = alert.get("informed_entity") or alert.get("informedEntity") or []
    periods = alert.get("active_period") or alert.get("activePeriod") or []
    return {
        "id": text(entity.get("id") or alert.get("id")),
        "cause": text(alert.get("cause")),
        "effect": text(alert.get("effect")),
        "severity_level": text(alert.get("severity_level") or alert.get("severityLevel")),
        "header_text": translation_text(alert.get("header_text") or alert.get("headerText")),
        "description_text": translation_text(alert.get("description_text") or alert.get("descriptionText")),
        "url": translation_text(alert.get("url")),
        "active_period": periods,
        "informed_entity": informed,
        "route_ids": sorted(
            {
                text(first(x, "route_id", "routeId"))
                for x in informed
                if isinstance(x, dict) and first(x, "route_id", "routeId")
            }
        ),
        "stop_ids": sorted(
            {
                text(first(x, "stop_id", "stopId"))
                for x in informed
                if isinstance(x, dict) and first(x, "stop_id", "stopId")
            }
        ),
    }


def parse_vehicle_entity(entity: dict[str, Any]) -> dict[str, Any]:
    vehicle = entity.get("vehicle") if isinstance(entity.get("vehicle"), dict) else entity
    trip = vehicle.get("trip") if isinstance(vehicle.get("trip"), dict) else {}
    position = vehicle.get("position") if isinstance(vehicle.get("position"), dict) else {}
    descriptor = vehicle.get("vehicle") if isinstance(vehicle.get("vehicle"), dict) else {}
    return {
        "id": text(entity.get("id") or descriptor.get("id")),
        "vehicle_id": text(descriptor.get("id")),
        "label": text(descriptor.get("label")),
        "route_id": text(first(trip, "route_id", "routeId")),
        "trip_id": text(first(trip, "trip_id", "tripId")),
        "start_time": text(first(trip, "start_time", "startTime")),
        "lat": first(position, "latitude", "lat"),
        "lon": first(position, "longitude", "lon"),
        "bearing": position.get("bearing"),
        "speed": position.get("speed"),
        "timestamp": epoch_to_iso(vehicle.get("timestamp")),
    }


def fetch_routes() -> list[dict[str, Any]]:
    return [parse_route(x) for x in as_list(request_json("/gtfs/routes"))]


def fetch_bus_routes() -> list[dict[str, Any]]:
    return [route for route in fetch_routes() if is_bus_route_type(route.get("route_type"))]


def fetch_stops(route_id: str | None = None) -> list[dict[str, Any]]:
    params = {"route_id": route_id} if route_id else None
    return [parse_stop(x) for x in as_list(request_json("/gtfs/stops", params))]


def route_type_index() -> dict[str, str]:
    return {r["route_id"]: r["route_type"] for r in fetch_routes() if r.get("route_id")}


def dedupe_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for route in routes:
        key = route.get("route_id", "")
        if key and key not in seen:
            seen.add(key)
            out.append(route)
    return out


def resolve_routes(route_ref: str, routes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    needle = route_ref.strip().lower()
    if not needle:
        return []
    choices = routes if routes is not None else fetch_bus_routes()
    exact = [
        route
        for route in choices
        if route.get("route_id", "").lower() == needle or route.get("route_short_name", "").lower() == needle
    ]
    if exact:
        return dedupe_routes(exact)
    contains = [
        route
        for route in choices
        if needle
        in " ".join(
            [
                route.get("route_id", ""),
                route.get("route_short_name", ""),
                route.get("route_long_name", ""),
                route.get("route_desc", ""),
            ]
        ).lower()
    ]
    return dedupe_routes(contains)


def stop_routes(stop_id: str) -> list[dict[str, Any]]:
    if stop_id not in _STOP_ROUTE_CACHE:
        _STOP_ROUTE_CACHE[stop_id] = [parse_route(x) for x in as_list(request_json("/gtfs/routes", {"stop_id": stop_id}))]
    return _STOP_ROUTE_CACHE[stop_id]


def stop_bus_routes(stop_id: str) -> list[dict[str, Any]]:
    return [route for route in stop_routes(stop_id) if is_bus_route_type(route.get("route_type"))]


def find_stop(stop_ref: str, stops: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    needle = stop_ref.strip().lower()
    rows = stops if stops is not None else fetch_stops()
    for stop in rows:
        if stop.get("stop_id", "").lower() == needle or stop.get("stop_code", "").lower() == needle:
            return stop
    for stop in rows:
        if stop.get("stop_name", "").lower() == needle:
            return stop
    return None


def is_regular_stop(stop: dict[str, Any]) -> bool:
    return text(stop.get("location_type")) in ("", "0")


def stop_search_text(stop: dict[str, Any]) -> str:
    return " ".join(
        [
            stop.get("stop_id", ""),
            stop.get("stop_code", ""),
            stop.get("stop_name", ""),
            stop.get("stop_desc", ""),
        ]
    ).lower()


def resolve_near_location(value: str, stops: list[dict[str, Any]]) -> tuple[float, float, str]:
    parsed = parse_lat_lon(value)
    if parsed:
        return parsed[0], parsed[1], "coordinates"

    needle = value.strip().lower()
    matches = [
        stop
        for stop in stops
        if is_regular_stop(stop)
        and stop.get("stop_lat") not in (None, "")
        and stop.get("stop_lon") not in (None, "")
        and (
            stop.get("stop_id", "").lower() == needle
            or stop.get("stop_code", "").lower() == needle
            or needle in stop.get("stop_name", "").lower()
            or needle in stop.get("stop_desc", "").lower()
        )
    ]
    if not matches:
        die(f"could not resolve --near {value!r}; use a stop name/code/id or 'lat,lon'")

    lat = sum(float(stop["stop_lat"]) for stop in matches) / len(matches)
    lon = sum(float(stop["stop_lon"]) for stop in matches) / len(matches)
    label = f"{len(matches)} matching stop" + ("" if len(matches) == 1 else "s")
    return lat, lon, label


def parse_lat_lon(value: str) -> tuple[float, float] | None:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        die("--near coordinates must be in 'lat,lon' order")
    return lat, lon


def distance_m(lat1: float, lon1: float, lat2: Any, lon2: Any) -> int | None:
    if lat2 in (None, "") or lon2 in (None, ""):
        return None
    try:
        p1 = radians(lat1)
        p2 = radians(float(lat2))
        dp = radians(float(lat2) - lat1)
        dl = radians(float(lon2) - lon1)
    except (TypeError, ValueError):
        return None
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return round(6371000 * 2 * atan2(sqrt(a), sqrt(1 - a)))


def enrich_bus_stop(stop: dict[str, Any]) -> dict[str, Any] | None:
    routes = stop_bus_routes(stop["stop_id"])
    if not routes:
        return None
    out = dict(stop)
    out["bus_routes"] = [
        route.get("route_short_name") or route.get("route_id")
        for route in routes
        if route.get("route_short_name") or route.get("route_id")
    ]
    return out


def collect_bus_stops(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for stop in candidates:
        enriched = enrich_bus_stop(stop)
        if enriched:
            selected.append(enriched)
        if len(selected) >= limit:
            break
    return selected


def bus_arrivals_for_stop(stop_id: str, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_refs = {
        ref.lower()
        for route in routes
        for ref in (route.get("route_id", ""), route.get("route_short_name", ""))
        if ref
    }
    rows = [parse_departure(x) for x in as_list(request_json("/stop-predictions", {"stop_id": stop_id}), "departures")]
    if not route_refs:
        return []
    return [
        row
        for row in rows
        if row.get("route_id", "").lower() in route_refs or row.get("service_id", "").lower() in route_refs
    ]


def alert_is_bus_relevant(alert: dict[str, Any], types: dict[str, str]) -> bool:
    route_ids = alert.get("route_ids") or []
    if route_ids:
        return any(is_bus_route_type(types.get(route_id)) for route_id in route_ids)
    stop_ids = alert.get("stop_ids") or []
    if stop_ids:
        return any(stop_bus_routes(stop_id) for stop_id in stop_ids)
    return True


def cmd_stops(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    rows = [stop for stop in fetch_stops() if is_regular_stop(stop)]
    if args.query:
        q = args.query.lower()
        rows = [stop for stop in rows if q in stop_search_text(stop)]
    near = None
    if args.near:
        lat, lon, source = resolve_near_location(args.near, rows)
        for stop in rows:
            stop["distance_m"] = distance_m(lat, lon, stop.get("stop_lat"), stop.get("stop_lon"))
        rows = [stop for stop in rows if stop.get("distance_m") is not None]
        rows.sort(key=lambda stop: stop["distance_m"])
        near = {"input": args.near, "lat": lat, "lon": lon, "resolved_from": source}
    rows = collect_bus_stops(rows, args.limit)
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "query": args.query,
        "near": near,
        "returned": len(rows),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stops": rows,
    }
    emit(data, args.json, print_stops)


def cmd_routes(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    rows = fetch_bus_routes()
    if args.query:
        q = args.query.lower()
        rows = [
            route
            for route in rows
            if q
            in " ".join(
                [
                    route.get("route_id", ""),
                    route.get("route_short_name", ""),
                    route.get("route_long_name", ""),
                    route.get("route_desc", ""),
                ]
            ).lower()
        ]
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "query": args.query,
        "total_matches": len(rows),
        "returned": min(len(rows), args.limit),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "routes": rows[: args.limit],
    }
    emit(data, args.json, print_routes)


def cmd_route(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    matches = resolve_routes(args.route)
    if not matches:
        die(f"bus route {args.route!r} not found")
    route = matches[0]
    stops = fetch_stops(route["route_id"])
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "route_ref": args.route,
        "matched_routes": len(matches),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "route": route,
        "stops_returned": min(len(stops), args.limit),
        "stops_total": len(stops),
        "stops": stops[: args.limit],
    }
    emit(data, args.json, print_route)


def cmd_stop(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    stop = find_stop(args.stop_id)
    if not stop:
        die(f"stop {args.stop_id!r} not found")
    routes = stop_bus_routes(stop["stop_id"])
    if not routes:
        die(f"stop {args.stop_id!r} is not served by Metlink bus routes")
    arrivals = bus_arrivals_for_stop(stop["stop_id"], routes)
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "stop_id": stop["stop_id"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "stop": stop,
        "routes": routes,
        "arrivals_returned": min(len(arrivals), args.limit),
        "arrivals_total": len(arrivals),
        "arrivals": arrivals[: args.limit],
    }
    emit(data, args.json, print_stop)


def cmd_arrivals(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    stop = find_stop(args.stop_id)
    if not stop:
        die(f"stop {args.stop_id!r} not found")
    routes = stop_bus_routes(stop["stop_id"])
    if not routes:
        die(f"stop {args.stop_id!r} is not served by Metlink bus routes")
    rows = bus_arrivals_for_stop(stop["stop_id"], routes)
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "stop_id": stop["stop_id"],
        "stop_name": stop.get("stop_name"),
        "total_arrivals": len(rows),
        "returned": min(len(rows), args.limit),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "arrivals": rows[: args.limit],
    }
    emit(data, args.json, print_arrivals)


def cmd_alerts(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = request_json("/gtfs-rt/servicealerts")
    rows = [parse_alert_entity(x) for x in as_list(payload, "entity")]
    types = route_type_index()
    rows = [row for row in rows if alert_is_bus_relevant(row, types)]
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "total_alerts": len(rows),
        "returned": min(len(rows), args.limit),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "alerts": rows[: args.limit],
    }
    emit(data, args.json, print_alerts)


def cmd_vehicles(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    routes = fetch_bus_routes()
    bus_route_ids = {route["route_id"] for route in routes}
    selected_route_ids: set[str] | None = None
    if args.route:
        matches = resolve_routes(args.route, routes)
        if not matches:
            die(f"bus route {args.route!r} not found")
        selected_route_ids = {route["route_id"] for route in matches}

    payload = request_json("/gtfs-rt/vehiclepositions")
    rows = [parse_vehicle_entity(x) for x in as_list(payload, "entity")]
    rows = [row for row in rows if row.get("route_id") in bus_route_ids]
    if selected_route_ids is not None:
        rows = [row for row in rows if row.get("route_id") in selected_route_ids]
    data = {
        "source": "metlink",
        "network": "wellington-region-buses",
        "route": args.route,
        "route_ids": sorted(selected_route_ids) if selected_route_ids else None,
        "total_vehicles": len(rows),
        "returned": min(len(rows), args.limit),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "vehicles": rows[: args.limit],
    }
    emit(data, args.json, print_vehicles)


def emit(data: dict[str, Any], as_json: bool, printer: Any) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        printer(data)


def print_stops(data: dict[str, Any]) -> None:
    bits = []
    if data.get("query"):
        bits.append(f"matching {data['query']!r}")
    if data.get("near"):
        bits.append(f"near {data['near']['input']!r}")
    label = " " + ", ".join(bits) if bits else ""
    print(f"Metlink bus stops{label}: showing {data['returned']} ({data['elapsed_ms']} ms)")
    if data.get("near"):
        near = data["near"]
        print(f"Resolved near point: {near['lat']:.6f},{near['lon']:.6f} from {near['resolved_from']}")
    print()
    for stop in data["stops"]:
        code = f" code {stop['stop_code']}" if stop.get("stop_code") else ""
        distance = f" {stop['distance_m']}m" if stop.get("distance_m") is not None else ""
        print(f"{stop['stop_id']}  {stop['stop_name']}{code}{distance}")
        bits = [stop.get("stop_desc"), latlon(stop)]
        if stop.get("bus_routes"):
            bits.append("routes " + ", ".join(stop["bus_routes"][:12]))
        print("  " + " | ".join(x for x in bits if x))
        print()


def print_routes(data: dict[str, Any]) -> None:
    print(
        f"Metlink bus routes: {data['total_matches']} total, "
        f"showing {data['returned']} ({data['elapsed_ms']} ms)"
    )
    print()
    for route in data["routes"]:
        short = route.get("route_short_name") or route.get("route_id")
        print(f"{route['route_id']}  {short}  {route.get('route_long_name')}")
        print(f"  type: {route.get('mode')} ({route.get('route_type')})")
        print()


def print_route(data: dict[str, Any]) -> None:
    route = data["route"]
    short = route.get("route_short_name") or route.get("route_id")
    print(f"Metlink bus route {short}: {route.get('route_long_name')}")
    print(f"route_id {route['route_id']} | type {route.get('mode')} ({route.get('route_type')})")
    if route.get("route_desc"):
        print(route["route_desc"])
    print(f"Stops: {data['stops_total']} total, showing {data['stops_returned']} ({data['elapsed_ms']} ms)")
    print()
    for stop in data["stops"]:
        print(f"{stop['stop_id']}  {stop['stop_name']}")
        if latlon(stop):
            print(f"  {latlon(stop)}")
        print()


def print_stop(data: dict[str, Any]) -> None:
    stop = data["stop"]
    print(f"Metlink bus stop {stop['stop_id']}: {stop['stop_name']} ({data['elapsed_ms']} ms)")
    bits = [f"code {stop['stop_code']}" if stop.get("stop_code") else "", latlon(stop)]
    print("  " + " | ".join(x for x in bits if x))
    print("  routes: " + ", ".join(route.get("route_short_name") or route.get("route_id") for route in data["routes"]))
    print()
    print_arrivals(
        {
            "stop_id": data["stop_id"],
            "stop_name": stop["stop_name"],
            "total_arrivals": data["arrivals_total"],
            "returned": data["arrivals_returned"],
            "elapsed_ms": data["elapsed_ms"],
            "arrivals": data["arrivals"],
        }
    )


def print_arrivals(data: dict[str, Any]) -> None:
    print(
        f"Metlink bus arrivals for stop {data['stop_id']} ({data.get('stop_name') or 'unknown'}): "
        f"{data['total_arrivals']} total, "
        f"showing {data['returned']} ({data['elapsed_ms']} ms)"
    )
    print()
    for dep in data["arrivals"]:
        service = dep.get("service_id") or dep.get("route_id") or "-"
        destination = dep.get("destination") or "-"
        print(f"{service}  {destination}")
        bits = [
            dep.get("expected_departure") or dep.get("expected_arrival") or dep.get("aimed_departure"),
            dep.get("status"),
            dep.get("delay"),
            f"trip {dep['trip_id']}" if dep.get("trip_id") else "",
            f"vehicle {dep['vehicle_id']}" if dep.get("vehicle_id") else "",
        ]
        print("  " + " | ".join(str(x) for x in bits if x))
        print()


def print_alerts(data: dict[str, Any]) -> None:
    print(
        f"Metlink bus alerts: {data['total_alerts']} total, "
        f"showing {data['returned']} ({data['elapsed_ms']} ms)"
    )
    print()
    for alert in data["alerts"]:
        print(alert.get("header_text") or alert.get("id") or "Alert")
        bits = [alert.get("severity_level"), alert.get("effect"), alert.get("cause")]
        print("  " + " | ".join(x for x in bits if x))
        if alert.get("description_text"):
            print(f"  {alert['description_text'][:240]}")
        if alert.get("route_ids"):
            print("  routes: " + ", ".join(alert["route_ids"][:10]))
        if alert.get("stop_ids") and not alert.get("route_ids"):
            print("  stops: " + ", ".join(alert["stop_ids"][:10]))
        print()


def print_vehicles(data: dict[str, Any]) -> None:
    label = f" route={data['route']}" if data.get("route") else ""
    print(
        f"Metlink bus vehicles{label}: {data['total_vehicles']} total, "
        f"showing {data['returned']} ({data['elapsed_ms']} ms)"
    )
    print()
    for vehicle in data["vehicles"]:
        name = vehicle.get("label") or vehicle.get("vehicle_id") or vehicle.get("id") or "-"
        print(f"{name}  route {vehicle.get('route_id') or '-'}  trip {vehicle.get('trip_id') or '-'}")
        bits = [latlon({"stop_lat": vehicle.get("lat"), "stop_lon": vehicle.get("lon")}), vehicle.get("timestamp")]
        print("  " + " | ".join(str(x) for x in bits if x))
        print()


def latlon(row: dict[str, Any]) -> str:
    lat = row.get("stop_lat")
    lon = row.get("stop_lon")
    if lat in (None, "") or lon in (None, ""):
        return ""
    return f"{lat},{lon}"


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Lightweight read-only NZ buses CLI for Wellington region Metlink buses."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("stops", help="search Metlink bus stops")
    sp.add_argument("query", nargs="?", default=None, help="filter by stop name, code, id, or description")
    sp.add_argument("--near", help="sort by distance from a stop name/code/id or 'lat,lon'")
    sp.add_argument("--limit", type=positive_int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stops)

    sp = sub.add_parser("routes", help="list/search Metlink bus routes")
    sp.add_argument("--query", help="filter by route id, short name, long name, or description")
    sp.add_argument("--limit", type=positive_int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_routes)

    sp = sub.add_parser("route", help="show one Metlink bus route and its stops")
    sp.add_argument("route", help="route number, short name, or route_id")
    sp.add_argument("--limit", type=positive_int, default=40, help="maximum stops to show")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser("stop", help="show one Metlink bus stop with live arrivals")
    sp.add_argument("stop_id")
    sp.add_argument("--limit", type=positive_int, default=8, help="maximum arrivals to show")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stop)

    sp = sub.add_parser("arrivals", help="show live arrivals for a Metlink bus stop")
    sp.add_argument("stop_id")
    sp.add_argument("--limit", type=positive_int, default=12)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_arrivals)

    sp = sub.add_parser("vehicles", help="show live Metlink bus vehicle positions")
    sp.add_argument("--route", help="filter by route number, short name, or route_id")
    sp.add_argument("--limit", type=positive_int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_vehicles)

    sp = sub.add_parser("alerts", help="show active Metlink bus service alerts")
    sp.add_argument("--limit", type=positive_int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_alerts)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
