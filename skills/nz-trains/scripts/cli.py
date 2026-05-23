#!/usr/bin/env python3
"""Metlink Wellington trains read-only CLI.

Self-contained stdlib wrapper around Metlink GTFS and GTFS-RT JSON endpoints.
Requires METLINK_API_KEY. No login, browser automation, writes, or third-party
dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - old Python fallback
    ZoneInfo = None  # type: ignore[assignment]


BASE_API = "https://api.opendata.metlink.org.nz/v1"
UA = os.environ.get("NZ_TRAINS_USER_AGENT", "thecolab-nz-trains-skill/1.0")
NZ_TZ = ZoneInfo("Pacific/Auckland") if ZoneInfo else timezone.utc

LINE_ORDER = ["JVL", "KPL", "HVL", "MEL", "WRL"]
LINE_META: dict[str, dict[str, Any]] = {
    "JVL": {
        "name": "Johnsonville Line",
        "termini": ("WELL1", "JOHN"),
        "aliases": ("jvl", "johnsonville", "johnsonville line"),
    },
    "KPL": {
        "name": "Kapiti Line",
        "termini": ("WELL1", "WAIK"),
        "aliases": ("kpl", "kapiti", "kapiti line", "waikanae"),
    },
    "HVL": {
        "name": "Hutt Valley Line",
        "termini": ("WELL1", "UPPE"),
        "aliases": ("hvl", "hutt", "hutt valley", "hutt valley line", "upper hutt"),
    },
    "MEL": {
        "name": "Melling Line",
        "termini": ("WELL1", "WEST"),
        "aliases": ("mel", "melling", "melling line", "western hutt"),
    },
    "WRL": {
        "name": "Wairarapa Line",
        "termini": ("WELL1", "MAST"),
        "aliases": ("wrl", "wairarapa", "wairarapa line", "masterton"),
    },
}

LINE_STATION_IDS: dict[str, list[str]] = {
    "JVL": ["WELL", "CROF", "NGAI", "AWAR", "SIML", "BOXH", "KHAN", "RARO", "JOHN"],
    "KPL": ["WELL", "NGAU", "TAKA", "REDW", "TAWA", "LIND", "KENE", "PORI", "PARE", "MANA", "PLIM", "PUKE", "PAEK", "PARA", "WAIK"],
    "HVL": ["WELL", "NGAU", "PETO", "AVA", "WOBU", "WATE", "EPUN", "NAEN", "TAIT", "WING", "POMA", "MANO", "SILV", "HERE", "TREN", "WALL", "UPPE"],
    "MEL": ["WELL", "NGAU", "PETO", "WEST"],
    "WRL": ["WELL", "PETO", "WATE", "UPPE", "MAYM", "FEAT", "WOOD", "MATA", "CART", "SOLW", "RENA", "MAST"],
}

SCHEDULE_REL = {
    0: "SCHEDULED",
    1: "ADDED",
    2: "UNSCHEDULED",
    3: "CANCELED",
}

_CACHE: dict[Any, Any] = {}


class CliError(Exception):
    """Expected user-facing CLI error."""


def die(message: str, code: int = 1) -> None:
    print(f"nz-trains: {message}", file=sys.stderr)
    raise SystemExit(code)


def require_api_key() -> str:
    key = os.environ.get("METLINK_API_KEY")
    if not key:
        raise CliError("METLINK_API_KEY is required; export it before running data commands")
    return key


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = BASE_API + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json",
        "User-Agent": UA,
        "x-api-key": require_api_key(),
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = raw[:300].strip()
        try:
            payload = json.loads(raw)
            detail = payload.get("error") or payload.get("message") or detail
        except Exception:
            pass
        if e.code in (401, 403):
            raise CliError(f"authentication failed calling {path}; check METLINK_API_KEY")
        if e.code == 429:
            raise CliError(f"rate limited calling {path}; retry later or narrow the query")
        raise CliError(f"HTTP {e.code} from {path}: {detail}")
    except urllib.error.URLError as e:
        raise CliError(f"network error calling {path}: {e.reason}")
    except json.JSONDecodeError as e:
        raise CliError(f"invalid JSON from {path}: {e}")


def cached(key: Any, loader: Any) -> Any:
    if key not in _CACHE:
        _CACHE[key] = loader()
    return _CACHE[key]


def norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def route_id(value: Any) -> str:
    return str(value if value is not None else "")


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected a positive integer, received {raw!r}") from e
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive integer, received {raw!r}")
    return value


def fetch_routes() -> list[dict[str, Any]]:
    return cached("routes", lambda: request_json("/gtfs/routes"))


def train_routes() -> list[dict[str, Any]]:
    def load() -> list[dict[str, Any]]:
        rows = []
        for route in fetch_routes() or []:
            short = str(route.get("route_short_name") or "")
            if int_or_none(route.get("route_type")) == 2 and short in LINE_META:
                row = dict(route)
                row["route_id"] = route_id(row.get("route_id"))
                row["route_short_name"] = short
                row["line_name"] = LINE_META[short]["name"]
                rows.append(row)
        rows.sort(key=lambda r: LINE_ORDER.index(r["route_short_name"]))
        return rows

    return cached("train_routes", load)


def routes_by_id() -> dict[str, dict[str, Any]]:
    return {route_id(r.get("route_id")): r for r in train_routes()}


def routes_by_short() -> dict[str, dict[str, Any]]:
    return {str(r.get("route_short_name")): r for r in train_routes()}


def resolve_line(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    needle = norm_text(raw)
    by_short = routes_by_short()
    for short, route in by_short.items():
        aliases = {norm_text(short), norm_text(route.get("route_id")), norm_text(route.get("route_long_name"))}
        aliases.update(norm_text(a) for a in LINE_META[short]["aliases"])
        if needle in aliases:
            return route
    expected = ", ".join(LINE_ORDER)
    raise CliError(f"unknown train line {raw!r}; expected one of {expected}")


def fetch_stops() -> list[dict[str, Any]]:
    return cached("stops", lambda: request_json("/gtfs/stops"))


def stops_by_id() -> dict[str, dict[str, Any]]:
    return cached("stops_by_id", lambda: {str(s.get("stop_id")): s for s in fetch_stops() or []})


def normalize_station_id(stop_id: str) -> str:
    stop = stops_by_id().get(str(stop_id))
    parent = stop.get("parent_station") if stop else None
    return str(parent or stop_id)


def stop_record(stop: dict[str, Any], *, lines: list[str] | None = None) -> dict[str, Any]:
    out = {
        "stop_id": str(stop.get("stop_id") or ""),
        "stop_code": str(stop.get("stop_code") or ""),
        "stop_name": stop.get("stop_name") or "",
        "zone_id": stop.get("zone_id") or "",
        "lat": stop.get("stop_lat"),
        "lon": stop.get("stop_lon"),
        "location_type": stop.get("location_type"),
        "parent_station": stop.get("parent_station") or "",
    }
    if lines is not None:
        out["lines"] = lines
    return out


def line_stations(line_short: str) -> list[dict[str, Any]]:
    def load() -> list[dict[str, Any]]:
        stops = stops_by_id()
        rows: list[dict[str, Any]] = []
        for station_id in LINE_STATION_IDS[line_short]:
            stop = stops.get(station_id)
            if not stop:
                continue
            rec = stop_record(stop, lines=[line_short])
            rec["line"] = line_short
            rows.append(rec)
        return rows

    return cached(("line_stations", line_short), load)


def all_stations(line_short: str | None = None) -> list[dict[str, Any]]:
    if line_short:
        return line_stations(line_short)
    merged: dict[str, dict[str, Any]] = {}
    for short in LINE_ORDER:
        for station in line_stations(short):
            sid = station["stop_id"]
            if sid not in merged:
                merged[sid] = {k: v for k, v in station.items() if k not in ("line", "lines")}
                merged[sid]["lines"] = []
            if short not in merged[sid]["lines"]:
                merged[sid]["lines"].append(short)
    return list(merged.values())


def station_line_index() -> dict[str, set[str]]:
    def load() -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}
        for short in LINE_ORDER:
            for station in line_stations(short):
                sid = station["stop_id"]
                index.setdefault(sid, set()).add(short)
        for stop in fetch_stops() or []:
            sid = str(stop.get("stop_id") or "")
            parent = str(stop.get("parent_station") or "")
            if parent in index:
                index.setdefault(sid, set()).update(index[parent])
        return index

    return cached("station_line_index", load)


def is_train_station_stop(stop: dict[str, Any]) -> bool:
    sid = str(stop.get("stop_id") or "")
    parent = str(stop.get("parent_station") or "")
    if sid in station_line_index() or parent in station_line_index():
        return True
    if "cable car" in norm_text(stop.get("stop_name")):
        return False
    return bool(re.fullmatch(r"[A-Z]+[0-9]*", sid) or re.fullmatch(r"[A-Z]+", parent))


def resolve_station(query: str) -> tuple[dict[str, Any], bool]:
    q = query.strip()
    stops = stops_by_id()
    exact = stops.get(q) or stops.get(q.upper())
    if exact:
        return exact, is_train_station_stop(exact)

    needle = norm_text(q)
    matches = []
    for stop in fetch_stops() or []:
        sid = str(stop.get("stop_id") or "")
        code = str(stop.get("stop_code") or "")
        name = str(stop.get("stop_name") or "")
        if needle and (
            needle == norm_text(sid)
            or needle == norm_text(code)
            or needle in norm_text(name)
        ):
            trainish = is_train_station_stop(stop)
            matches.append((stop, trainish))
    if not matches:
        raise CliError(f"no Metlink stop or train station matched {query!r}")

    def sort_key(item: tuple[dict[str, Any], bool]) -> tuple[int, int, int, int]:
        stop, trainish = item
        exact_name = norm_text(stop.get("stop_name")) == needle
        parent = int_or_none(stop.get("location_type")) == 1
        has_parent = bool(stop.get("parent_station"))
        return (
            0 if trainish else 1,
            0 if exact_name else 1,
            0 if parent else 1 if not has_parent else 2,
            len(str(stop.get("stop_name") or "")),
        )

    matches.sort(key=sort_key)
    return matches[0]


def parse_duration_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    text = text[1:] if text[:1] in "+-" else text
    m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
    if not m:
        return None
    hours, minutes, seconds = (int(part or 0) for part in m.groups())
    return sign * (hours * 3600 + minutes * 60 + seconds)


def delay_text(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if abs(seconds) < 60:
        return "on time"
    minutes = round(abs(seconds) / 60)
    if seconds > 0:
        return f"+{minutes} min late"
    return f"{minutes} min early"


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.search(r"[+-]\d{4}$", text):
        text = text[:-5] + text[-5:-2] + ":" + text[-2:]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NZ_TZ)
    return dt


def format_time(value: Any) -> str:
    dt = parse_datetime(value)
    if not dt:
        return str(value or "-")
    return dt.astimezone(NZ_TZ).strftime("%a %H:%M")


def format_timestamp(value: Any) -> str:
    dt = parse_datetime(value)
    if not dt:
        return str(value or "-")
    return dt.astimezone(NZ_TZ).strftime("%Y-%m-%d %H:%M %Z")


def translated_text(obj: Any) -> str:
    if not isinstance(obj, dict):
        return ""
    translations = obj.get("translation") or []
    if not isinstance(translations, list):
        return ""
    for item in translations:
        if isinstance(item, dict) and item.get("language") == "en":
            return str(item.get("text") or "")
    for item in translations:
        if isinstance(item, dict) and item.get("text") is not None:
            return str(item.get("text") or "")
    return ""


def active_periods(periods: Any) -> bool:
    items = listify(periods)
    if not items:
        return True
    now = time.time()
    for item in items:
        if not isinstance(item, dict):
            continue
        start = float(item.get("start") or 0)
        end_raw = item.get("end")
        end = float(end_raw) if end_raw else float("inf")
        if start <= now <= end:
            return True
    return False


def parse_arrival(item: dict[str, Any]) -> dict[str, Any]:
    departure = item.get("departure") or {}
    arrival = item.get("arrival") or {}
    aimed = departure.get("aimed") or arrival.get("aimed")
    expected = departure.get("expected") or arrival.get("expected")
    delay = parse_duration_seconds(item.get("delay"))
    service_id = str(item.get("service_id") or "")
    return {
        "line": service_id,
        "line_name": LINE_META.get(service_id, {}).get("name", service_id),
        "stop_id": item.get("stop_id"),
        "platform_name": item.get("name"),
        "direction": item.get("direction"),
        "origin": item.get("origin") or {},
        "destination": item.get("destination") or {},
        "aimed": aimed,
        "expected": expected,
        "delay_seconds": delay,
        "delay": delay_text(delay),
        "status": item.get("status") or ("delayed" if delay and delay >= 60 else "ontime"),
        "monitored": bool(item.get("monitored")),
        "vehicle_id": item.get("vehicle_id"),
        "trip_id": item.get("trip_id"),
        "trip_headsign": item.get("trip_headsign"),
        "wheelchair_accessible": item.get("wheelchair_accessible"),
    }


def station_arrivals(query: str, limit: int) -> dict[str, Any]:
    stop, trainish = resolve_station(query)
    prediction_stop_id = str(stop.get("parent_station") or stop.get("stop_id"))
    payload = request_json("/stop-predictions", {"stop_id": prediction_stop_id}) or {}
    departures = payload.get("departures") or []
    arrivals = [
        parse_arrival(d)
        for d in departures
        if isinstance(d, dict) and str(d.get("service_id") or "") in LINE_META
    ]
    arrivals = arrivals[:limit]
    return {
        "query": query,
        "station": stop_record(stop),
        "is_train_station": trainish,
        "prediction_stop_id": prediction_stop_id,
        "farezone": payload.get("farezone"),
        "closed": payload.get("closed"),
        "total_train_arrivals": len([d for d in departures if isinstance(d, dict) and str(d.get("service_id") or "") in LINE_META]),
        "returned": len(arrivals),
        "arrivals": arrivals,
    }


def stop_name(stop_id: Any) -> str:
    sid = str(stop_id or "")
    stop = stops_by_id().get(sid) or stops_by_id().get(normalize_station_id(sid))
    return str(stop.get("stop_name") or sid) if stop else sid


def event_delay_seconds(update: dict[str, Any]) -> int | None:
    for key in ("arrival", "departure"):
        event = update.get(key) or {}
        if isinstance(event, dict) and event.get("delay") is not None:
            return int_or_none(event.get("delay"))
    return None


def event_time(update: dict[str, Any]) -> int | None:
    for key in ("arrival", "departure"):
        event = update.get(key) or {}
        if isinstance(event, dict) and event.get("time") is not None:
            return int_or_none(event.get("time"))
    return None


def trip_update_rows(line_short: str | None = None) -> list[dict[str, Any]]:
    route_map = routes_by_id()
    wanted_route_id = route_id(resolve_line(line_short).get("route_id")) if line_short else None
    payload = request_json("/gtfs-rt/tripupdates") or {}
    rows: list[dict[str, Any]] = []
    for entity in payload.get("entity") or []:
        update = entity.get("trip_update") if isinstance(entity, dict) else None
        if not isinstance(update, dict):
            continue
        trip = update.get("trip") or {}
        rid = route_id(trip.get("route_id"))
        if rid not in route_map or (wanted_route_id and rid != wanted_route_id):
            continue
        route = route_map[rid]
        vehicle = update.get("vehicle") or {}
        stop_updates = listify(update.get("stop_time_update")) or [{}]
        for stop_update in stop_updates:
            if not isinstance(stop_update, dict):
                continue
            delay = event_delay_seconds(stop_update)
            rel_code = int_or_none(trip.get("schedule_relationship"))
            stop_rel_code = int_or_none(stop_update.get("schedule_relationship"))
            rel = SCHEDULE_REL.get(rel_code if rel_code is not None else stop_rel_code, "UNKNOWN")
            cancelled = rel == "CANCELED" or SCHEDULE_REL.get(stop_rel_code) == "CANCELED"
            sid = stop_update.get("stop_id")
            rows.append({
                "line": route.get("route_short_name"),
                "line_name": route.get("line_name"),
                "route_id": rid,
                "trip_id": trip.get("trip_id"),
                "direction_id": trip.get("direction_id"),
                "start_date": trip.get("start_date"),
                "start_time": trip.get("start_time"),
                "vehicle_id": vehicle.get("id"),
                "stop_id": sid,
                "stop_name": stop_name(sid),
                "stop_sequence": stop_update.get("stop_sequence"),
                "event_time": event_time(stop_update),
                "delay_seconds": delay,
                "delay": delay_text(delay),
                "schedule_relationship": rel,
                "cancelled": cancelled,
                "feed_timestamp": (payload.get("header") or {}).get("timestamp"),
                "entity_id": entity.get("id"),
            })
    rows.sort(key=lambda r: ((r.get("cancelled") is not True), -(r.get("delay_seconds") or 0)))
    return rows


def delayed_rows(line_short: str | None = None) -> list[dict[str, Any]]:
    rows = trip_update_rows(line_short)
    return [r for r in rows if r.get("cancelled") or (r.get("delay_seconds") or 0) >= 60]


def vehicle_rows(line_short: str | None = None) -> list[dict[str, Any]]:
    route_map = routes_by_id()
    wanted_route_id = route_id(resolve_line(line_short).get("route_id")) if line_short else None
    payload = request_json("/gtfs-rt/vehiclepositions") or {}
    rows: list[dict[str, Any]] = []
    for entity in payload.get("entity") or []:
        vehicle = entity.get("vehicle") if isinstance(entity, dict) else None
        if not isinstance(vehicle, dict):
            continue
        trip = vehicle.get("trip") or {}
        rid = route_id(trip.get("route_id"))
        if rid not in route_map or (wanted_route_id and rid != wanted_route_id):
            continue
        route = route_map[rid]
        pos = vehicle.get("position") or {}
        vehicle_info = vehicle.get("vehicle") or {}
        rows.append({
            "line": route.get("route_short_name"),
            "line_name": route.get("line_name"),
            "route_id": rid,
            "trip_id": trip.get("trip_id"),
            "direction_id": trip.get("direction_id"),
            "start_date": trip.get("start_date"),
            "start_time": trip.get("start_time"),
            "vehicle_id": vehicle_info.get("id"),
            "lat": pos.get("latitude"),
            "lon": pos.get("longitude"),
            "bearing": pos.get("bearing"),
            "speed": pos.get("speed"),
            "timestamp": vehicle.get("timestamp"),
            "entity_id": entity.get("id"),
        })
    rows.sort(key=lambda r: (LINE_ORDER.index(r["line"]), str(r.get("vehicle_id") or "")))
    return rows


def alert_lines(alert: dict[str, Any]) -> set[str]:
    route_map = routes_by_id()
    station_index = station_line_index()
    lines: set[str] = set()
    entities = alert.get("informed_entity") or []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        rid = route_id(ent.get("route_id"))
        if rid in route_map:
            lines.add(str(route_map[rid].get("route_short_name")))
        if int_or_none(ent.get("route_type")) == 2 and not rid:
            lines.update(LINE_ORDER)
        stop_id = ent.get("stop_id")
        if stop_id:
            sid = str(stop_id)
            norm_id = normalize_station_id(sid)
            lines.update(station_index.get(sid, set()))
            lines.update(station_index.get(norm_id, set()))
        trip_id = str(ent.get("trip_id") or "")
        for short in LINE_ORDER:
            if trip_id.startswith(short + "__"):
                lines.add(short)

    text = norm_text((alert.get("header_text") or "") + " " + (alert.get("description_text") or ""))
    for short, meta in LINE_META.items():
        terms = {norm_text(short), norm_text(meta["name"])}
        if any(term and re.search(rf"(^| ){re.escape(term)}( |$)", text) for term in terms):
            lines.add(short)
    return lines


def alert_rows(line_short: str | None = None) -> list[dict[str, Any]]:
    payload = request_json("/gtfs-rt/servicealerts") or {}
    wanted = resolve_line(line_short).get("route_short_name") if line_short else None
    rows: list[dict[str, Any]] = []
    for entity in payload.get("entity") or []:
        alert = entity.get("alert") if isinstance(entity, dict) else None
        if not isinstance(alert, dict):
            continue
        header = translated_text(alert.get("header_text"))
        desc = translated_text(alert.get("description_text"))
        parsed = {
            "id": entity.get("id"),
            "timestamp": entity.get("timestamp"),
            "severity_level": alert.get("severity_level"),
            "cause": alert.get("cause"),
            "effect": alert.get("effect"),
            "header_text": header,
            "description_text": desc,
            "active_period": alert.get("active_period") or [],
            "informed_entity": alert.get("informed_entity") or [],
            "url": translated_text(alert.get("url")),
        }
        lines = sorted(alert_lines(parsed), key=LINE_ORDER.index)
        parsed["lines"] = lines
        if not lines:
            continue
        if wanted and wanted not in lines:
            continue
        if not active_periods(parsed["active_period"]):
            continue
        rows.append(parsed)
    severity_rank = {"SEVERE": 0, "WARNING": 1, "INFO": 2}
    rows.sort(key=lambda r: (severity_rank.get(str(r.get("severity_level")), 9), str(r.get("id") or "")))
    return rows


def line_status_rows() -> list[dict[str, Any]]:
    delays = delayed_rows()
    vehicles = vehicle_rows()
    alerts = alert_rows()
    rows = []
    for route in train_routes():
        short = str(route.get("route_short_name"))
        line_delays = [d for d in delays if d.get("line") == short]
        line_vehicles = [v for v in vehicles if v.get("line") == short]
        line_alerts = [a for a in alerts if short in (a.get("lines") or [])]
        cancelled = sum(1 for d in line_delays if d.get("cancelled"))
        max_delay = max([d.get("delay_seconds") or 0 for d in line_delays], default=0)
        if cancelled:
            status = "cancellations"
        elif any(a.get("severity_level") in ("SEVERE", "WARNING") for a in line_alerts):
            status = "alerts"
        elif line_delays:
            status = "delays"
        else:
            status = "normal"
        rows.append({
            "line": short,
            "route_id": route.get("route_id"),
            "line_name": route.get("line_name"),
            "route_long_name": route.get("route_long_name"),
            "route_desc": route.get("route_desc"),
            "route_color": route.get("route_color"),
            "status": status,
            "active_vehicles": len(line_vehicles),
            "delayed_trips": len(line_delays),
            "cancelled_trips": cancelled,
            "max_delay_seconds": max_delay,
            "active_alerts": len(line_alerts),
        })
    return rows


def emit(data: Any, as_json: bool, render: Any) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))


def render_lines(data: dict[str, Any]) -> str:
    lines = ["Wellington train lines (Metlink GTFS)", "LINE  STATUS         VEH  DELAYS  ALERTS  NAME"]
    for row in data["lines"]:
        lines.append(
            f"{row['line']:<4}  {row['status']:<13}  {row['active_vehicles']:>3}  "
            f"{row['delayed_trips']:>6}  {row['active_alerts']:>6}  {row['line_name']}"
        )
    return "\n".join(lines)


def render_stations(data: dict[str, Any]) -> str:
    title = "Train stations"
    if data.get("filter_line"):
        title += f" on {data['filter_line']}"
    lines = [f"{title}: {data['count']}"]
    for station in data["stations"]:
        line_text = ",".join(station.get("lines") or [station.get("line") or ""])
        lines.append(f"  {station['stop_id']:<6} {station['stop_name']:<32} zone {station.get('zone_id') or '-':<4} {line_text}")
    return "\n".join(lines)


def render_arrivals(data: dict[str, Any]) -> str:
    station = data["station"]
    lines = [f"Train arrivals for {station['stop_name']} ({data['prediction_stop_id']})"]
    if not data.get("is_train_station"):
        lines.append("  This stop is not identified as a train station; showing train-filtered results only.")
    if data.get("closed"):
        lines.append("  Station is marked closed by Metlink.")
    if not data["arrivals"]:
        lines.append("  No train arrivals currently returned.")
        return "\n".join(lines)
    for arr in data["arrivals"]:
        when = format_time(arr.get("expected") or arr.get("aimed"))
        dest = (arr.get("destination") or {}).get("name") or arr.get("trip_headsign") or "-"
        platform = arr.get("stop_id") or arr.get("platform_name") or "-"
        lines.append(f"  {when:<10} {arr['line']:<3} to {dest:<24} {arr['delay']:<12} platform {platform}")
    return "\n".join(lines)


def render_delays(data: dict[str, Any]) -> str:
    title = "Current train delays"
    if data.get("filter_line"):
        title += f" on {data['filter_line']}"
    lines = [f"{title}: {data['total_delays']}"]
    if not data["delays"]:
        lines.append("  No late or cancelled train trips currently returned.")
        return "\n".join(lines)
    for row in data["delays"]:
        when = format_timestamp(row.get("event_time")) if row.get("event_time") else row.get("start_time") or "-"
        status = "canceled" if row.get("cancelled") else row["delay"]
        lines.append(f"  {row['line']:<3} {status:<12} {row.get('stop_name'):<28} {when} trip {row.get('trip_id')}")
    return "\n".join(lines)


def render_vehicles(data: dict[str, Any]) -> str:
    title = "Live train vehicles"
    if data.get("filter_line"):
        title += f" on {data['filter_line']}"
    lines = [f"{title}: {data['total_vehicles']}"]
    if not data["vehicles"]:
        lines.append("  No live train vehicles currently returned.")
        return "\n".join(lines)
    for row in data["vehicles"]:
        pos = f"{row.get('lat')},{row.get('lon')}"
        lines.append(f"  {row['line']:<3} vehicle {str(row.get('vehicle_id') or '-'):>5}  {pos:<24} bearing {row.get('bearing') or '-'}")
    return "\n".join(lines)


def render_alerts(data: dict[str, Any]) -> str:
    title = "Active train service alerts"
    if data.get("filter_line"):
        title += f" for {data['filter_line']}"
    lines = [f"{title}: {data['total_alerts']}"]
    if not data["alerts"]:
        lines.append("  No active train service alerts currently returned.")
        return "\n".join(lines)
    for alert in data["alerts"]:
        line_text = ",".join(alert.get("lines") or [])
        severity = alert.get("severity_level") or "INFO"
        lines.append(f"  [{severity}] {line_text}: {alert.get('header_text') or alert.get('id')}")
    return "\n".join(lines)


def render_line(data: dict[str, Any]) -> str:
    route = data["route"]
    status = data["status"]
    lines = [
        f"{route['route_short_name']} - {route.get('line_name')}",
        f"Status: {status['status']} | vehicles {status['active_vehicles']} | delays {status['delayed_trips']} | alerts {status['active_alerts']}",
        f"Stations: {data['station_count']}",
    ]
    if data["delays"]:
        lines.append("Delays:")
        for row in data["delays"][:5]:
            lines.append(f"  {row['delay']:<12} {row.get('stop_name')} trip {row.get('trip_id')}")
    if data["alerts"]:
        lines.append("Alerts:")
        for alert in data["alerts"][:5]:
            lines.append(f"  [{alert.get('severity_level')}] {alert.get('header_text')}")
    return "\n".join(lines)


def cmd_lines(args: argparse.Namespace) -> None:
    data = {"timestamp": datetime.now(timezone.utc).isoformat(), "lines": line_status_rows()}
    emit(data, args.json, render_lines)


def cmd_line(args: argparse.Namespace) -> None:
    route = resolve_line(args.name)
    short = str(route["route_short_name"])
    status = next(row for row in line_status_rows() if row["line"] == short)
    stations = line_stations(short)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "route": route,
        "status": status,
        "station_count": len(stations),
        "stations": stations,
        "delays": delayed_rows(short)[:10],
        "vehicles": vehicle_rows(short)[:10],
        "alerts": alert_rows(short)[:10],
    }
    emit(data, args.json, render_line)


def cmd_stations(args: argparse.Namespace) -> None:
    route = resolve_line(args.line) if args.line else None
    short = str(route["route_short_name"]) if route else None
    stations = all_stations(short)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filter_line": short,
        "count": len(stations),
        "stations": stations,
    }
    emit(data, args.json, render_stations)


def cmd_station(args: argparse.Namespace) -> None:
    data = station_arrivals(args.station, args.limit)
    emit(data, args.json, render_arrivals)


def cmd_arrivals(args: argparse.Namespace) -> None:
    data = station_arrivals(args.station, args.limit)
    emit(data, args.json, render_arrivals)


def cmd_delays(args: argparse.Namespace) -> None:
    route = resolve_line(args.line) if args.line else None
    short = str(route["route_short_name"]) if route else None
    rows = delayed_rows(short)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filter_line": short,
        "total_delays": len(rows),
        "returned": min(len(rows), args.limit),
        "delays": rows[:args.limit],
    }
    emit(data, args.json, render_delays)


def cmd_vehicles(args: argparse.Namespace) -> None:
    route = resolve_line(args.line) if args.line else None
    short = str(route["route_short_name"]) if route else None
    rows = vehicle_rows(short)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filter_line": short,
        "total_vehicles": len(rows),
        "returned": min(len(rows), args.limit),
        "vehicles": rows[:args.limit],
    }
    emit(data, args.json, render_vehicles)


def cmd_alerts(args: argparse.Namespace) -> None:
    route = resolve_line(args.line) if args.line else None
    short = str(route["route_short_name"]) if route else None
    rows = alert_rows(short)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filter_line": short,
        "total_alerts": len(rows),
        "returned": min(len(rows), args.limit),
        "alerts": rows[:args.limit],
    }
    emit(data, args.json, render_alerts)


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Wellington Metlink train CLI (read-only GTFS/GTFS-RT).")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("lines", help="list Wellington train lines with current status")
    add_json(sp)
    sp.set_defaults(func=cmd_lines)

    sp = sub.add_parser("line", help="show detail for one train line")
    sp.add_argument("name", help="line code or name, e.g. WRL or Wairarapa")
    add_json(sp)
    sp.set_defaults(func=cmd_line)

    sp = sub.add_parser("stations", help="list train stations")
    sp.add_argument("--line", help="filter by train line code or name")
    add_json(sp)
    sp.set_defaults(func=cmd_stations)

    sp = sub.add_parser("station", help="show station detail with next train arrivals")
    sp.add_argument("station", help="stop ID or station name, e.g. WELL or Masterton")
    sp.add_argument("--limit", type=positive_int, default=12)
    add_json(sp)
    sp.set_defaults(func=cmd_station)

    sp = sub.add_parser("arrivals", help="show next train arrivals at a station")
    sp.add_argument("station", help="stop ID or station name, e.g. WELL or Wellington Station")
    sp.add_argument("--limit", type=positive_int, default=12)
    add_json(sp)
    sp.set_defaults(func=cmd_arrivals)

    sp = sub.add_parser("delays", help="show current late or cancelled train trips")
    sp.add_argument("--line", help="filter by train line code or name")
    sp.add_argument("--limit", type=positive_int, default=20)
    add_json(sp)
    sp.set_defaults(func=cmd_delays)

    sp = sub.add_parser("vehicles", help="show live train vehicle positions")
    sp.add_argument("--line", help="filter by train line code or name")
    sp.add_argument("--limit", type=positive_int, default=20)
    add_json(sp)
    sp.set_defaults(func=cmd_vehicles)

    sp = sub.add_parser("alerts", help="show active train service alerts")
    sp.add_argument("--line", help="filter by train line code or name")
    sp.add_argument("--limit", type=positive_int, default=20)
    add_json(sp)
    sp.set_defaults(func=cmd_alerts)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except CliError as e:
        die(str(e))
    except BrokenPipeError:
        return 1
    except Exception as e:
        if os.environ.get("NZ_TRAINS_DEBUG"):
            raise
        die(f"unexpected error: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
