#!/usr/bin/env python3
"""NZ tides and surf lightweight read-only CLI.

Self-contained stdlib wrapper around public LINZ tide prediction tables and
SwellMap surf forecast payloads. No login, browser automation, API key, or
write action is required.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


LINZ_SITE = "https://www.linz.govt.nz"
LINZ_PORTS_API = LINZ_SITE + "/api/v1/tp"
LINZ_CSV_BASE = "https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv"
SWELLMAP_SITE = "https://www.swellmap.com"
SWELLMAP_SURF_BASE = SWELLMAP_SITE + "/surf-forecasts/new-zealand"
METOCEAN_DOCS = "https://developer.metservice.com/docs/api-catalog/point-forecast-api/"
NIWA_SITE = "https://niwa.co.nz"

UA = os.environ.get(
    "NZ_TIDES_SURF_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

NZ_TZ = ZoneInfo("Pacific/Auckland") if ZoneInfo else timezone(timedelta(hours=12))


def key(value: str) -> str:
    text = value.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TIDE_ALIASES: dict[str, str] = {
    "piha": "Anawhata",
    "karekare": "Anawhata",
    "muriwai": "Anawhata",
    "muriwai beach": "Anawhata",
    "bethells": "Anawhata",
    "bethells beach": "Anawhata",
    "te henga": "Anawhata",
    "raglan surf": "Raglan",
    "mt maunganui": "Moturiki Island",
    "mount maunganui": "Moturiki Island",
    "the mount": "Moturiki Island",
    "tay street": "Moturiki Island",
    "main beach mount": "Moturiki Island",
    "lyall bay": "Wellington",
    "breaker bay": "Wellington",
}


BREAKS: dict[str, dict[str, Any]] = {
    "piha": {"name": "Piha", "slug": "piha", "region": "auckland", "tide_port": "Anawhata"},
    "muriwai": {"name": "Muriwai Beach", "slug": "muriwai-beach", "region": "auckland", "tide_port": "Anawhata"},
    "bethells": {"name": "Bethells Beach", "slug": "bethells-beach", "region": "auckland", "tide_port": "Anawhata"},
    "karekare": {"name": "Karekare", "slug": "karekare", "region": "auckland", "tide_port": "Anawhata"},
    "karioitahi": {"name": "Karioitahi", "slug": "karioitahi", "region": "auckland", "tide_port": "Anawhata"},
    "port waikato": {"name": "Port Waikato", "slug": "port-waikato", "region": "auckland", "tide_port": "Port Waikato"},
    "raglan": {"name": "Raglan / Manu Bay", "slug": "manu-bay", "region": "raglan", "tide_port": "Raglan"},
    "manu bay": {"name": "Manu Bay", "slug": "manu-bay", "region": "raglan", "tide_port": "Raglan"},
    "raglan bar": {"name": "Raglan Bar", "slug": "raglan-bar", "region": "raglan", "tide_port": "Raglan"},
    "mussel rock": {"name": "Mussel Rock", "slug": "mussel-rock", "region": "raglan", "tide_port": "Raglan"},
    "whangamata": {"name": "Whangamata", "slug": "whangamata", "region": "coromandel", "tide_port": "Whangamata"},
    "hot water beach": {"name": "Hot Water Beach", "slug": "hot-water-beach", "region": "coromandel", "tide_port": "Whitianga"},
    "kuaotunu": {"name": "Kuaotunu", "slug": "kuaotunu", "region": "coromandel", "tide_port": "Whitianga"},
    "whitianga": {"name": "Whitianga", "slug": "whitianga", "region": "coromandel", "tide_port": "Whitianga"},
    "mt maunganui": {"name": "Mt Maunganui / Tay Street", "slug": "tay-street", "region": "bop", "tide_port": "Moturiki Island"},
    "mount maunganui": {"name": "Mt Maunganui / Tay Street", "slug": "tay-street", "region": "bop", "tide_port": "Moturiki Island"},
    "tay street": {"name": "Tay Street", "slug": "tay-street", "region": "bop", "tide_port": "Moturiki Island"},
    "maketu": {"name": "Maketu", "slug": "maketu", "region": "bop", "tide_port": "Maketu"},
    "lyall bay": {"name": "Lyall Bay", "slug": "lyall-bay", "region": "wgtn", "tide_port": "Wellington"},
    "breaker bay": {"name": "Breaker Bay", "slug": "breaker-bay", "region": "wgtn", "tide_port": "Wellington"},
    "makara": {"name": "Makara", "slug": "makara", "region": "wgtn", "tide_port": "Wellington"},
    "plimmerton": {"name": "Plimmerton", "slug": "plimmerton", "region": "wgtn", "tide_port": "Wellington"},
    "wainui beach": {"name": "Wainui Beach", "slug": "wainui-beach", "region": "gisborne", "tide_port": "Gisborne"},
    "makorori": {"name": "Makorori", "slug": "makorori", "region": "gisborne", "tide_port": "Gisborne"},
    "hicks bay": {"name": "Hicks Bay", "slug": "hicks-bay", "region": "gisborne", "tide_port": "Wharekahika / Hicks Bay"},
    "te arai": {"name": "Te Arai Point", "slug": "te-arai-point", "region": "northland", "tide_port": "Leigh"},
    "mangawhai": {"name": "Mangawhai Heads", "slug": "mangawhai-heads", "region": "northland", "tide_port": "Leigh"},
    "st clair": {"name": "St Clair", "slug": "st-clair", "region": "otago", "tide_port": "Dunedin"},
}

REGION_BREAKS: dict[str, list[str]] = {
    "auckland": ["piha", "muriwai", "bethells", "karekare", "karioitahi"],
    "coromandel": ["whangamata", "hot water beach", "kuaotunu", "whitianga"],
    "gisborne": ["wainui beach", "makorori", "hicks bay"],
    "wgtn": ["lyall bay", "breaker bay", "makara", "plimmerton"],
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-tides-surf: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_text(url: str, *, accept: str = "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.7", timeout: int = 25) -> tuple[str, str]:
    headers = {"Accept": accept, "User-Agent": UA}
    if url.startswith(LINZ_SITE):
        headers["Referer"] = LINZ_SITE + "/products-services/tides-and-tidal-streams/tide-predictions"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace"), resp.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        detail = re.sub(r"\s+", " ", raw[:300]).strip()
        die(f"HTTP {e.code} from {url}: {detail or e.reason}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def request_json(url: str, timeout: int = 25) -> Any:
    text, _ = request_text(url, accept="application/json, text/plain, */*", timeout=timeout)
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def emit(data: dict[str, Any], as_json: bool, printer: Any) -> None:
    if as_json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        printer(data)


def nz_now() -> datetime:
    return datetime.now(NZ_TZ).replace(microsecond=0)


def nz_today() -> date:
    return nz_now().date()


def parse_date(value: str | None, label: str = "date") -> date:
    if not value:
        return nz_today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        die(f"{label} must be an ISO date like 2026-05-24")


def float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round_or_none(value: Any, places: int = 2) -> float | None:
    number = float_or_none(value)
    return round(number, places) if number is not None else None


def cardinal(degrees: Any) -> str | None:
    deg = float_or_none(degrees)
    if deg is None:
        return None
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((deg % 360 + 22.5) // 45) % 8]


def parse_linz_location(raw: str | None) -> tuple[float | None, float | None]:
    if not raw or "," not in raw:
        return None, None
    left, right = raw.split(",", 1)
    return float_or_none(left.strip()), float_or_none(right.strip())


def fetch_linz_ports() -> list[dict[str, Any]]:
    payload = request_json(LINZ_PORTS_API)
    if not isinstance(payload, list):
        die("unexpected LINZ tide port index response")
    ports = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        lat, lon = parse_linz_location(row.get("field_location"))
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        prediction_file = str(row.get("field_tide_prediction_file") or "").strip()
        ports.append(
            {
                "name": name,
                "key": key(name),
                "lat": lat,
                "lon": lon,
                "tide_type": row.get("field_tide_type") or "",
                "reference_port": row.get("field_tide_reference_port") or "",
                "prediction_file": prediction_file,
                "has_prediction_csv": bool(prediction_file),
            }
        )
    return ports


def resolve_linz_port(identifier: str, ports: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], str | None]:
    ports = ports or fetch_linz_ports()
    original = identifier.strip()
    needle = key(original)
    alias = TIDE_ALIASES.get(needle)
    target = key(alias) if alias else needle
    for port in ports:
        if port["key"] == target:
            return port, alias if alias else None
    for port in ports:
        if target and target in port["key"]:
            return port, alias if alias else None
    names = {port["key"]: port for port in ports}
    close = difflib.get_close_matches(target, list(names), n=1, cutoff=0.72)
    if close:
        return names[close[0]], alias if alias else None
    sample = ", ".join(port["name"] for port in ports[:8])
    die(f"unknown LINZ tide port {original!r}; run `ports` for supported ports. Examples: {sample}")


def linz_csv_url(prediction_file: str, year: int) -> str:
    filename = f"{prediction_file} {year}.csv"
    return LINZ_CSV_BASE + "/" + urllib.parse.quote(filename, safe="")


def parse_linz_csv(text: str, port_name: str, source_url: str) -> list[dict[str, Any]]:
    rows = csv.reader(text.replace("\ufeff", "").splitlines())
    events: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            day = int(row[0].strip())
            month = int(row[2].strip())
            year = int(row[3].strip())
        except ValueError:
            continue
        for idx in range(4, min(len(row), 12), 2):
            if idx + 1 >= len(row):
                continue
            tm = row[idx].strip()
            height = float_or_none(row[idx + 1].strip())
            if height is None or not re.match(r"^\d{1,2}:\d{2}$", tm):
                continue
            hour, minute = [int(part) for part in tm.split(":", 1)]
            local = datetime(year, month, day, hour, minute, tzinfo=NZ_TZ)
            events.append(
                {
                    "time": local.isoformat(),
                    "date": local.date().isoformat(),
                    "time_local": local.strftime("%H:%M"),
                    "height_m": round(height, 3),
                    "type": "",
                    "port": port_name,
                    "source": "LINZ tide predictions",
                    "source_url": source_url,
                }
            )
    events.sort(key=lambda item: item["time"])
    for idx, event in enumerate(events):
        height = event["height_m"]
        prev_height = events[idx - 1]["height_m"] if idx > 0 else None
        next_height = events[idx + 1]["height_m"] if idx + 1 < len(events) else None
        if prev_height is None and next_height is not None:
            event["type"] = "high" if height > next_height else "low"
        elif next_height is None and prev_height is not None:
            event["type"] = "high" if height > prev_height else "low"
        elif prev_height is not None and next_height is not None:
            event["type"] = "high" if height >= prev_height and height >= next_height else "low"
        else:
            event["type"] = "unknown"
    return events


def fetch_linz_tides(port: dict[str, Any], start: date, days: int) -> tuple[list[dict[str, Any]], list[str]]:
    prediction_file = port.get("prediction_file") or port["name"]
    if not prediction_file:
        die(f"{port['name']} has no direct LINZ annual tide prediction CSV; use its reference port {port.get('reference_port') or 'from the ports list'}")
    end = start + timedelta(days=days)
    years = sorted({start.year, (end - timedelta(days=1)).year})
    events: list[dict[str, Any]] = []
    urls: list[str] = []
    for year in years:
        url = linz_csv_url(str(prediction_file), year)
        text, final_url = request_text(url, accept="text/csv,*/*")
        urls.append(final_url)
        events.extend(parse_linz_csv(text, port["name"], final_url))
    return [event for event in events if start <= date.fromisoformat(event["date"]) < end], urls


def tides_payload(port_arg: str, start: date, days: int) -> dict[str, Any]:
    days = max(1, min(days, 31))
    port, alias = resolve_linz_port(port_arg)
    started = time.perf_counter()
    events, urls = fetch_linz_tides(port, start, days)
    if not events:
        die(f"no LINZ tide events found for {port['name']} from {start.isoformat()} for {days} day(s)")
    return {
        "query": port_arg,
        "resolved_port": port["name"],
        "alias_target": alias,
        "date_start": start.isoformat(),
        "days": days,
        "timezone": "Pacific/Auckland",
        "source": "LINZ tide predictions",
        "source_urls": urls,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "events": events,
    }


def cmd_ports(args: argparse.Namespace) -> None:
    ports = fetch_linz_ports()
    data = {
        "source": "LINZ tide predictions port index",
        "source_url": LINZ_PORTS_API,
        "count": len(ports),
        "ports": [
            {k: port[k] for k in ("name", "lat", "lon", "tide_type", "reference_port", "prediction_file", "has_prediction_csv")}
            for port in ports
        ],
        "aliases": TIDE_ALIASES,
    }
    emit(data, args.json, print_ports)


def print_ports(data: dict[str, Any]) -> None:
    print(f"LINZ tide ports: {data['count']}")
    print("Direct annual CSV where prediction_file is present; common surf aliases are resolved by the CLI.")
    print()
    for port in data["ports"][:120]:
        marker = "csv" if port["has_prediction_csv"] else "offset"
        ref = f" via {port['reference_port']}" if port.get("reference_port") else ""
        print(f"{port['name']} ({marker}{ref})")
    if data["count"] > 120:
        print(f"... {data['count'] - 120} more; use --json for the full list")


def cmd_tides(args: argparse.Namespace) -> None:
    start = parse_date(args.date)
    data = tides_payload(args.port, start, args.days)
    emit(data, args.json, print_tides)


def print_tides(data: dict[str, Any]) -> None:
    alias = f" for {data['query']}" if data.get("alias_target") else ""
    print(f"LINZ tides: {data['resolved_port']}{alias}, {data['date_start']} +{data['days']} day(s)")
    print(f"Timezone: {data['timezone']}")
    current_date = None
    for event in data["events"]:
        if event["date"] != current_date:
            current_date = event["date"]
            print()
            print(current_date)
        print(f"  {event['time_local']}  {event['type']:>4}  {event['height_m']:.2f} m")


def cmd_next_tide(args: argparse.Namespace) -> None:
    now = nz_now()
    data = tides_payload(args.port, now.date(), 3)
    upcoming = [event for event in data["events"] if datetime.fromisoformat(event["time"]) >= now]
    next_high = next((event for event in upcoming if event["type"] == "high"), None)
    next_low = next((event for event in upcoming if event["type"] == "low"), None)
    if not next_high and not next_low:
        die(f"no upcoming LINZ tide events found for {data['resolved_port']}")
    data.update({"now": now.isoformat(), "next_high": next_high, "next_low": next_low, "events": upcoming[:8]})
    emit(data, args.json, print_next_tide)


def print_next_tide(data: dict[str, Any]) -> None:
    print(f"Next LINZ tides: {data['resolved_port']} (now {data['now']})")
    for label in ("next_high", "next_low"):
        event = data.get(label)
        if event:
            when = datetime.fromisoformat(event["time"]).strftime("%a %d %b %H:%M")
            print(f"{label.replace('_', ' ').title()}: {when}, {event['height_m']:.2f} m")


def resolve_break(identifier: str) -> dict[str, Any]:
    needle = key(identifier)
    if needle in BREAKS:
        return BREAKS[needle]
    by_slug = {key(value["slug"]): value for value in BREAKS.values()}
    if needle in by_slug:
        return by_slug[needle]
    names = {key(value["name"]): value for value in BREAKS.values()}
    for lookup in (by_slug, names):
        close = difflib.get_close_matches(needle, list(lookup), n=1, cutoff=0.7)
        if close:
            return lookup[close[0]]
    sample = ", ".join(sorted({value["name"] for value in BREAKS.values()})[:10])
    die(f"unknown surf break {identifier!r}; run `breaks` for supported breaks. Examples: {sample}")


def swellmap_json_from_html(text: str, url: str) -> dict[str, Any]:
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', text, flags=re.S)
    if not match:
        die(f"could not find SwellMap Next.js data payload at {url}")
    raw = html.unescape(match.group(1))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid SwellMap Next.js JSON at {url}: {e}")
    if not isinstance(payload, dict):
        die(f"unexpected SwellMap payload shape at {url}")
    return payload


def fetch_swellmap_payload(slug: str) -> tuple[dict[str, Any], str]:
    url = f"{SWELLMAP_SURF_BASE}/{urllib.parse.quote(slug, safe='-')}"
    text, final_url = request_text(url)
    return swellmap_json_from_html(text, final_url), final_url


def nested(data: Any, *path: str) -> Any:
    cur = data
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def parse_swellmap_time(value: Any) -> datetime | None:
    text = str(value or "")
    try:
        return datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=NZ_TZ)
    except ValueError:
        return None


def value_at(series: Any, idx: int) -> Any:
    if isinstance(series, list) and idx < len(series):
        return series[idx]
    return None


def normalize_surf_forecast(info: dict[str, Any], days: int, source_url: str) -> dict[str, Any]:
    page_props = info.get("pageProps") or nested(info, "props", "pageProps") or {}
    state = nested(page_props, "initialState") or {}
    location = nested(state, "navigation", "location") or {}
    region = nested(state, "navigation", "region") or {}
    forecast_state = nested(state, "forecast") or {}
    forecast = forecast_state.get("forecastData") or {}
    if not isinstance(forecast, dict) or not forecast.get("time"):
        die("SwellMap did not return forecastData for this break")
    today = nz_today()
    end = today + timedelta(days=max(1, min(days, 7)))
    rows = []
    for idx, raw_time in enumerate(forecast.get("time") or []):
        local = parse_swellmap_time(raw_time)
        if not local or not (today <= local.date() < end):
            continue
        sea_temp = value_at(forecast.get("sea_temp"), idx)
        sea_temp_value = (sea_temp or {}).get("value") if isinstance(sea_temp, dict) else None
        wetsuit = (sea_temp or {}).get("recomendation") if isinstance(sea_temp, dict) else None
        wind_kmh = round_or_none(value_at(forecast.get("wind_sp"), idx), 1)
        gust_kmh = round_or_none(value_at(forecast.get("wind_gust"), idx), 1)
        rows.append(
            {
                "time": local.isoformat(),
                "date": local.date().isoformat(),
                "time_local": local.strftime("%H:%M"),
                "rating": round_or_none(value_at(forecast.get("rating"), idx), 2),
                "wave_m": round_or_none(value_at(forecast.get("wave"), idx), 2),
                "swell_m": round_or_none(value_at(forecast.get("swell"), idx), 2),
                "surf_face_m": round_or_none(value_at(forecast.get("set_face"), idx), 2),
                "swell_period_s": round_or_none(value_at(forecast.get("period"), idx), 1),
                "swell_direction_deg": round_or_none(value_at(forecast.get("swell_dir"), idx), 0),
                "swell_direction": cardinal(value_at(forecast.get("swell_dir"), idx)),
                "wind_speed_kmh": wind_kmh,
                "wind_speed_knots": round(wind_kmh / 1.852, 1) if wind_kmh is not None else None,
                "wind_gust_kmh": gust_kmh,
                "wind_gust_knots": round(gust_kmh / 1.852, 1) if gust_kmh is not None else None,
                "wind_direction_deg": round_or_none(value_at(forecast.get("wind_dir"), idx), 0),
                "wind_direction": cardinal(value_at(forecast.get("wind_dir"), idx)),
                "summary": value_at(forecast.get("summary_description"), idx),
                "summary_icon": value_at(forecast.get("summary_icon"), idx),
                "sea_temp_c": round_or_none(sea_temp_value, 1),
                "wetsuit_recommendation": wetsuit,
            }
        )
    tide_rows = []
    for tide in forecast.get("tide") or []:
        if not isinstance(tide, dict):
            continue
        local = parse_swellmap_time(tide.get("time"))
        if not local or not (today <= local.date() < end):
            continue
        tide_rows.append(
            {
                "time": local.isoformat(),
                "date": local.date().isoformat(),
                "time_local": local.strftime("%H:%M"),
                "type": str(tide.get("level") or "").lower(),
                "height_m": round_or_none(tide.get("depth"), 3),
            }
        )
    sun_rows = []
    sunrise_series = forecast.get("sunrise") or []
    sunset_series = forecast.get("sunset") or []
    for offset_days in range(max(1, min(days, 7))):
        day = today + timedelta(days=offset_days)
        sr = value_at(sunrise_series, offset_days)
        ss = value_at(sunset_series, offset_days)
        if sr or ss:
            sun_rows.append({"date": day.isoformat(), "sunrise": sr, "sunset": ss})
    return {
        "spot": location.get("name") or forecast.get("title") or "",
        "slug": location.get("id") or forecast.get("title") or "",
        "region": region.get("name") or "",
        "lat": location.get("lat") or forecast.get("lat"),
        "lon": location.get("lon") or forecast.get("lon"),
        "days": days,
        "timezone": forecast.get("timezone") or "Pacific/Auckland",
        "source": "SwellMap surf forecast",
        "source_url": source_url,
        "last_updated": forecast_state.get("lastUpdated"),
        "forecast": rows,
        "tides": tide_rows,
        "sun": sun_rows,
    }


def surf_payload(break_arg: str, days: int) -> dict[str, Any]:
    spot = resolve_break(break_arg)
    started = time.perf_counter()
    raw, source_url = fetch_swellmap_payload(spot["slug"])
    data = normalize_surf_forecast(raw, days, source_url)
    data.update(
        {
            "query": break_arg,
            "known_break_name": spot["name"],
            "known_region": spot["region"],
            "linz_tide_port": spot["tide_port"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
    )
    return data


def cmd_breaks(args: argparse.Namespace) -> None:
    seen: set[str] = set()
    breaks = []
    for value in BREAKS.values():
        slug = value["slug"]
        if slug in seen:
            continue
        seen.add(slug)
        breaks.append(
            {
                "name": value["name"],
                "slug": slug,
                "region": value["region"],
                "linz_tide_port": value["tide_port"],
                "source_url": f"{SWELLMAP_SURF_BASE}/{slug}",
            }
        )
    breaks.sort(key=lambda row: (row["region"], row["name"]))
    data = {"source": "SwellMap known NZ surf break list curated for this CLI", "count": len(breaks), "breaks": breaks}
    emit(data, args.json, print_breaks)


def print_breaks(data: dict[str, Any]) -> None:
    print(f"Known surf breaks: {data['count']}")
    current = None
    for row in data["breaks"]:
        if row["region"] != current:
            current = row["region"]
            print()
            print(current)
        print(f"  {row['name']} ({row['slug']}) - LINZ tide: {row['linz_tide_port']}")


def cmd_surf(args: argparse.Namespace) -> None:
    data = surf_payload(args.break_name, args.days)
    emit(data, args.json, print_surf)


def print_surf(data: dict[str, Any]) -> None:
    print(f"SwellMap surf: {data['spot']} ({data['region']})")
    print(f"Last updated: {data.get('last_updated') or 'unknown'}")
    print(f"LINZ tide companion: {data['linz_tide_port']}")
    first = next((r for r in data["forecast"] if r.get("sea_temp_c") is not None), None)
    if first:
        bits = [f"Sea temp {first['sea_temp_c']:.1f}°C"]
        if first.get("wetsuit_recommendation"):
            bits.append(first["wetsuit_recommendation"])
        print(" | ".join(bits))
    sun_by_date = {row["date"]: row for row in data.get("sun") or []}
    current_date = None
    for row in data["forecast"]:
        if row["date"] != current_date:
            current_date = row["date"]
            sun = sun_by_date.get(current_date)
            print()
            if sun and (sun.get("sunrise") or sun.get("sunset")):
                print(f"{current_date}  sunrise {sun.get('sunrise') or '-'}  sunset {sun.get('sunset') or '-'}")
            else:
                print(current_date)
        rating = "-" if row["rating"] is None else f"{row['rating']:.1f}/10"
        wave = "-" if row["wave_m"] is None else f"{row['wave_m']:.1f} m"
        face = f" face {row['surf_face_m']:.1f} m" if row.get("surf_face_m") is not None else ""
        period = "-" if row["swell_period_s"] is None else f"{row['swell_period_s']:.0f} s"
        direction = row["swell_direction"] or "-"
        wind_dir = row["wind_direction"] or "-"
        wind_kt = row.get("wind_speed_knots")
        gust_kt = row.get("wind_gust_knots")
        if wind_kt is not None and gust_kt is not None:
            wind = f"{wind_dir} {wind_kt:.0f}kt (g {gust_kt:.0f})"
        elif wind_kt is not None:
            wind = f"{wind_dir} {wind_kt:.0f}kt"
        else:
            wind = wind_dir
        summary = row["summary"] or ""
        print(f"  {row['time_local']}  rating {rating}  wave {wave}{face}  period {period}  swell {direction}  wind {wind}  {summary}")


def score_rows(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any] | None:
    morning = [
        row
        for row in rows
        if date.fromisoformat(row["date"]) == target_date and 5 <= int(row["time_local"].split(":", 1)[0]) <= 11 and row.get("rating") is not None
    ]
    if not morning:
        morning = [row for row in rows if date.fromisoformat(row["date"]) == target_date and row.get("rating") is not None]
    if not morning:
        return None
    ratings = [float(row["rating"]) for row in morning if row.get("rating") is not None]
    waves = [float(row["wave_m"]) for row in morning if row.get("wave_m") is not None]
    periods = [float(row["swell_period_s"]) for row in morning if row.get("swell_period_s") is not None]
    return {
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "avg_wave_m": round(sum(waves) / len(waves), 2) if waves else None,
        "avg_period_s": round(sum(periods) / len(periods), 1) if periods else None,
        "sample_count": len(morning),
        "samples": morning,
    }


def cmd_best_break(args: argparse.Namespace) -> None:
    region = args.region.lower()
    names = REGION_BREAKS.get(region)
    if not names:
        die(f"unsupported region {args.region!r}; choose one of: {', '.join(sorted(REGION_BREAKS))}")
    target_date = parse_date(args.date) if args.date else nz_today() + timedelta(days=1)
    contenders = []
    errors = []
    for name in names:
        try:
            forecast = surf_payload(name, 3)
            score = score_rows(forecast["forecast"], target_date)
            if score:
                contenders.append(
                    {
                        "name": forecast["spot"],
                        "slug": forecast["slug"],
                        "region": forecast["known_region"],
                        "linz_tide_port": forecast["linz_tide_port"],
                        "source_url": forecast["source_url"],
                        **score,
                    }
                )
        except SystemExit as e:
            errors.append({"break": name, "error": str(e)})
    contenders.sort(key=lambda row: (row.get("avg_rating") or -1, row.get("avg_period_s") or -1, row.get("avg_wave_m") or -1), reverse=True)
    data = {
        "region": region,
        "date": target_date.isoformat(),
        "window": "morning 05:00-11:59 NZ time, falling back to all-day samples if needed",
        "source": "SwellMap surf forecast",
        "timezone": "Pacific/Auckland",
        "best": contenders[0] if contenders else None,
        "contenders": contenders,
        "errors": errors,
    }
    emit(data, args.json, print_best_break)


def print_best_break(data: dict[str, Any]) -> None:
    print(f"Best break: {data['region']} on {data['date']} ({data['window']})")
    best = data.get("best")
    if not best:
        print("No comparable forecast rows found.")
        return
    print(f"Pick: {best['name']} - avg rating {best['avg_rating']}/10, wave {best.get('avg_wave_m')} m, period {best.get('avg_period_s')} s")
    print()
    for row in data["contenders"]:
        print(f"{row['name']}: rating {row['avg_rating']}/10, wave {row.get('avg_wave_m')} m, period {row.get('avg_period_s')} s")


def cmd_marine(args: argparse.Namespace) -> None:
    data = {
        "area": args.area,
        "status": "not_wired",
        "source": "NIWA marine forecast",
        "source_url": NIWA_SITE,
        "message": (
            "A no-key NIWA public marine wave forecast endpoint was not confirmed during implementation. "
            "Use `surf` or `best-break` for no-login SwellMap surf forecasts, or the existing `metservice-nz` "
            "skill's `marine` command for MetOcean wave variables when METOCEAN_API_KEY is available."
        ),
        "metservice_nz_skill": "skills/metservice-nz/scripts/cli.py marine <location>",
        "metocean_docs": METOCEAN_DOCS,
    }
    emit(data, args.json, print_marine)


def print_marine(data: dict[str, Any]) -> None:
    print(f"NIWA marine forecast for {data['area']}: not wired")
    print(data["message"])
    print(f"MetOcean docs: {data['metocean_docs']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only NZ LINZ tide tables and SwellMap surf forecasts")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ports", help="list available LINZ tide ports")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_ports)

    p = sub.add_parser("tides", help="LINZ tide predictions for a port")
    p.add_argument("port", help="LINZ port or surf alias, e.g. Auckland, Piha, Raglan")
    p.add_argument("--date", help="start date in YYYY-MM-DD, default today in Pacific/Auckland")
    p.add_argument("--days", type=int, default=1, help="number of days, max 31")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_tides)

    p = sub.add_parser("next-tide", help="next high and next low LINZ tide from now")
    p.add_argument("port", help="LINZ port or surf alias")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_next_tide)

    p = sub.add_parser("breaks", help="list known NZ surf breaks")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_breaks)

    p = sub.add_parser("surf", help="SwellMap surf forecast for a named break")
    p.add_argument("break_name", help="known break, e.g. Piha, Raglan, Lyall Bay")
    p.add_argument("--days", type=int, default=3, help="number of forecast days to show, max 7")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_surf)

    p = sub.add_parser("best-break", help="compare breaks in a region and rank the best morning drive")
    p.add_argument("--region", default="auckland", choices=sorted(REGION_BREAKS), help="region to compare")
    p.add_argument("--date", help="target date in YYYY-MM-DD, default tomorrow in Pacific/Auckland")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_best_break)

    p = sub.add_parser("marine", help="NIWA marine forecast placeholder and MetService handoff")
    p.add_argument("area", help="coastal area name")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=cmd_marine)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
