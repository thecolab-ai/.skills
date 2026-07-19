#!/usr/bin/env python3
"""MetService NZ weather CLI.

Read-only stdlib wrapper around the MetOcean point-time API and MetService
public warnings page.

BUG FIX vs the TS version: METOCEAN_API_KEY is NOT required at module import
time. It is only checked inside functions that call the MetOcean API, so
commands like `warnings` and `locations` work without the key set.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

API_BASE = "https://forecast-v2.metoceanapi.com/point/time"
WARNINGS_URL = "https://www.metservice.com/warnings/home"
UA = "metservice-nz-skill/1.0 (+https://github.com/thecolab-ai/.skills)"
DEFAULT_TIMEOUT = 15

LOCATIONS: dict[str, dict] = {
    "clevedon":     {"name": "Clevedon",       "lat": -36.9697, "lon": 175.0752},
    "auckland":     {"name": "Auckland CBD",    "lat": -36.8485, "lon": 174.7633},
    "wellington":   {"name": "Wellington",      "lat": -41.2865, "lon": 174.7762},
    "christchurch": {"name": "Christchurch",    "lat": -43.5321, "lon": 172.6362},
    "queenstown":   {"name": "Queenstown",      "lat": -45.0312, "lon": 168.6626},
}

WEATHER_VARS = [
    "air.temperature.at-2m",
    "air.humidity.at-2m",
    "air.pressure.at-sea-level",
    "air.visibility",
    "cloud.cover",
    "precipitation.rate",
    "wind.speed.at-10m",
    "wind.direction.at-10m",
    "wind.speed.gust.at-10m",
    "radiation.flux.downward.shortwave",
]

WIND_VARS = [
    "wind.speed.at-10m",
    "wind.direction.at-10m",
    "wind.speed.gust.at-10m",
]

RAIN_VARS = [
    "precipitation.rate",
    "cloud.cover",
]

MARINE_VARS = [
    "wave.height",
    "wave.height.primary-swell",
    "wave.height.wind-sea",
    "wave.period.peak",
    "wave.period.primary-swell.peak",
    "wave.direction.peak",
    "wave.direction.primary-swell.mean",
    "sea.temperature.at-surface",
]

CYCLONE_VARS = [
    "air.pressure.at-sea-level",
    "wind.speed.at-10m",
    "wind.speed.gust.at-10m",
    "wind.direction.at-10m",
    "wave.height",
    "wave.height.primary-swell",
    "wave.period.peak",
    "precipitation.rate",
]

try:
    from zoneinfo import ZoneInfo
    NZ_TZ: dt.tzinfo = ZoneInfo("Pacific/Auckland")
except Exception:
    NZ_TZ = dt.timezone(dt.timedelta(hours=12), name="Pacific/Auckland")


def die(message: str, code: int = 1) -> None:
    print(f"metservice-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def require_api_key() -> str:
    key = os.environ.get("METOCEAN_API_KEY", "")
    if not key:
        die(
            "METOCEAN_API_KEY env var not set. "
            "Sign up at https://forecast-v2.metoceanapi.com and set the key in your environment."
        )
    return key


def query_point_time(request: dict) -> dict:
    """POST to MetOcean point-time API. Requires METOCEAN_API_KEY."""
    api_key = require_api_key()
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": UA,
    }
    body = json.dumps(request).encode("utf-8")
    try:
        return nzfetch.fetch_json(
            API_BASE,
            timeout=DEFAULT_TIMEOUT,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            data=body,
            method="POST",
            allowed_hosts={"forecast-v2.metoceanapi.com"},
        )
    except nzfetch.Blocked as e:
        die(f"network error calling MetOcean API: {e}")
    except nzfetch.FetchError as e:
        die(f"MetOcean API error: {e}")


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "MetService-NZ-Skill/1.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        die(f"MetService warnings page: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        die(f"network error fetching warnings: {e.reason}")


# --- Helpers ---

def now_iso_hour() -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_location(name_or_coords: str | None = None, coords_flag: str | None = None) -> dict:
    if coords_flag:
        try:
            lat, lon = [float(x.strip()) for x in coords_flag.split(",")]
        except Exception:
            die(f"Invalid coordinates: {coords_flag}. Expected format: lat,lon")
        return {"name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}
    if name_or_coords:
        key = name_or_coords.lower().strip()
        if key in LOCATIONS:
            return LOCATIONS[key]
        if "," in key:
            try:
                lat, lon = [float(x.strip()) for x in key.split(",")]
                return {"name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}
            except Exception:
                pass
        available = ", ".join(LOCATIONS)
        die(f"Unknown location: {name_or_coords}. Available: {available}")
    available = ", ".join(LOCATIONS)
    die(f"Please specify a location: {available} — or use --location lat,lon")


def deg_to_compass(deg: float | None) -> str:
    if deg is None:
        return "?"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


def num(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "-"
    return f"{v:.{decimals}f}"


def format_nz_time(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(NZ_TZ)
        return d.strftime("%-I:%M %p")
    except Exception:
        return iso


def format_nz_datetime(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(NZ_TZ)
        return d.strftime("%a %-d %b, %-I:%M %p")
    except Exception:
        return iso


def pad_right(s: str, length: int) -> str:
    return s.ljust(length)


def get_arr(variables: dict, key: str) -> list:
    return (variables.get(key) or {}).get("data") or []


# --- MetOcean API fetchers ---

def fetch_current_conditions(location: dict) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": WEATHER_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": 1},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [from_t])

    def get(key: str) -> float | None:
        arr = get_arr(v, key)
        return arr[0] if arr else None

    temp_k = get("air.temperature.at-2m")
    pressure_pa = get("air.pressure.at-sea-level")
    vis_m = get("air.visibility")
    wind_ms = get("wind.speed.at-10m")
    gust_ms = get("wind.speed.gust.at-10m")
    rain = get("precipitation.rate")

    return {
        "location": location,
        "time": times[0] if times else from_t,
        "tempC": temp_k - 273.15 if temp_k is not None else None,
        "humidity": get("air.humidity.at-2m"),
        "pressureHpa": pressure_pa / 100 if pressure_pa is not None else None,
        "visibilityKm": vis_m / 1000 if vis_m is not None else None,
        "cloudCoverPct": get("cloud.cover"),
        "rainMmH": max(0, rain) if rain is not None else None,
        "windSpeedKmh": wind_ms * 3.6 if wind_ms is not None else None,
        "windDirDeg": get("wind.direction.at-10m"),
        "gustSpeedKmh": gust_ms * 3.6 if gust_ms is not None else None,
        "solarWm2": get("radiation.flux.downward.shortwave"),
    }


def fetch_hourly_forecast(location: dict, hours: int = 24) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": WEATHER_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    temp_arr = get_arr(v, "air.temperature.at-2m")
    rain_arr = get_arr(v, "precipitation.rate")
    wind_arr = get_arr(v, "wind.speed.at-10m")
    dir_arr = get_arr(v, "wind.direction.at-10m")
    gust_arr = get_arr(v, "wind.speed.gust.at-10m")
    cloud_arr = get_arr(v, "cloud.cover")
    hum_arr = get_arr(v, "air.humidity.at-2m")

    hour_list = []
    for i, t in enumerate(times):
        tk = temp_arr[i] if i < len(temp_arr) else None
        rain = rain_arr[i] if i < len(rain_arr) else None
        wind = wind_arr[i] if i < len(wind_arr) else None
        gust = gust_arr[i] if i < len(gust_arr) else None
        hour_list.append({
            "time": t,
            "tempC": tk - 273.15 if tk is not None else None,
            "rainMmH": max(0, rain) if rain is not None else None,
            "windSpeedKmh": wind * 3.6 if wind is not None else None,
            "windDirDeg": dir_arr[i] if i < len(dir_arr) else None,
            "gustSpeedKmh": gust * 3.6 if gust is not None else None,
            "cloudCoverPct": cloud_arr[i] if i < len(cloud_arr) else None,
            "humidity": hum_arr[i] if i < len(hum_arr) else None,
        })

    return {"location": location, "hours": hour_list}


def fetch_daily_forecast(location: dict, days: int = 7) -> dict:
    hours = days * 24
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": ["air.temperature.at-2m", "precipitation.rate", "wind.speed.at-10m",
                      "wind.direction.at-10m", "wind.speed.gust.at-10m", "cloud.cover"],
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    temp_arr = get_arr(v, "air.temperature.at-2m")
    rain_arr = get_arr(v, "precipitation.rate")
    wind_arr = get_arr(v, "wind.speed.at-10m")
    dir_arr = get_arr(v, "wind.direction.at-10m")
    gust_arr = get_arr(v, "wind.speed.gust.at-10m")
    cloud_arr = get_arr(v, "cloud.cover")

    day_map: dict[str, list[int]] = {}
    for i, t in enumerate(times):
        try:
            d = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(NZ_TZ)
            key = d.strftime("%d/%m/%Y")
        except Exception:
            key = t[:10]
        day_map.setdefault(key, []).append(i)

    day_list = []
    for date_key, indices in day_map.items():
        temps = [temp_arr[i] for i in indices if i < len(temp_arr) and temp_arr[i] is not None]
        rains = [rain_arr[i] for i in indices if i < len(rain_arr) and rain_arr[i] is not None]
        winds = [wind_arr[i] for i in indices if i < len(wind_arr) and wind_arr[i] is not None]
        gusts = [gust_arr[i] for i in indices if i < len(gust_arr) and gust_arr[i] is not None]
        dirs = [dir_arr[i] for i in indices if i < len(dir_arr) and dir_arr[i] is not None]
        clouds = [cloud_arr[i] for i in indices if i < len(cloud_arr) and cloud_arr[i] is not None]
        day_list.append({
            "date": date_key,
            "highC": max(temps) - 273.15 if temps else None,
            "lowC": min(temps) - 273.15 if temps else None,
            "totalRainMm": sum(max(0, r) for r in rains),
            "avgWindKmh": (sum(winds) / len(winds)) * 3.6 if winds else None,
            "maxGustKmh": max(gusts) * 3.6 if gusts else None,
            "dominantWindDir": dirs[len(dirs) // 2] if dirs else None,
            "avgCloudPct": sum(clouds) / len(clouds) if clouds else None,
        })

    return {"location": location, "days": day_list}


def fetch_marine_forecast(location: dict, hours: int = 24) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": MARINE_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    wave_h = get_arr(v, "wave.height")
    swell_h = get_arr(v, "wave.height.primary-swell")
    wind_sea_h = get_arr(v, "wave.height.wind-sea")
    wave_p = get_arr(v, "wave.period.peak")
    swell_p = get_arr(v, "wave.period.primary-swell.peak")
    wave_d = get_arr(v, "wave.direction.peak")
    swell_d = get_arr(v, "wave.direction.primary-swell.mean")
    sea_t = get_arr(v, "sea.temperature.at-surface")

    hour_list = []
    for i, t in enumerate(times):
        st = sea_t[i] if i < len(sea_t) else None
        hour_list.append({
            "time": t,
            "waveHeightM": wave_h[i] if i < len(wave_h) else None,
            "swellHeightM": swell_h[i] if i < len(swell_h) else None,
            "windSeaHeightM": wind_sea_h[i] if i < len(wind_sea_h) else None,
            "wavePeriodS": wave_p[i] if i < len(wave_p) else None,
            "swellPeriodS": swell_p[i] if i < len(swell_p) else None,
            "waveDirectionDeg": wave_d[i] if i < len(wave_d) else None,
            "swellDirectionDeg": swell_d[i] if i < len(swell_d) else None,
            "seaTempC": st - 273.15 if st is not None else None,
        })

    return {"location": location, "hours": hour_list}


def fetch_wind_forecast(location: dict, hours: int = 24) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": WIND_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    wind_arr = get_arr(v, "wind.speed.at-10m")
    gust_arr = get_arr(v, "wind.speed.gust.at-10m")
    dir_arr = get_arr(v, "wind.direction.at-10m")

    hour_list = []
    for i, t in enumerate(times):
        wind = wind_arr[i] if i < len(wind_arr) else None
        gust = gust_arr[i] if i < len(gust_arr) else None
        hour_list.append({
            "time": t,
            "speedKmh": wind * 3.6 if wind is not None else None,
            "gustKmh": gust * 3.6 if gust is not None else None,
            "directionDeg": dir_arr[i] if i < len(dir_arr) else None,
        })

    return {"location": location, "hours": hour_list}


def fetch_rain_forecast(location: dict, hours: int = 24) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": RAIN_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    rain_arr = get_arr(v, "precipitation.rate")
    cloud_arr = get_arr(v, "cloud.cover")

    hour_list = []
    for i, t in enumerate(times):
        rain = rain_arr[i] if i < len(rain_arr) else None
        hour_list.append({
            "time": t,
            "rainMmH": max(0, rain) if rain is not None else None,
            "cloudCoverPct": cloud_arr[i] if i < len(cloud_arr) else None,
        })

    return {"location": location, "hours": hour_list}


def fetch_cyclone_data(location: dict, hours: int = 48) -> dict:
    from_t = now_iso_hour()
    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": CYCLONE_VARS,
        "time": {"from": from_t, "interval": "1h", "repeat": hours},
    })
    v = data.get("variables", {})
    times = data.get("dimensions", {}).get("time", {}).get("data", [])

    press_arr = get_arr(v, "air.pressure.at-sea-level")
    wind_arr = get_arr(v, "wind.speed.at-10m")
    gust_arr = get_arr(v, "wind.speed.gust.at-10m")
    dir_arr = get_arr(v, "wind.direction.at-10m")
    wave_arr = get_arr(v, "wave.height")
    swell_arr = get_arr(v, "wave.height.primary-swell")
    period_arr = get_arr(v, "wave.period.peak")
    rain_arr = get_arr(v, "precipitation.rate")

    hour_list = []
    for i, t in enumerate(times):
        press = press_arr[i] if i < len(press_arr) else None
        wind = wind_arr[i] if i < len(wind_arr) else None
        gust = gust_arr[i] if i < len(gust_arr) else None
        rain = rain_arr[i] if i < len(rain_arr) else None
        hour_list.append({
            "time": t,
            "pressureHpa": press / 100 if press is not None else None,
            "windSpeedKmh": wind * 3.6 if wind is not None else None,
            "gustSpeedKmh": gust * 3.6 if gust is not None else None,
            "windDirDeg": dir_arr[i] if i < len(dir_arr) else None,
            "waveHeightM": wave_arr[i] if i < len(wave_arr) else None,
            "swellHeightM": swell_arr[i] if i < len(swell_arr) else None,
            "wavePeriodS": period_arr[i] if i < len(period_arr) else None,
            "rainMmH": max(0, rain) if rain is not None else None,
        })

    current = hour_list[0] if hour_list else {}
    return {
        "location": location,
        "time": current.get("time") or (times[0] if times else from_t),
        "pressureHpa": current.get("pressureHpa"),
        "windSpeedKmh": current.get("windSpeedKmh"),
        "gustSpeedKmh": current.get("gustSpeedKmh"),
        "windDirDeg": current.get("windDirDeg"),
        "waveHeightM": current.get("waveHeightM"),
        "swellHeightM": current.get("swellHeightM"),
        "wavePeriodS": current.get("wavePeriodS"),
        "rainMmH": current.get("rainMmH"),
        "hours": hour_list,
    }


def fetch_pressure_trend(location: dict) -> dict:
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    past_start = now - dt.timedelta(hours=12)
    from_t = past_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = query_point_time({
        "points": [{"lon": location["lon"], "lat": location["lat"]}],
        "variables": ["air.pressure.at-sea-level"],
        "time": {"from": from_t, "interval": "1h", "repeat": 24},
    })
    times = data.get("dimensions", {}).get("time", {}).get("data", [])
    press_arr = get_arr(data.get("variables", {}), "air.pressure.at-sea-level")

    readings = []
    for i, t in enumerate(times):
        press = press_arr[i] if i < len(press_arr) else None
        readings.append({"time": t, "pressureHpa": press / 100 if press is not None else None})

    current_idx = min(12, len(readings) - 1)
    current_hpa = readings[current_idx]["pressureHpa"] if readings else None

    change_per_hour = None
    change_3h = None
    change_6h = None

    def safe_diff(a_idx: int, b_idx: int) -> float | None:
        if a_idx >= len(readings) or b_idx >= len(readings):
            return None
        a = readings[a_idx]["pressureHpa"]
        b = readings[b_idx]["pressureHpa"]
        if a is None or b is None:
            return None
        return a - b

    if current_idx >= 1:
        change_per_hour = safe_diff(current_idx, current_idx - 1)
    if current_idx >= 3:
        change_3h = safe_diff(current_idx, current_idx - 3)
    if current_idx >= 6:
        change_6h = safe_diff(current_idx, current_idx - 6)

    direction = "unknown"
    severity = ""
    if change_3h is not None:
        rate = change_3h / 3
        if rate <= -3:
            direction = "falling-rapidly"
            severity = "DANGER: Rapid pressure drop (>3 hPa/hr) — severe storm/cyclone intensification"
        elif rate <= -1:
            direction = "falling"
            severity = "Pressure falling — storm approaching"
        elif rate < 1:
            direction = "steady"
            severity = "Pressure stable"
        elif rate < 3:
            direction = "rising"
            severity = "Pressure rising — conditions improving"
        else:
            direction = "rising-rapidly"
            severity = "Rapid pressure rise — strong wind shift possible"

    if current_hpa is not None and current_hpa < 990:
        extra = f"WARNING: Pressure {current_hpa:.0f} hPa is in tropical cyclone territory (<990 hPa)"
        severity = (severity + ". " if severity else "") + extra

    return {
        "location": location,
        "currentHpa": current_hpa,
        "readings": readings,
        "trend": {
            "changePerHour": change_per_hour,
            "change3h": change_3h,
            "change6h": change_6h,
            "direction": direction,
            "severity": severity,
        },
    }


def scrape_warnings() -> dict:
    """Scrape MetService public warnings page. Does NOT require METOCEAN_API_KEY."""
    fetched_at = now_utc_iso()
    html = fetch_html(WARNINGS_URL)

    # Strip scripts and styles then get text
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    warnings: list[dict] = []

    # Look for structured warning blocks (Red/Orange/Yellow Warning/Watch/Advisory)
    warning_block_re = re.compile(
        r"(Red|Orange|Yellow)\s+(Warning|Watch|Advisory)[:\s]+([^.]{5,})", re.IGNORECASE
    )
    for m in warning_block_re.finditer(text):
        warnings.append({
            "type": m.group(2),
            "level": m.group(1),
            "areas": "",
            "description": m.group(3).strip()[:300],
            "timing": "",
        })

    # Fallback: pick up general severe weather mentions
    if not warnings:
        severe_re = re.compile(
            r"(?:severe weather|tropical cyclone|heavy rain|strong wind|storm)[^.]{5,}",
            re.IGNORECASE,
        )
        for m in severe_re.finditer(text):
            warnings.append({
                "type": "Alert",
                "level": "Info",
                "areas": "",
                "description": m.group(0).strip()[:300],
                "timing": "",
            })

    # Extract outlook
    outlook_m = re.search(r"outlook[:\s]+([^.]{5,}(?:\.[^.]{5,}){0,2})", text, re.IGNORECASE)
    outlook = outlook_m.group(1).strip() if outlook_m else ""

    # Collect relevant sentences for raw
    keywords = ["warning", "watch", "advisory", "alert", "severe", "cyclone", "tropical"]
    sentences = re.split(r"[.!]\s+", text)
    relevant = [s for s in sentences if any(kw in s.lower() for kw in keywords)]
    raw = ". ".join(relevant[:20])[:1000]

    return {
        "source": WARNINGS_URL,
        "fetchedAt": fetched_at,
        "warnings": warnings,
        "outlook": outlook,
        "raw": raw,
    }


# --- Commands ---

def emit(data: Any, as_json: bool, render_fn) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_fn())


def get_location(args: argparse.Namespace, positional: str | None = None) -> dict:
    return resolve_location(positional, getattr(args, "location", None))


def cmd_now(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    c = fetch_current_conditions(loc)

    def render() -> str:
        lines = [f"{loc['name']} — Current Conditions"]
        lines.append(f"   {format_nz_datetime(c['time'])} NZST")
        lines.append(f"Temp: {num(c['tempC'])}C")
        lines.append(f"Humidity: {num(c['humidity'], 0)}%")
        lines.append(f"Wind: {num(c['windSpeedKmh'], 0)} km/h {deg_to_compass(c['windDirDeg'])}  Gusts: {num(c['gustSpeedKmh'], 0)} km/h")
        lines.append(f"Rain: {num(c['rainMmH'])} mm/h")
        lines.append(f"Cloud: {num(c['cloudCoverPct'], 0)}%")
        lines.append(f"Pressure: {num(c['pressureHpa'], 0)} hPa")
        if c.get("visibilityKm") is not None:
            lines.append(f"Visibility: {num(c['visibilityKm'])} km")
        if c.get("solarWm2") is not None:
            lines.append(f"Solar: {num(c['solarWm2'], 0)} W/m2")
        return "\n".join(lines)

    emit(c, args.json, render)


def cmd_forecast(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_hourly_forecast(loc)

    def render() -> str:
        lines = [f"{loc['name']} — 24h Forecast", ""]
        lines.append(f"{'Time':<10} {'Temp':<7} {'Rain':<9} {'Wind':<12} {'Gust':<9} {'Cloud':<6} Dir")
        lines.append("-" * 62)
        for h in data["hours"]:
            t = pad_right(format_nz_time(h["time"]), 10)
            temp = pad_right(f"{num(h['tempC'])}C", 7)
            rain = pad_right(f"{num(h['rainMmH'])}mm/h", 9)
            wind = pad_right(f"{num(h['windSpeedKmh'], 0)}km/h", 12)
            gust = pad_right(f"{num(h['gustSpeedKmh'], 0)}km/h", 9)
            cloud = pad_right(f"{num(h['cloudCoverPct'], 0)}%", 6)
            d = deg_to_compass(h["windDirDeg"])
            lines.append(f"{t} {temp} {rain} {wind} {gust} {cloud} {d}")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_daily(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_daily_forecast(loc)

    def render() -> str:
        lines = [f"{loc['name']} — 7-Day Forecast", ""]
        lines.append(f"{'Day':<14} {'High':<7} {'Low':<7} {'Rain':<8} {'Wind':<10} {'Gust':<9} {'Cloud':<6} Dir")
        lines.append("-" * 72)
        for d in data["days"]:
            day = pad_right(d["date"], 14)
            high = pad_right(f"{num(d['highC'])}C", 7)
            low = pad_right(f"{num(d['lowC'])}C", 7)
            rain = pad_right(f"{num(d['totalRainMm'])}mm", 8)
            wind = pad_right(f"{num(d['avgWindKmh'], 0)}km/h", 10)
            gust = pad_right(f"{num(d['maxGustKmh'], 0)}km/h" if d["maxGustKmh"] is not None else "-", 9)
            cloud = pad_right(f"{num(d['avgCloudPct'], 0)}%", 6)
            direction = deg_to_compass(d["dominantWindDir"])
            lines.append(f"{day} {high} {low} {rain} {wind} {gust} {cloud} {direction}")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_marine(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_marine_forecast(loc)
    has_data = any(h.get("waveHeightM") is not None for h in data["hours"])
    if not has_data:
        print(f"{loc['name']} — No marine data available (location may be too far inland).")
        print("Try a coastal location or use --location with offshore coordinates.")
        return

    def render() -> str:
        lines = [f"{loc['name']} — Marine Forecast", ""]
        lines.append(f"{'Time':<10} {'Wave':<7} {'Swell':<7} {'Period':<8} {'Dir':<5} {'WindSea':<8} SeaTemp")
        lines.append("-" * 58)
        for h in data["hours"]:
            t = pad_right(format_nz_time(h["time"]), 10)
            wave = pad_right(f"{num(h['waveHeightM'])}m" if h["waveHeightM"] is not None else "-", 7)
            swell = pad_right(f"{num(h['swellHeightM'])}m" if h["swellHeightM"] is not None else "-", 7)
            period_val = h["swellPeriodS"] or h["wavePeriodS"]
            period = pad_right(f"{num(period_val)}s" if period_val is not None else "-", 8)
            d = pad_right(deg_to_compass(h.get("swellDirectionDeg") or h.get("waveDirectionDeg")), 5)
            wind_sea = pad_right(f"{num(h['windSeaHeightM'])}m" if h["windSeaHeightM"] is not None else "-", 8)
            sea_t = f"{num(h['seaTempC'])}C" if h["seaTempC"] is not None else "-"
            lines.append(f"{t} {wave} {swell} {period} {d} {wind_sea} {sea_t}")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_wind(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_wind_forecast(loc)

    def render() -> str:
        lines = [f"{loc['name']} — Wind Forecast", ""]
        lines.append(f"{'Time':<10} {'Speed':<10} {'Gust':<10} {'Dir':<5} Compass")
        lines.append("-" * 45)
        for h in data["hours"]:
            t = pad_right(format_nz_time(h["time"]), 10)
            speed = pad_right(f"{num(h['speedKmh'], 0)} km/h", 10)
            gust = pad_right(f"{num(h['gustKmh'], 0)} km/h", 10)
            dir_deg = pad_right(f"{h['directionDeg']:.0f}D" if h["directionDeg"] is not None else "-", 5)
            compass = deg_to_compass(h["directionDeg"])
            lines.append(f"{t} {speed} {gust} {dir_deg} {compass}")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_rain(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_rain_forecast(loc)

    def render() -> str:
        lines = [f"{loc['name']} — Rain Forecast", ""]
        lines.append(f"{'Time':<10} {'Rain':<10} {'Cloud':<6} Bar")
        lines.append("-" * 45)
        for h in data["hours"]:
            t = pad_right(format_nz_time(h["time"]), 10)
            rain = pad_right(f"{num(h['rainMmH'])} mm/h", 10)
            cloud = pad_right(f"{num(h['cloudCoverPct'], 0)}%", 6)
            bar_len = round((h["rainMmH"] or 0) * 10)
            bar = "#" * min(bar_len, 30) if bar_len > 0 else ""
            lines.append(f"{t} {rain} {cloud} {bar}")
        total = sum(h["rainMmH"] or 0 for h in data["hours"])
        lines.append("")
        lines.append(f"Total rainfall estimate: {num(total)} mm over {len(data['hours'])}h")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_warnings(args: argparse.Namespace) -> None:
    """Fetch MetService warnings — does NOT require METOCEAN_API_KEY."""
    data = scrape_warnings()

    def render() -> str:
        lines = ["MetService Warnings"]
        lines.append(f"   Fetched: {format_nz_datetime(data['fetchedAt'])} NZST")
        lines.append(f"   Source: {data['source']}")
        lines.append("")
        if not data["warnings"]:
            lines.append("   No active warnings found.")
        else:
            for w in data["warnings"]:
                level = f"[{w['level'].upper()}]" if w.get("level") else ""
                lines.append(f"   {level} {w['type']}: {w['description']}")
                if w.get("areas"):
                    lines.append(f"      Areas: {w['areas']}")
                if w.get("timing"):
                    lines.append(f"      Timing: {w['timing']}")
        if data.get("outlook"):
            lines.append("")
            lines.append(f"   Outlook: {data['outlook']}")
        if data.get("raw"):
            lines.append("")
            lines.append("   Raw relevant content:")
            lines.append(f"   {data['raw'][:500]}")
        lines.append("")
        lines.append("   Also check:")
        lines.append("   * https://www.metservice.com/warnings/severe-weather-outlook")
        lines.append("   * https://www.metservice.com/marine-surf/tropical-cyclones")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_cyclone(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    hours = int(getattr(args, "hours", 48) or 48)
    data = fetch_cyclone_data(loc, hours)

    def render() -> str:
        lines = [f"{loc['name']} — Cyclone Tracker"]
        lines.append(f"   {format_nz_datetime(data['time'])} NZST")
        lines.append("")
        lines.append("  CURRENT CONDITIONS:")

        p = data.get("pressureHpa")
        p_label = "[!]" if p is not None and p < 990 else "[W]" if p is not None and p < 1000 else "   "
        cyclone_note = " -- CYCLONE TERRITORY" if p is not None and p < 990 else ""
        lines.append(f"  {p_label} Pressure: {num(p, 1)} hPa{cyclone_note}")

        g = data.get("gustSpeedKmh")
        w_label = "[!]" if g is not None and g > 118 else "[W]" if g is not None and g > 63 else "   "
        lines.append(f"  {w_label} Wind: {num(data.get('windSpeedKmh'), 0)} km/h sustained, {num(g, 0)} km/h gusts {deg_to_compass(data.get('windDirDeg'))}")
        if g is not None and g > 118:
            lines.append("       ^^^ SEVERE TROPICAL CYCLONE WIND SPEEDS")
        elif g is not None and g > 63:
            lines.append("       ^^^ TROPICAL CYCLONE WIND SPEEDS")

        lines.append(f"     Wave: {num(data.get('waveHeightM'))} m  Swell: {num(data.get('swellHeightM'))} m  Period: {num(data.get('wavePeriodS'), 0)} s")
        lines.append(f"     Rain: {num(data.get('rainMmH'))} mm/h")
        lines.append("")

        press_readings = [h for h in data["hours"][:6] if h.get("pressureHpa") is not None]
        if len(press_readings) >= 2:
            first = press_readings[0]["pressureHpa"]
            last = press_readings[-1]["pressureHpa"]
            change = last - first
            rate = change / (len(press_readings) - 1)
            sign = "+" if change >= 0 else ""
            r_sign = "+" if rate >= 0 else ""
            lines.append(f"  PRESSURE TREND (next {len(press_readings) - 1}h): {sign}{change:.1f} hPa ({r_sign}{rate:.1f} hPa/hr)")
            if rate <= -3:
                lines.append("  [!] DANGER: Rapid pressure drop -- severe cyclone intensification")
            elif rate <= -1:
                lines.append("  [W] Pressure falling -- storm approaching")
            lines.append("")

        max_gust = max((h.get("gustSpeedKmh") or 0 for h in data["hours"]), default=0)
        min_press = min((h["pressureHpa"] for h in data["hours"] if h.get("pressureHpa") is not None), default=0)
        max_wave = max((h.get("waveHeightM") or 0 for h in data["hours"]), default=0)
        max_rain = max((h.get("rainMmH") or 0 for h in data["hours"]), default=0)

        lines.append(f"  PEAK CONDITIONS (next {hours}h):")
        lines.append(f"     Min pressure: {min_press:.1f} hPa")
        lines.append(f"     Max gust: {max_gust:.0f} km/h")
        lines.append(f"     Max wave: {max_wave:.1f} m")
        lines.append(f"     Max rain rate: {max_rain:.1f} mm/h")
        lines.append("")

        lines.append(f"  {'Time':<10} {'Press':<9} {'Wind':<10} {'Gust':<10} {'Dir':<5} {'Wave':<7} Rain")
        lines.append("  " + "-" * 64)
        for h in data["hours"]:
            t = pad_right(format_nz_time(h["time"]), 10)
            press = pad_right(f"{h['pressureHpa']:.1f}" if h["pressureHpa"] is not None else "-", 9)
            wind = pad_right(f"{num(h['windSpeedKmh'], 0)}km/h", 10)
            gust_s = pad_right(f"{num(h['gustSpeedKmh'], 0)}km/h", 10)
            d = pad_right(deg_to_compass(h["windDirDeg"]), 5)
            wave = pad_right(f"{num(h['waveHeightM'])}m" if h["waveHeightM"] is not None else "-", 7)
            rain_s = f"{num(h['rainMmH'])}mm/h"
            lines.append(f"  {t} {press} {wind} {gust_s} {d} {wave} {rain_s}")

        lines.append("")
        lines.append("  Thresholds: Pressure <990 hPa = cyclone | Wind >63 km/h = TC | >118 km/h = severe TC")
        lines.append("  Pressure drop >3 hPa/hr = rapid intensification")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_pressure(args: argparse.Namespace) -> None:
    loc = get_location(args, getattr(args, "location_pos", None))
    data = fetch_pressure_trend(loc)

    def render() -> str:
        lines = [f"{loc['name']} — Pressure Trend", ""]
        lines.append(f"   Current: {num(data['currentHpa'], 1)} hPa")
        lines.append(f"   Trend: {data['trend']['direction'].upper()}")
        cph = data["trend"]["changePerHour"]
        if cph is not None:
            sign = "+" if cph >= 0 else ""
            lines.append(f"   Rate: {sign}{cph:.2f} hPa/hr")
        c3h = data["trend"]["change3h"]
        if c3h is not None:
            sign = "+" if c3h >= 0 else ""
            lines.append(f"   3h change: {sign}{c3h:.1f} hPa")
        c6h = data["trend"]["change6h"]
        if c6h is not None:
            sign = "+" if c6h >= 0 else ""
            lines.append(f"   6h change: {sign}{c6h:.1f} hPa")
        if data["trend"].get("severity"):
            lines.append(f"   {data['trend']['severity']}")
        lines.append("")
        lines.append("   12h history -> 12h forecast:")
        lines.append(f"   {'Time':<10} {'hPa':<10} Bar")
        lines.append("   " + "-" * 50)
        valid = [r for r in data["readings"] if r["pressureHpa"] is not None]
        if valid:
            min_p = min(r["pressureHpa"] for r in valid)
            max_p = max(r["pressureHpa"] for r in valid)
            range_p = max(max_p - min_p, 1)
            for r in data["readings"]:
                t = pad_right(format_nz_time(r["time"]), 10)
                hpa = pad_right(f"{r['pressureHpa']:.1f}" if r["pressureHpa"] is not None else "-", 10)
                bar_len = round(((r["pressureHpa"] - min_p) / range_p) * 30) if r["pressureHpa"] is not None else 0
                bar = "#" * bar_len if bar_len > 0 else ""
                lines.append(f"   {t} {hpa} {bar}")
        lines.append("")
        lines.append("   Key: >3 hPa/hr drop = DANGER (rapid cyclone intensification)")
        lines.append("        <990 hPa = tropical cyclone territory")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_watch(args: argparse.Namespace) -> None:
    """Continuous cyclone monitoring — polls every N minutes."""
    loc = get_location(args, getattr(args, "location_pos", None))
    interval_ms = int(getattr(args, "interval", 5) or 5) * 60 * 1000
    last_pressure: float | None = None
    poll_count = 0

    print(f"Watching {loc['name']} — polling every {args.interval} min (Ctrl+C to stop)")
    print("")

    import time as _time

    def poll() -> None:
        nonlocal last_pressure, poll_count
        poll_count += 1
        try:
            data = fetch_cyclone_data(loc, 6)
            current = data["hours"][0] if data["hours"] else None
            if not current:
                return

            now_str = format_nz_datetime(data["time"])
            pressure_change = None
            if last_pressure is not None and current.get("pressureHpa") is not None:
                pressure_change = current["pressureHpa"] - last_pressure

            if args.json:
                print(json.dumps({
                    "poll": poll_count,
                    "time": data["time"],
                    "pressureHpa": current.get("pressureHpa"),
                    "pressureChange": pressure_change,
                    "windSpeedKmh": current.get("windSpeedKmh"),
                    "gustSpeedKmh": current.get("gustSpeedKmh"),
                    "windDir": deg_to_compass(current.get("windDirDeg")),
                    "waveHeightM": current.get("waveHeightM"),
                    "rainMmH": current.get("rainMmH"),
                }))
            else:
                change_str = ""
                if pressure_change is not None:
                    sign = "+" if pressure_change >= 0 else ""
                    change_str = f" ({sign}{pressure_change:.1f})"

                p = current.get("pressureHpa")
                g = current.get("gustSpeedKmh")
                alert = ""
                if p is not None and p < 990:
                    alert = " [!] CYCLONE"
                elif g is not None and g > 118:
                    alert = " [!] SEVERE WIND"
                elif g is not None and g > 63:
                    alert = " [W] HIGH WIND"
                elif pressure_change is not None and pressure_change < -3:
                    alert = " [!] RAPID DROP"

                print(
                    f"[{now_str}] P: {num(p, 1)} hPa{change_str} | "
                    f"Wind: {num(current.get('windSpeedKmh'), 0)}/{num(g, 0)} km/h {deg_to_compass(current.get('windDirDeg'))} | "
                    f"Wave: {num(current.get('waveHeightM'))}m | Rain: {num(current.get('rainMmH'))}mm/h{alert}"
                )

            last_pressure = current.get("pressureHpa")
        except SystemExit:
            raise
        except Exception as err:
            print(f"[Poll {poll_count}] Error: {err}", file=sys.stderr)

    poll()
    interval_s = interval_ms / 1000
    while True:
        _time.sleep(interval_s)
        poll()


def cmd_locations(args: argparse.Namespace) -> None:
    locs = [
        {"key": k, "name": v["name"], "lat": v["lat"], "lon": v["lon"]}
        for k, v in LOCATIONS.items()
    ]

    def render() -> str:
        lines = ["Known Locations", ""]
        lines.append(f"{'Key':<15} {'Name':<18} {'Lat':<10} Lon")
        lines.append("-" * 55)
        for loc in locs:
            lines.append(f"{loc['key']:<15} {loc['name']:<18} {loc['lat']:.4f}     {loc['lon']:.4f}")
        lines.append("")
        lines.append("Usage: <command> <location>  (e.g. now auckland)")
        lines.append("Custom: --location lat,lon  (e.g. --location -37.0,175.5)")
        return "\n".join(lines)

    emit(locs, args.json, render)


# --- Parser ---

def add_location_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("location_pos", nargs="?", metavar="location",
                    help="named location or lat,lon (e.g. auckland, -36.85,174.76)")
    sp.add_argument("--location", metavar="LAT,LON",
                    help="custom coordinates as lat,lon")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Query NZ weather data from the MetOcean API and MetService public site."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("now", help="current conditions snapshot")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_now)

    sp = sub.add_parser("forecast", help="24-hour hourly forecast")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_forecast)

    sp = sub.add_parser("daily", help="7-day daily summary")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_daily)

    sp = sub.add_parser("marine", help="marine forecast: waves, swell, sea temperature")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_marine)

    sp = sub.add_parser("wind", help="detailed wind forecast")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wind)

    sp = sub.add_parser("rain", help="precipitation forecast")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_rain)

    sp = sub.add_parser("warnings", help="scrape MetService severe weather warnings (no API key needed)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_warnings)

    sp = sub.add_parser("cyclone", help="cyclone-specific data: pressure, extreme wind, storm surge indicators")
    add_location_args(sp)
    sp.add_argument("--hours", type=int, default=48, help="hours to forecast (default 48)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cyclone)

    sp = sub.add_parser("pressure", help="barometric pressure trend — key cyclone indicator")
    add_location_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_pressure)

    sp = sub.add_parser("watch", help="continuous cyclone monitoring — polls on an interval")
    add_location_args(sp)
    sp.add_argument("--interval", type=int, default=5, help="polling interval in minutes (default 5)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("locations", help="list known locations")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_locations)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
