#!/usr/bin/env python3
"""Auckland Transport public transport CLI.

Read-only stdlib wrapper around the AT public GTFS and GTFS-RT APIs.
Provides stops, departures, alerts, vehicles, routes, and network status.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_URL = "https://api.at.govt.nz"
API_KEY = os.environ.get("AT_API_KEY", "de42128902d24a7a86a013633f7aa832")
UA = "at-transport-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 15

try:
    from zoneinfo import ZoneInfo
    NZ_TZ: dt.tzinfo = ZoneInfo("Pacific/Auckland")
except Exception:
    NZ_TZ = dt.timezone(dt.timedelta(hours=12), name="Pacific/Auckland")


def die(message: str, code: int = 1) -> None:
    print(f"at-transport: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    url = f"{BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Ocp-Apim-Subscription-Key": API_KEY,
        "User-Agent": UA,
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(url, headers=headers, timeout=timeout, accept="application/json")
        raw = body.decode("utf-8", "replace")
        return json.loads(raw) if raw else None
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(f"AT API {path}: {e}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


# --- Helpers ---

def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def format_nz_time(epoch_or_iso: Any) -> str:
    if not epoch_or_iso:
        return "??:??"
    try:
        if isinstance(epoch_or_iso, (int, float)):
            d = dt.datetime.fromtimestamp(epoch_or_iso, tz=NZ_TZ)
        else:
            d = dt.datetime.fromisoformat(str(epoch_or_iso).replace("Z", "+00:00")).astimezone(NZ_TZ)
        return d.strftime("%-I:%M %p").lower().replace("am", "am").replace("pm", "pm")
    except Exception:
        return str(epoch_or_iso)


def format_nz_full(epoch_or_iso: Any) -> str:
    if not epoch_or_iso:
        return "unknown"
    try:
        if isinstance(epoch_or_iso, (int, float)):
            d = dt.datetime.fromtimestamp(epoch_or_iso, tz=NZ_TZ)
        else:
            d = dt.datetime.fromisoformat(str(epoch_or_iso).replace("Z", "+00:00")).astimezone(NZ_TZ)
        return d.strftime("%d %b %Y, %-I:%M %p NZST")
    except Exception:
        return str(epoch_or_iso)


def format_delay(seconds: int) -> str:
    if abs(seconds) <= 60:
        return "(on time)"
    mins = round(seconds / 60)
    if mins > 0:
        return f"(+{mins} min late)"
    return f"({abs(mins)} min early)"


def format_distance(meters: int) -> str:
    if meters < 1000:
        return f"{meters}m"
    return f"{meters / 1000:.1f}km"


def route_type_name(route_type: int) -> str:
    names = {0: "Tram", 1: "Subway", 2: "Train", 3: "Bus", 4: "Ferry"}
    return names.get(route_type, "Transit")


def route_type_icon(route_type: int) -> str:
    icons = {0: "[Tram]", 1: "[Subway]", 2: "[Train]", 3: "[Bus]", 4: "[Ferry]"}
    return icons.get(route_type, "[Transit]")


def severity_label(level: str) -> str:
    labels = {"SEVERE": "MAJOR", "WARNING": "WARN", "INFO": "INFO"}
    return labels.get(level, level)


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    to_rad = lambda d: d * math.pi / 180
    d_lat = to_rad(lat2 - lat1)
    d_lon = to_rad(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_lat_lon(raw: str) -> tuple[float, float]:
    parts = raw.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected lat,lon (e.g. -36.844,174.768), got: {raw}")
    try:
        lat, lon = float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected lat,lon (e.g. -36.844,174.768), got: {raw}")
    return lat, lon


def positive_int(raw: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    if v <= 0:
        raise argparse.ArgumentTypeError(f"Expected positive integer, got: {raw}")
    return v


# --- GTFS Static ---

_stops_cache: list[dict] | None = None
_routes_cache: dict[str, dict] | None = None


def get_stops() -> list[dict]:
    global _stops_cache
    if _stops_cache is not None:
        return _stops_cache
    data = request_json("/gtfs/v3/stops", timeout=30)
    _stops_cache = [item["attributes"] for item in (data or {}).get("data", [])]
    return _stops_cache


def get_stop(stop_id: str) -> dict:
    data = request_json(f"/gtfs/v3/stops/{urllib.parse.quote(stop_id)}")
    return (data or {}).get("data", {}).get("attributes", {})


def get_routes_map() -> dict[str, dict]:
    global _routes_cache
    if _routes_cache is not None:
        return _routes_cache
    data = request_json("/gtfs/v3/routes", timeout=30)
    _routes_cache = {
        item["attributes"]["route_id"]: item["attributes"]
        for item in (data or {}).get("data", [])
        if item.get("attributes", {}).get("route_id")
    }
    return _routes_cache


def get_route(route_id: str) -> dict:
    data = request_json(f"/gtfs/v3/routes/{urllib.parse.quote(route_id)}")
    attrs = (data or {}).get("data", {}).get("attributes", {})
    if not attrs:
        die(f"Route not found: {route_id}. Use the full route ID (e.g. STH-201).")
    return attrs


def search_stops(query: str) -> list[dict]:
    stops = get_stops()
    lower = query.lower()
    return [
        s for s in stops
        if lower in s.get("stop_name", "").lower()
        or s.get("stop_code", "").lower() == lower
        or s.get("stop_id", "").lower() == lower
    ]


def nearby_stops(lat: float, lon: float, radius_m: int = 500) -> list[dict]:
    stops = get_stops()
    results = []
    for s in stops:
        dist = haversine_meters(lat, lon, s.get("stop_lat", 0), s.get("stop_lon", 0))
        if dist <= radius_m:
            results.append({**s, "distance_m": round(dist)})
    results.sort(key=lambda s: s["distance_m"])
    return results


# --- GTFS-RT Realtime ---

def get_service_alerts() -> list[dict]:
    data = request_json("/realtime/legacy/servicealerts")
    entities = (data or {}).get("response", {}).get("entity", [])
    alerts = []
    for e in entities:
        a = e.get("alert", {})
        header = (a.get("header_text") or {}).get("translation", [{}])[0].get("text", "")
        desc = (a.get("description_text") or {}).get("translation", [{}])[0].get("text", "")
        alerts.append({
            "id": e.get("id", ""),
            "active_period": a.get("active_period", []),
            "informed_entity": a.get("informed_entity", []),
            "cause": a.get("cause", ""),
            "effect": a.get("effect", ""),
            "severity_level": a.get("severity_level") or "UNKNOWN",
            "header_text": header,
            "description_text": desc,
        })
    return alerts


def get_trip_updates() -> list[dict]:
    data = request_json("/realtime/legacy/tripupdates")
    entities = (data or {}).get("response", {}).get("entity", [])
    updates = []
    for e in entities:
        tu = e.get("trip_update", {})
        stu = tu.get("stop_time_update", {})
        if not stu.get("stop_id"):
            continue
        updates.append({
            "id": e.get("id", ""),
            "trip": tu.get("trip", {}),
            "stop_time_update": stu,
            "vehicle": tu.get("vehicle"),
            "timestamp": tu.get("timestamp", 0),
            "delay": tu.get("delay", 0),
        })
    return updates


def get_vehicle_positions() -> list[dict]:
    data = request_json("/realtime/legacy/vehiclelocations")
    entities = (data or {}).get("response", {}).get("entity", [])
    vehicles = []
    for e in entities:
        v = e.get("vehicle", {})
        vehicles.append({
            "id": e.get("id", ""),
            "position": v.get("position", {}),
            "trip": v.get("trip"),
            "vehicle": v.get("vehicle", {}),
            "timestamp": v.get("timestamp", 0),
        })
    return vehicles


def resolve_stop_ids(stop_input: str) -> set:
    stops = get_stops()
    ids = set()
    match = next(
        (s for s in stops if s.get("stop_id") == stop_input or s.get("stop_code") == stop_input),
        None,
    )
    if match:
        ids.add(match["stop_id"])
        if match.get("location_type") == 1:
            for s in stops:
                if s.get("parent_station") == match["stop_id"]:
                    ids.add(s["stop_id"])
        if match.get("parent_station"):
            ids.add(match["parent_station"])
            for s in stops:
                if s.get("parent_station") == match["parent_station"]:
                    ids.add(s["stop_id"])
    return ids


def get_departures(stop_input: str) -> dict:
    stops = get_stops()
    match = next(
        (s for s in stops if s.get("stop_id") == stop_input or s.get("stop_code") == stop_input),
        None,
    )
    if not match:
        die(f"Stop not found: {stop_input}. Use 'stops <query>' to search.")

    stop_ids = resolve_stop_ids(stop_input)
    trip_updates = get_trip_updates()
    routes_map = get_routes_map()
    stop_name_map = {s["stop_id"]: s.get("stop_name", s["stop_id"]) for s in stops}

    departures = []
    for tu in trip_updates:
        stu = tu["stop_time_update"]
        if stu.get("stop_id") not in stop_ids:
            continue
        route = routes_map.get(tu["trip"].get("route_id", ""), {})
        dep_time = (stu.get("departure") or {}).get("time") or (stu.get("arrival") or {}).get("time")
        delay = (
            (stu.get("departure") or {}).get("delay")
            or (stu.get("arrival") or {}).get("delay")
            or tu.get("delay", 0)
        )
        expected_time = None
        if dep_time:
            expected_time = dt.datetime.fromtimestamp(dep_time, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        departures.append({
            "route_id": tu["trip"].get("route_id", ""),
            "route_short_name": route.get("route_short_name") or tu["trip"].get("route_id", ""),
            "route_type": route.get("route_type", 3),
            "trip_id": tu["trip"].get("trip_id", ""),
            "stop_id": stu.get("stop_id", ""),
            "stop_name": stop_name_map.get(stu.get("stop_id", ""), stu.get("stop_id", "")),
            "direction_id": tu["trip"].get("direction_id", 0),
            "scheduled_time": tu["trip"].get("start_time", ""),
            "expected_time": expected_time,
            "delay_seconds": delay or 0,
            "vehicle_id": (tu.get("vehicle") or {}).get("id"),
            "vehicle_label": ((tu.get("vehicle") or {}).get("label") or "").strip() or None,
        })

    departures.sort(key=lambda d: (
        dt.datetime.fromisoformat(d["expected_time"].replace("Z", "+00:00")).timestamp()
        if d["expected_time"] else 0
    ) or d["scheduled_time"])

    return {"stop": match, "departures": departures}


def get_network_status() -> dict:
    # These are three independent realtime endpoints. Fetch them concurrently so
    # `status` stays inside the 30s smoke-test budget even when one AT endpoint is
    # sluggish. Sequential calls can legitimately take 35–45s with the existing
    # 15s per-request timeout.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        alerts_future = executor.submit(get_service_alerts)
        trips_future = executor.submit(get_trip_updates)
        vehicles_future = executor.submit(get_vehicle_positions)
        alerts = alerts_future.result()
        trip_updates = trips_future.result()
        vehicles = vehicles_future.result()

    by_severity: dict[str, int] = {}
    for a in alerts:
        lvl = a["severity_level"]
        by_severity[lvl] = by_severity.get(lvl, 0) + 1

    active = [t for t in trip_updates if t["trip"].get("schedule_relationship") != 3]
    delayed = [t for t in active if abs(t.get("delay", 0)) > 120]
    total_delay = sum(t.get("delay", 0) for t in active)
    avg_delay = total_delay / len(active) if active else 0
    on_time = [t for t in active if abs(t.get("delay", 0)) <= 120]
    on_time_pct = (len(on_time) / len(active)) * 100 if active else 100

    return {
        "timestamp": now_utc(),
        "alerts_count": len(alerts),
        "alerts_by_severity": by_severity,
        "active_trips": len(active),
        "active_vehicles": len(vehicles),
        "delayed_trips": len(delayed),
        "avg_delay_seconds": round(avg_delay),
        "on_time_percentage": round(on_time_pct * 10) / 10,
    }


# --- Commands ---

def emit(data: Any, as_json: bool, render_fn) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_fn())


def cmd_alerts(args: argparse.Namespace) -> None:
    alerts = get_service_alerts()
    now_ts = time.time()
    active = [
        a for a in alerts
        if any(
            (p.get("start") or 0) <= now_ts <= (p.get("end") if p.get("end") is not None else now_ts + 1)
            for p in a.get("active_period", [])
        )
    ]
    limited = active[: args.limit] if args.limit else active

    output = {
        "timestamp": now_utc(),
        "total_active": len(active),
        "returned": len(limited),
        "alerts": limited,
    }

    def render() -> str:
        if not active:
            return "No active service alerts."
        lines = [f"SERVICE ALERTS ({len(active)} active)"]
        for a in limited:
            lines.append(f"  [{severity_label(a['severity_level'])}] {a['header_text']}")
            if a.get("description_text"):
                desc = a["description_text"]
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                lines.append(f"         {desc.replace(chr(10), chr(10) + '         ')}")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_departures(args: argparse.Namespace) -> None:
    result = get_departures(args.stop_id)
    limit = args.limit or 15
    departures = result["departures"][:limit]
    stop = result["stop"]

    output = {
        "stop": stop,
        "total_departures": len(result["departures"]),
        "returned": len(departures),
        "departures": departures,
    }

    def render() -> str:
        lines = [
            f"Departures from {stop.get('stop_name')} (Stop {stop.get('stop_code')})",
            "──────────────────────────────────────────",
        ]
        if not departures:
            lines.append("  No real-time departures currently tracked for this stop.")
            return "\n".join(lines)
        for d in departures:
            icon = route_type_icon(d.get("route_type", 3))
            t = format_nz_time(d["expected_time"]) if d["expected_time"] else d["scheduled_time"]
            delay = format_delay(d.get("delay_seconds", 0))
            route_name = d.get("route_short_name", "")
            lines.append(f"  {icon} Route {route_name:<6} Due {t:<10} {delay}")
        lines.append("")
        lines.append(f"  {len(result['departures'])} total departures tracked")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_stops(args: argparse.Namespace) -> None:
    results = search_stops(args.query)
    limit = args.limit or 20
    limited = results[:limit]

    output = {
        "query": args.query,
        "total_matches": len(results),
        "returned": len(limited),
        "stops": limited,
    }

    def render() -> str:
        if not results:
            return f'No stops found matching "{args.query}".'
        lines = [f'Stops matching "{args.query}" ({len(results)} found)', "──────────────────────────────────────────"]
        for s in limited:
            type_label = " [Station]" if s.get("location_type") == 1 else ""
            platform = f" (Platform {s['platform_code']})" if s.get("platform_code") else ""
            lines.append(f"  {s.get('stop_code', ''):<8} {s.get('stop_name', '')}{type_label}{platform}")
            lines.append(f"           ID: {s.get('stop_id')}  ({s.get('stop_lat', 0):.5f}, {s.get('stop_lon', 0):.5f})")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_nearby(args: argparse.Namespace) -> None:
    lat, lon = args.location
    radius = args.radius or 500
    limit = args.limit or 20
    results = nearby_stops(lat, lon, radius)
    limited = results[:limit]

    output = {
        "location": {"lat": lat, "lon": lon},
        "radius_m": radius,
        "total_nearby": len(results),
        "returned": len(limited),
        "stops": limited,
    }

    def render() -> str:
        if not results:
            return f"No stops found within {radius}m of {lat},{lon}."
        lines = [
            f"Stops within {format_distance(radius)} of {lat:.5f},{lon:.5f} ({len(results)} found)",
            "──────────────────────────────────────────",
        ]
        for s in limited:
            type_label = " [Station]" if s.get("location_type") == 1 else ""
            dist = format_distance(s.get("distance_m", 0))
            lines.append(f"  {dist:<6} {s.get('stop_code', ''):<8} {s.get('stop_name', '')}{type_label}")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_route(args: argparse.Namespace) -> None:
    try:
        route = get_route(args.route_id)
    except SystemExit:
        # Try short-name lookup
        routes_map = get_routes_map()
        match = next(
            (r for r in routes_map.values() if r.get("route_short_name", "").lower() == args.route_id.lower()),
            None,
        )
        if not match:
            die(f"Route not found: {args.route_id}. Use the full route ID (e.g. STH-201).")
        route = match

    def render() -> str:
        icon = route_type_icon(route.get("route_type", 3))
        lines = [
            f"{icon} Route {route.get('route_short_name')}",
            "──────────────────────────────────────────",
            f"  ID:       {route.get('route_id')}",
            f"  Name:     {route.get('route_long_name')}",
            f"  Type:     {route_type_name(route.get('route_type', 3))}",
            f"  Agency:   {route.get('agency_id')}",
        ]
        if route.get("route_color"):
            lines.append(f"  Color:    #{route['route_color']}")
        return "\n".join(lines)

    emit(route, args.json, render)


def cmd_vehicles(args: argparse.Namespace) -> None:
    limit = args.limit or 20
    vehicles = get_vehicle_positions()

    if args.route:
        vehicles = [v for v in vehicles if (v.get("trip") or {}).get("route_id") == args.route]

    vehicles.sort(key=lambda v: v.get("timestamp", 0), reverse=True)
    limited = vehicles[:limit]

    simplified = [
        {
            "vehicle_id": v["id"],
            "label": v.get("vehicle", {}).get("label"),
            "lat": v.get("position", {}).get("latitude"),
            "lon": v.get("position", {}).get("longitude"),
            "speed": v.get("position", {}).get("speed"),
            "bearing": v.get("position", {}).get("bearing"),
            "route_id": (v.get("trip") or {}).get("route_id"),
            "trip_id": (v.get("trip") or {}).get("trip_id"),
            "last_update": dt.datetime.fromtimestamp(v["timestamp"], tz=dt.timezone.utc).isoformat().replace("+00:00", "Z") if v.get("timestamp") else None,
        }
        for v in limited
    ]

    output = {
        "timestamp": now_utc(),
        "filter_route": args.route or None,
        "total_vehicles": len(vehicles),
        "returned": len(limited),
        "vehicles": simplified,
    }

    def render() -> str:
        route_label = f" on route {args.route}" if args.route else ""
        lines = [f"Live vehicles{route_label} ({len(vehicles)} total)", "──────────────────────────────────────────"]
        if not simplified:
            lines.append("  No vehicles currently tracked.")
            return "\n".join(lines)
        for v in simplified:
            route = v.get("route_id") or "unknown"
            spd = v.get("speed") or 0
            speed_str = f"{spd * 3.6:.0f} km/h" if spd and spd > 0 else "stopped"
            label = (v.get("label") or "").strip() or v.get("vehicle_id", "")
            lat = v.get("lat") or 0
            lon = v.get("lon") or 0
            lines.append(f"  {label:<18} Route {route:<10} {speed_str:<10} ({lat:.4f}, {lon:.4f})")
        return "\n".join(lines)

    emit(output, args.json, render)


def cmd_status(args: argparse.Namespace) -> None:
    status = get_network_status()

    def render() -> str:
        lines = [
            "Auckland Transport Network Status",
            f"   {format_nz_full(status['timestamp'])}",
            "──────────────────────────────────────────",
            f"  Active trips:     {status['active_trips']}",
            f"  Active vehicles:  {status['active_vehicles']}",
            f"  On-time:          {status['on_time_percentage']}%",
            f"  Delayed trips:    {status['delayed_trips']}",
            f"  Avg delay:        {status['avg_delay_seconds']}s",
            f"  Service alerts:   {status['alerts_count']}",
        ]
        if status.get("alerts_by_severity"):
            sev_parts = ", ".join(f"{severity_label(k)}: {v}" for k, v in status["alerts_by_severity"].items())
            lines.append(f"  Alert breakdown:  {sev_parts}")
        return "\n".join(lines)

    emit(status, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Query live Auckland Transport public transport data — stops, departures, alerts, vehicles, and network status."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    # alerts
    sp = sub.add_parser("alerts", help="show active service alerts and disruptions")
    sp.add_argument("--limit", type=positive_int, help="limit number of alerts")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_alerts)

    # departures
    sp = sub.add_parser("departures", help="show next departures from a stop (real-time)")
    sp.add_argument("stop_id", help="stop code (e.g. 11814) or full stop ID")
    sp.add_argument("--limit", type=positive_int, help="limit departures shown (default 15)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_departures)

    # stops
    sp = sub.add_parser("stops", help="search for stops by name or code")
    sp.add_argument("query", help="search term (stop name, code, or ID)")
    sp.add_argument("--limit", type=positive_int, help="limit results (default 20)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stops)

    # nearby
    sp = sub.add_parser("nearby", help="find stops near a location")
    sp.add_argument("--location", required=True, type=parse_lat_lon, metavar="LAT,LON",
                    help="latitude,longitude (e.g. --location=-36.844,174.768)")
    sp.add_argument("--radius", type=positive_int, help="search radius in meters (default 500)")
    sp.add_argument("--limit", type=positive_int, help="limit results (default 20)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_nearby)

    # route
    sp = sub.add_parser("route", help="show info about a specific route")
    sp.add_argument("route_id", help="route ID (e.g. STH-201, 70-221)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_route)

    # vehicles
    sp = sub.add_parser("vehicles", help="show live vehicle positions, optionally filtered by route")
    sp.add_argument("--route", help="filter by route ID")
    sp.add_argument("--limit", type=positive_int, help="limit results (default 20)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_vehicles)

    # status
    sp = sub.add_parser("status", help="show overall Auckland Transport network status summary")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
