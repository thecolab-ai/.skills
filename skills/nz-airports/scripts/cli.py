#!/usr/bin/env python3
"""NZ airports lightweight live flight-board CLI.

Self-contained stdlib wrapper around public airport arrivals/departures boards.
No login, booking, PNR lookup, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


UA = os.environ.get(
    "NZ_AIRPORTS_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)
ADSB_UA = "nz-airports-cli/1.0"
ADSB_TIMEOUT_SECONDS = 6
ADSB_MAX_AIRCRAFT = 250

AIRPORTS: dict[str, dict[str, str]] = {
    "AKL": {
        "name": "Auckland Airport",
        "city": "Auckland",
        "iata": "AKL",
        "icao": "NZAA",
        "source": "adsb.lol",
        "source_url": "https://api.adsb.lol/v2/lat/-37.008/lon/174.785/dist/30",
        "source_kind": "live_adsb",
    },
    "CHC": {
        "name": "Christchurch Airport",
        "city": "Christchurch",
        "iata": "CHC",
        "icao": "NZCH",
        "source": "christchurchairport.nz",
        "source_url": "https://www.christchurchairport.nz/travellers/flights/arrivals-and-departures/",
        "source_kind": "scheduled_fids",
    },
    "ZQN": {
        "name": "Queenstown Airport",
        "city": "Queenstown",
        "iata": "ZQN",
        "icao": "NZQN",
        "source": "queenstownairport.co.nz",
        "source_url": "https://www.queenstownairport.co.nz/",
        "source_kind": "scheduled_fids",
    },
    "WLG": {
        "name": "Wellington Airport",
        "city": "Wellington",
        "iata": "WLG",
        "icao": "NZWN",
        "source": "wellingtonairport.co.nz",
        "source_url": "https://www.wellingtonairport.co.nz/flights/",
        "source_kind": "scheduled_fids",
    },
}

ADSB_AIRPORTS: dict[str, dict[str, float]] = {
    "AKL": {"lat": -37.008, "lon": 174.785, "radius_nm": 30},
}

CHC_API = "https://www.christchurchairport.nz/api/flights"
ZQN_API = "https://www.queenstownairport.co.nz/api/flights"
WLG_FLIGHTS = "https://www.wellingtonairport.co.nz/flights/"


def die(message: str, code: int = 1) -> None:
    print(f"nz-airports: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_text(url: str, timeout: int = 25) -> str:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = raw[:300].replace("\n", " ")
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def request_json(url: str, timeout: int = 25) -> Any:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": url.rsplit("/", 1)[0] + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = raw[:300].replace("\n", " ")
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def request_adsb_aircraft(code: str) -> tuple[list[dict[str, Any]], str]:
    url = adsb_url(code)
    headers = {
        "Accept": "application/json",
        "User-Agent": ADSB_UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=ADSB_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code} from adsb.lol"
    except urllib.error.URLError as e:
        return [], f"network error calling adsb.lol: {e.reason}"
    except json.JSONDecodeError as e:
        return [], f"invalid JSON from adsb.lol: {e}"

    if not isinstance(payload, dict):
        return [], "unexpected adsb.lol payload shape"
    aircraft = payload.get("ac")
    if not isinstance(aircraft, list):
        return [], clean(payload.get("msg"))
    rows = [row for row in aircraft if isinstance(row, dict)]
    if len(rows) > ADSB_MAX_AIRCRAFT:
        return rows[:ADSB_MAX_AIRCRAFT], f"capped ADS-B aircraft at {ADSB_MAX_AIRCRAFT} of {len(rows)}"
    return rows, ""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def nz_today() -> str:
    if ZoneInfo is None:
        return datetime.now(timezone.utc).date().isoformat()
    return datetime.now(ZoneInfo("Pacific/Auckland")).date().isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def numeric(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def airport_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    code = raw.upper()
    if code not in AIRPORTS:
        die(f"unsupported airport {raw}; run `airports` for supported codes")
    return code


def flight_numbers(values: Any) -> list[str]:
    if isinstance(values, list):
        raw = values
    elif values:
        raw = [values]
    else:
        raw = []
    out: list[str] = []
    seen = set()
    for item in raw:
        value = clean(item).upper().replace(" ", "")
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def carrier_from_flight(number: str) -> str:
    match = re.match(r"^([A-Z]{2,3})", number.upper())
    return match.group(1) if match else ""


def combine_date_time(date_value: str, time_value: str) -> str:
    if not date_value or not time_value:
        return clean(time_value or date_value)
    return f"{date_value} {time_value}"


def normalize_chc(row: dict[str, Any], direction: str, flight_type: str) -> dict[str, Any]:
    numbers = flight_numbers(row.get("flightNumbers"))
    airport_names = [clean(x) for x in row.get("airports") or [] if clean(x)]
    other_side = " / ".join(airport_names)
    is_arrival = direction == "arrivals"
    return {
        "airport": "CHC",
        "airport_name": AIRPORTS["CHC"]["name"],
        "direction": direction,
        "flight_numbers": numbers,
        "primary_flight": numbers[0] if numbers else "",
        "airline_code": clean(row.get("airlineCode")),
        "airline_name": clean(row.get("airlineName")),
        "origin": other_side if is_arrival else "Christchurch",
        "destination": "Christchurch" if is_arrival else other_side,
        "scheduled": clean(row.get("scheduled")),
        "estimated": clean(row.get("estimateActual")),
        "gate": clean(row.get("gate")),
        "status": clean(row.get("status")),
        "terminal": flight_type.lower(),
        "is_domestic": flight_type == "Domestic",
        "source": AIRPORTS["CHC"]["source"],
        "source_url": AIRPORTS["CHC"]["source_url"],
    }


def normalize_zqn(row: dict[str, Any], direction: str) -> dict[str, Any]:
    numbers = flight_numbers(row.get("flightList"))
    scheduled = combine_date_time(clean(row.get("schDate")), clean(row.get("schTime")))
    estimated = combine_date_time(clean(row.get("estDate")), clean(row.get("estTime")))
    return {
        "airport": "ZQN",
        "airport_name": AIRPORTS["ZQN"]["name"],
        "direction": direction,
        "flight_numbers": numbers,
        "primary_flight": numbers[0] if numbers else "",
        "airline_code": carrier_from_flight(numbers[0]) if numbers else "",
        "airline_name": "",
        "origin": clean(row.get("from")),
        "destination": clean(row.get("destination")),
        "scheduled": scheduled,
        "estimated": estimated,
        "scheduled_date": clean(row.get("schDate")),
        "estimated_date": clean(row.get("estDate")),
        "gate": "",
        "status": clean(row.get("status")),
        "terminal": "domestic" if row.get("isDomestic") else "international",
        "is_domestic": bool(row.get("isDomestic")),
        "order_by": clean(row.get("orderByDate")),
        "source": AIRPORTS["ZQN"]["source"],
        "source_url": AIRPORTS["ZQN"]["source_url"],
    }


def normalize_wlg(row: dict[str, Any], direction: str, day: str) -> dict[str, Any]:
    number = clean(row.get("flight_number")).upper().replace(" ", "")
    numbers = flight_numbers(number)
    is_arrival = direction == "arrivals"
    place = clean(row.get("place"))
    scheduled_time = clean(row.get("scheduled"))
    estimated_time = clean(row.get("estimated"))
    return {
        "airport": "WLG",
        "airport_name": AIRPORTS["WLG"]["name"],
        "direction": direction,
        "flight_numbers": numbers,
        "primary_flight": numbers[0] if numbers else "",
        "airline_code": clean(row.get("carrier_code")),
        "airline_name": clean(row.get("carrier_name")),
        "origin": place if is_arrival else "Wellington",
        "destination": "Wellington" if is_arrival else place,
        "scheduled": combine_date_time(day, scheduled_time),
        "estimated": combine_date_time(day, estimated_time),
        "scheduled_time": scheduled_time,
        "estimated_time": estimated_time,
        "gate": clean(row.get("gate")),
        "status": clean(row.get("status_text")),
        "terminal": clean(row.get("zone")),
        "is_domestic": clean(row.get("zone")).upper() != "I",
        "source": AIRPORTS["WLG"]["source"],
        "source_url": AIRPORTS["WLG"]["source_url"],
    }


def classify_adsb_aircraft(aircraft: dict[str, Any]) -> str:
    if aircraft.get("alt_baro") == "ground":
        return "ground"
    alt = numeric(aircraft.get("alt_baro"))
    rate = numeric(aircraft.get("baro_rate")) or 0
    if alt is None:
        return "overhead"
    if alt < 6000:
        if rate < -200:
            return "arrival"
        if rate > 200:
            return "departure"
        return "arrival"
    return "overhead"


def normalize_adsb(row: dict[str, Any], direction: str) -> dict[str, Any]:
    hex_value = clean(row.get("hex")).upper()
    callsign = clean(row.get("flight")).upper().replace(" ", "") or hex_value
    alt_baro = row.get("alt_baro")
    altitude_ft = 0 if alt_baro == "ground" else numeric(alt_baro)
    classification = classify_adsb_aircraft(row)
    return {
        "airport": "AKL",
        "airport_name": AIRPORTS["AKL"]["name"],
        "direction": direction,
        "data_type": "live_adsb",
        "flight_numbers": [callsign] if callsign else [],
        "primary_flight": callsign,
        "callsign": callsign,
        "hex": hex_value,
        "registration": clean(row.get("r")),
        "aircraft_type": clean(row.get("t")),
        "classification": classification,
        "altitude_ft": altitude_ft,
        "altitude_baro": alt_baro,
        "distance_nm": numeric(row.get("dst")),
        "ground_speed_kt": numeric(row.get("gs")),
        "vertical_rate_fpm": numeric(row.get("baro_rate")),
        "lat": numeric(row.get("lat")),
        "lon": numeric(row.get("lon")),
        "airline_code": carrier_from_flight(callsign),
        "airline_name": "",
        "origin": "",
        "destination": "",
        "scheduled": "",
        "estimated": "",
        "gate": "",
        "status": classification,
        "terminal": "",
        "is_domestic": None,
        "source": AIRPORTS["AKL"]["source"],
        "source_url": AIRPORTS["AKL"]["source_url"],
        "raw_adsb": row,
    }


def fetch_chc(direction: str) -> dict[str, Any]:
    api_direction = "Arrive" if direction == "arrivals" else "Depart"
    flights: list[dict[str, Any]] = []
    updated: list[str] = []
    for flight_type in ("Domestic", "International"):
        params = {
            "maxFlights": "",
            "flightDirection": api_direction,
            "flightType": flight_type,
        }
        url = CHC_API + "?" + urllib.parse.urlencode(params)
        payload = request_json(url)
        if not isinstance(payload, dict):
            die(f"unexpected Christchurch payload from {url}")
        if payload.get("lastUpdated"):
            updated.append(clean(payload.get("lastUpdated")))
        for row in payload.get("flights") or []:
            if isinstance(row, dict):
                flights.append(normalize_chc(row, direction, flight_type))
    return board_result("CHC", direction, flights, ", ".join(sorted(set(updated))))


def fetch_zqn(direction: str) -> dict[str, Any]:
    endpoint = "arrivals" if direction == "arrivals" else "departures"
    payload = request_json(f"{ZQN_API}/{endpoint}")
    if not isinstance(payload, list):
        die(f"unexpected Queenstown payload from {ZQN_API}/{endpoint}")
    today = nz_today()
    todays_rows = [
        row for row in payload
        if isinstance(row, dict) and (row.get("schDate") == today or row.get("estDate") == today)
    ]
    rows = todays_rows if todays_rows else [row for row in payload if isinstance(row, dict)]
    flights = [normalize_zqn(row, direction) for row in rows]
    return board_result("ZQN", direction, flights, "")


def fetch_wlg(direction: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"direction": "A" if direction == "arrivals" else "D"})
    url = f"{WLG_FLIGHTS}?{query}"
    text = request_text(url)
    match = re.search(
        r'<script[^>]*type=["\']application/json["\'][^>]*data-flights[^>]*>\s*(\{.*?\})\s*</script>',
        text,
        re.S,
    )
    if not match:
        die(f"could not find Wellington embedded flight JSON at {url}")
    try:
        payload = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        die(f"invalid Wellington embedded flight JSON at {url}: {e}")
    rows = payload.get("flights") or []
    day = clean(payload.get("day"))
    flights = [normalize_wlg(row, direction, day) for row in rows if isinstance(row, dict)]
    return board_result("WLG", direction, flights, clean(payload.get("last_updated")))


def adsb_url(code: str) -> str:
    meta = ADSB_AIRPORTS[code]
    return f"https://api.adsb.lol/v2/lat/{meta['lat']}/lon/{meta['lon']}/dist/{meta['radius_nm']}"


def fetch_adsb_akl(direction: str) -> dict[str, Any]:
    aircraft, source_note = request_adsb_aircraft("AKL")
    counts = {"arrival": 0, "departure": 0, "ground": 0, "overhead": 0}
    normalized: list[dict[str, Any]] = []
    for row in aircraft:
        classification = classify_adsb_aircraft(row)
        counts[classification] += 1
        if classification == direction.rstrip("s"):
            normalized.append(normalize_adsb(row, direction))
    normalized.sort(
        key=lambda flight: (
            flight.get("distance_nm") is None,
            flight.get("distance_nm") if flight.get("distance_nm") is not None else 999,
        )
    )
    result = board_result("AKL", direction, normalized, "")
    result.update(
        {
            "data_type": "live_adsb",
            "adsb_endpoint": adsb_url("AKL"),
            "adsb_radius_nm": ADSB_AIRPORTS["AKL"]["radius_nm"],
            "adsb_total_aircraft": len(aircraft),
            "classification_counts": counts,
        }
    )
    if source_note:
        result["source_note"] = source_note
    return result


def board_result(airport: str, direction: str, flights: list[dict[str, Any]], source_last_updated: str) -> dict[str, Any]:
    meta = AIRPORTS[airport]
    return {
        "airport": airport,
        "airport_name": meta["name"],
        "direction": direction,
        "source": meta["source"],
        "source_url": meta["source_url"],
        "data_type": meta["source_kind"],
        "source_last_updated": source_last_updated,
        "fetched_at": now_iso(),
        "total_flights": len(flights),
        "flights": flights,
    }


FETCHERS = {
    "AKL": fetch_adsb_akl,
    "CHC": fetch_chc,
    "ZQN": fetch_zqn,
    "WLG": fetch_wlg,
}


def fetch_board(code: str, direction: str) -> dict[str, Any]:
    return FETCHERS[code](direction)


def limited_board(result: dict[str, Any], limit: int) -> dict[str, Any]:
    flights = result["flights"][:limit]
    out = dict(result)
    out["returned"] = len(flights)
    out["flights"] = flights
    return out


def selected_airports(raw: str | None) -> list[str]:
    code = airport_code(raw)
    return [code] if code else list(AIRPORTS)


def cmd_board(args: argparse.Namespace, direction: str) -> None:
    results = [limited_board(fetch_board(code, direction), args.limit) for code in selected_airports(args.airport)]
    if args.airport:
        emit_board(results[0], args.json)
    else:
        data = {
            "direction": direction,
            "fetched_at": now_iso(),
            "airports": results,
        }
        emit_boards(data, args.json)


def cmd_arrivals(args: argparse.Namespace) -> None:
    cmd_board(args, "arrivals")


def cmd_departures(args: argparse.Namespace) -> None:
    cmd_board(args, "departures")


def cmd_flight(args: argparse.Namespace) -> None:
    needle = args.flight_number.upper().replace(" ", "")
    matches: list[dict[str, Any]] = []
    for code in selected_airports(args.airport):
        for direction in ("arrivals", "departures"):
            result = fetch_board(code, direction)
            for flight in result["flights"]:
                if needle in flight.get("flight_numbers", []):
                    matches.append(flight)
    data = {
        "query": needle,
        "airport": airport_code(args.airport),
        "fetched_at": now_iso(),
        "total_matches": len(matches),
        "flights": matches,
    }
    emit_flight_matches(data, args.json)


def cmd_airports(args: argparse.Namespace) -> None:
    data = {
        "count": len(AIRPORTS),
        "airports": [
            {
                "code": code,
                "name": meta["name"],
                "city": meta["city"],
                "iata": meta["iata"],
                "icao": meta["icao"],
                "source": meta["source"],
                "source_url": meta["source_url"],
                "source_kind": meta["source_kind"],
            }
            for code, meta in AIRPORTS.items()
        ],
        "not_wired": [],
    }
    emit_airports(data, args.json)


def route_label(flight: dict[str, Any]) -> str:
    if flight.get("direction") == "arrivals":
        return f"from {flight.get('origin') or '-'}"
    return f"to {flight.get('destination') or '-'}"


def time_label(flight: dict[str, Any]) -> str:
    scheduled = flight.get("scheduled") or "-"
    estimated = flight.get("estimated")
    if estimated and estimated != scheduled:
        return f"{scheduled} (est {estimated})"
    return str(scheduled)


def flight_line(flight: dict[str, Any]) -> str:
    if flight.get("data_type") == "live_adsb":
        return adsb_flight_line(flight)
    nums = "/".join(flight.get("flight_numbers") or [flight.get("primary_flight") or "-"])
    airline = flight.get("airline_name") or flight.get("airline_code") or ""
    gate = f" gate {flight['gate']}" if flight.get("gate") else ""
    terminal = f" {flight['terminal']}" if flight.get("terminal") else ""
    status = f" - {flight['status']}" if flight.get("status") else ""
    return f"  {time_label(flight):<28} {nums:<18} {route_label(flight)}{gate}{terminal} {airline}{status}".rstrip()


def adsb_altitude_label(flight: dict[str, Any]) -> str:
    if flight.get("altitude_baro") == "ground":
        return "ground"
    altitude = numeric(flight.get("altitude_ft"))
    return f"{altitude:.0f} ft" if altitude is not None else "-"


def adsb_number_label(value: Any, suffix: str, decimals: int = 0) -> str:
    number = numeric(value)
    if number is None:
        return "-"
    return f"{number:.{decimals}f} {suffix}"


def adsb_flight_line(flight: dict[str, Any]) -> str:
    callsign = flight.get("callsign") or flight.get("hex") or "-"
    aircraft = flight.get("aircraft_type") or "-"
    registration = flight.get("registration") or "-"
    altitude = adsb_altitude_label(flight)
    distance = adsb_number_label(flight.get("distance_nm"), "nm", 1)
    speed = adsb_number_label(flight.get("ground_speed_kt"), "kt")
    vertical = adsb_number_label(flight.get("vertical_rate_fpm"), "fpm")
    return (
        f"  {callsign:<10} {aircraft:<8} {registration:<9} "
        f"alt {altitude:<8} dist {distance:<8} gs {speed:<7} vr {vertical}"
    ).rstrip()


def print_board(result: dict[str, Any]) -> None:
    if result.get("data_type") == "live_adsb":
        print_adsb_board(result)
        return
    updated = f", updated {result['source_last_updated']}" if result.get("source_last_updated") else ""
    print(f"{result['airport']} {result['direction']}: {result.get('returned', len(result['flights']))} of {result['total_flights']} flights ({result['source']}{updated})")
    if not result["flights"]:
        print("  No flights currently listed.")
        return
    for flight in result["flights"]:
        print(flight_line(flight))


def print_adsb_board(result: dict[str, Any]) -> None:
    returned = result.get("returned", len(result["flights"]))
    total = result["total_flights"]
    nearby = result.get("adsb_total_aircraft", 0)
    radius = result.get("adsb_radius_nm")
    print(
        f"{result['airport']} {result['direction']}: {returned} of {total} classified live aircraft "
        f"({result['source']}, {nearby} nearby within {radius:g} nm)"
    )
    if result.get("source_note"):
        print(f"  Source note: {result['source_note']}")
    if not result["flights"]:
        print(f"  No live ADS-B aircraft currently classified as {result['direction']} near this airport.")
        return
    for flight in result["flights"]:
        print(flight_line(flight))


def emit_board(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_board(data)


def emit_boards(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for index, result in enumerate(data["airports"]):
            if index:
                print()
            print_board(result)


def emit_flight_matches(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print(f"{data['query']}: {data['total_matches']} matches")
    if not data["flights"]:
        print("  No matching flights currently listed.")
        return
    for flight in data["flights"]:
        print(f"  {flight['airport']} {flight['direction']}: {flight_line(flight).strip()}")


def emit_airports(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print(f"Supported airports: {data['count']}")
    for airport in data["airports"]:
        kind = "live ADS-B aircraft positions" if airport["source_kind"] == "live_adsb" else "scheduled FIDS board"
        print(f"  {airport['code']}  {airport['name']} ({airport['source']}; {kind})")
    if data["not_wired"]:
        print()
        print("Not wired:")
        for airport in data["not_wired"]:
            print(f"  {airport['code']}  {airport['name']} - {airport['reason']}")


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected integer, received {raw}")
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def add_board_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--airport", choices=sorted(AIRPORTS), help="airport code; defaults to all supported airports")
    parser.add_argument("--limit", type=positive_int, default=20, help="max flights to show per airport (default 20)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight read-only NZ airport arrivals/departures CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("arrivals", help="show current arrivals board")
    add_board_args(sp)
    sp.set_defaults(func=cmd_arrivals)

    sp = sub.add_parser("departures", help="show current departures board")
    add_board_args(sp)
    sp.set_defaults(func=cmd_departures)

    sp = sub.add_parser("flight", help="lookup a flight number across current boards")
    sp.add_argument("flight_number", help="flight number, e.g. NZ5640")
    sp.add_argument("--airport", choices=sorted(AIRPORTS), help="airport code; defaults to all supported airports")
    sp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sp.set_defaults(func=cmd_flight)

    sp = sub.add_parser("airports", help="list supported airports")
    sp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sp.set_defaults(func=cmd_airports)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
