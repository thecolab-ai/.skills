#!/usr/bin/env python3
"""NZ electricity public-data CLI.

Read-only stdlib wrapper around public EM6 JSON feeds and EMI CSV datasets.
No login, API key, browser automation, cache, or data mutation.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Callable, Iterable

EM6_BASE = "https://api.em6.co.nz/ords/em6/data_api"
EMI_DATASETS = "https://www.emi.ea.govt.nz/Wholesale/Datasets"
EMI_FINAL_PRICES = EMI_DATASETS + "/DispatchAndPricing/FinalEnergyPrices"
EMI_GENERATION_MD = EMI_DATASETS + "/Generation/Generation_MD"
EMI_DEMAND_REPORT = "https://www.emi.ea.govt.nz/Wholesale/Download/DataReport/CSV/W_GD_C"
UA = "nz-electricity-skill/1.0 (+https://github.com/thecolab-ai/.skills)"

REGION_ALIASES = {
    "northland": 1,
    "auckland": 2,
    "hamilton": 3,
    "edgecumbe": 4,
    "hawkes bay": 5,
    "hawkesbay": 5,
    "taranaki": 6,
    "bunnythorpe": 7,
    "wellington": 8,
    "nelson": 9,
    "christchurch": 10,
    "canterbury": 11,
    "west coast": 12,
    "westcoast": 12,
    "otago": 13,
    "southland": 14,
}

FUEL_ALIASES = {
    "hydro": "Hydro",
    "wind": "Wind",
    "geothermal": "Geothermal",
    "gas": "Gas",
    "coal": "Coal",
    "diesel": "Diesel",
    "biogas": "Biogas",
    "cogen": "Co-generation",
    "co-generation": "Co-generation",
}

DEMAND_REGION_ALIASES = {
    "nz": ("NZ", "NZ"),
    "new zealand": ("NZ", "NZ"),
    "uni": ("ZONE", "UNI"),
    "upper north island": ("ZONE", "UNI"),
    "cni": ("ZONE", "CNI"),
    "central north island": ("ZONE", "CNI"),
    "lni": ("ZONE", "LNI"),
    "lower north island": ("ZONE", "LNI"),
    "usi": ("ZONE", "USI"),
    "upper south island": ("ZONE", "USI"),
    "lsi": ("ZONE", "LSI"),
    "lower south island": ("ZONE", "LSI"),
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-electricity: {message}", file=sys.stderr)
    raise SystemExit(code)


def request(url: str, timeout: int = 30) -> urllib.response.addinfourl:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    url = EM6_BASE + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    try:
        with request(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("message") or payload.get("title") or raw[:240]
        except Exception:
            detail = raw[:240]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def read_url_text(url: str, timeout: int = 30) -> str:
    try:
        with request(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} from {url}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def fetch_csv_rows(
    url: str,
    keep: Callable[[dict[str, str]], bool],
    timeout: int = 60,
) -> tuple[list[dict[str, str]], str]:
    try:
        with request(url, timeout=timeout) as resp:
            final_url = resp.geturl()
            text = io.TextIOWrapper(resp, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text)
            rows = [row for row in reader if keep(row)]
            return rows, final_url
    except urllib.error.HTTPError as e:
        raise e
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")


def try_csv_rows(urls: Iterable[str], keep: Callable[[dict[str, str]], bool]) -> tuple[list[dict[str, str]], str | None]:
    last_status = None
    for url in urls:
        try:
            return fetch_csv_rows(url, keep)
        except urllib.error.HTTPError as e:
            last_status = e.code
            if e.code in (404, 500):
                continue
            raw = e.read().decode("utf-8", "replace")
            die(f"HTTP {e.code} from {url}: {raw[:240]}")
    if last_status:
        return [], None
    return [], None


def fetch_report_csv_rows(url: str, timeout: int = 60) -> tuple[list[dict[str, str]], str]:
    try:
        with request(url, timeout=timeout) as resp:
            final_url = resp.geturl()
            text = resp.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:240]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("Period start,"):
            reader = csv.DictReader(lines[idx:])
            return [row for row in reader], final_url
    die(f"could not find report CSV header in response from {url}")


def parse_date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        die(f"expected DATE as YYYY-MM-DD, received: {raw}")


def parse_month(raw: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", raw):
        die(f"expected month as YYYY-MM, received: {raw}")
    year, month = raw.split("-")
    try:
        dt.date(int(year), int(month), 1)
    except ValueError:
        die(f"expected valid month as YYYY-MM, received: {raw}")
    return year + month


def dates_between(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    step = dt.timedelta(days=1)
    cur = start
    while cur <= end:
        yield cur
        cur += step


def months_between(start: dt.date, end: dt.date) -> Iterable[str]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield f"{year:04d}{month:02d}"
        month += 1
        if month == 13:
            month = 1
            year += 1


def latest_daily_price_date() -> dt.date:
    html = read_url_text(EMI_FINAL_PRICES)
    match = re.search(r"(\d{8})_FinalEnergyPrices(?:_I)?\.csv", html)
    if not match:
        die("could not find latest EMI final energy price CSV in dataset listing")
    return dt.date.fromisoformat(f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}")


def latest_generation_month() -> str:
    html = read_url_text(EMI_GENERATION_MD)
    match = re.search(r"(\d{6})_Generation_MD\.csv", html)
    if not match:
        die("could not find latest EMI generation CSV in dataset listing")
    return match.group(1)


def month_label(yyyymm: str) -> str:
    return f"{yyyymm[:4]}-{yyyymm[4:]}"


def iso_date_from_emi(raw: str) -> str:
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw):
        d, m, y = raw.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return raw


def as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def round2(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def resolve_region(raw: str | None, items: list[dict[str, Any]]) -> int | None:
    if not raw:
        return None
    needle = raw.strip().lower()
    if needle.isdigit():
        return int(needle)
    if needle in REGION_ALIASES:
        return REGION_ALIASES[needle]
    matches = [
        int(item["grid_zone_id"])
        for item in items
        if needle in str(item.get("grid_zone_name", "")).lower()
    ]
    if len(matches) == 1:
        return matches[0]
    valid = ", ".join(str(item.get("grid_zone_name")) for item in items)
    die(f"unknown or ambiguous region '{raw}'. Valid regions: {valid}")


def cmd_spot(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = request_json("/region/price/")
    items = list(payload.get("items") or []) if isinstance(payload, dict) else []
    region_id = resolve_region(args.region, items)
    if region_id is not None:
        items = [item for item in items if int(item.get("grid_zone_id", -1)) == region_id]
    if region_id is not None and not items:
        die(f"no EM6 spot price returned for region {args.region}")
    items = sorted(items, key=lambda x: int(x.get("grid_zone_id", 0)))
    data = {
        "source": "EM6 Current Regional Price API",
        "source_url": EM6_BASE + "/region/price/",
        "count": len(items),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "prices": [
            {
                "timestamp": item.get("timestamp"),
                "trading_period": item.get("trading_period"),
                "grid_zone_id": item.get("grid_zone_id"),
                "grid_zone_name": item.get("grid_zone_name"),
                "dollars_per_mwh": item.get("price"),
            }
            for item in items
        ],
    }
    emit(data, args.json, render_spot)


def cmd_carbon(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = request_json("/current_carbon_intensity/")
    items = list(payload.get("items") or []) if isinstance(payload, dict) else []
    data = {
        "source": "EM6 Current Carbon Intensity API",
        "source_url": EM6_BASE + "/current_carbon_intensity/",
        "count": len(items),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "readings": items,
    }
    emit(data, args.json, render_carbon)


def nz_datetime(raw: str) -> str:
    raw = raw.strip()
    try:
        parsed = dt.datetime.strptime(raw, "%d/%m/%Y %H:%M:%S")
        return parsed.isoformat()
    except ValueError:
        return raw


def resolve_demand_region(raw: str | None) -> tuple[str, str | None, str]:
    value = (raw or "nz").strip().lower().replace("-", " ")
    if value in DEMAND_REGION_ALIASES:
        region_type, region_id = DEMAND_REGION_ALIASES[value]
        label = region_id if region_id else "NZ"
        return region_type, region_id, label
    valid = "NZ, UNI, CNI, LNI, USI, LSI"
    die(f"unknown demand region '{raw}'. Valid regions: {valid}")


def demand_report_url(start: dt.date, end: dt.date, region_type: str) -> str:
    params = {
        "DateFrom": start.strftime("%Y%m%d"),
        "DateTo": end.strftime("%Y%m%d"),
        "RegionType": region_type,
        "TimeScale": "TP",
        "Show": "Gwh",
        "_rsdr": "Y6",
        "_si": "v|4",
    }
    return EMI_DEMAND_REPORT + "?" + urllib.parse.urlencode(params)


def cmd_demand(args: argparse.Namespace) -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    start = parse_date(args.from_date) if args.from_date else today
    end = parse_date(args.to_date) if args.to_date else start
    if end < start:
        die("--to must be on or after --from")
    region_type, region_id, region_label = resolve_demand_region(args.region)

    started = time.perf_counter()
    url = demand_report_url(start, end, region_type)
    rows, source_url = fetch_report_csv_rows(url)
    demand = []
    for row in rows:
        if region_id and row.get("Region ID") != region_id:
            continue
        value = as_float(row.get("Demand (GWh)"))
        cost = as_float(row.get("Demand ($)"))
        if value is None:
            continue
        demand.append(
            {
                "period_start": nz_datetime(row.get("Period start", "")),
                "period_end": nz_datetime(row.get("Period end", "")),
                "region_id": row.get("Region ID"),
                "region": row.get("Region"),
                "demand_gwh": value,
                "average_mw": round(value * 2000, 1),
                "demand_dollars": cost,
            }
        )

    values = [row["demand_gwh"] for row in demand]
    peak = max(demand, key=lambda row: row["demand_gwh"]) if demand else None
    data = {
        "source": "EMI Demand Trends CSV report",
        "source_url": source_url,
        "region_type": region_type,
        "region_filter": region_label,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "timezone": "Pacific/Auckland local time as reported by EMI",
        "count": len(demand),
        "summary": {
            "total_gwh": round(sum(values), 3) if values else 0,
            "average_gwh_per_period": round(statistics.fmean(values), 3) if values else None,
            "peak_gwh": round(peak["demand_gwh"], 3) if peak else None,
            "peak_average_mw": peak["average_mw"] if peak else None,
            "peak_period_start": peak["period_start"] if peak else None,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "demand": demand,
    }
    emit(data, args.json, render_demand)


def price_source_urls(day: dt.date) -> list[str]:
    ymd = day.strftime("%Y%m%d")
    return [
        f"{EMI_FINAL_PRICES}/{ymd}_FinalEnergyPrices.csv",
        f"{EMI_FINAL_PRICES}/{ymd}_FinalEnergyPrices_I.csv",
    ]


def monthly_price_source_urls(yyyymm: str) -> list[str]:
    return [
        f"{EMI_FINAL_PRICES}/ByMonth/{yyyymm}_FinalEnergyPrices.csv",
        f"{EMI_FINAL_PRICES}/ByMonth/{yyyymm}_FinalEnergyPrices_incomplete.csv",
    ]


def price_rows_from_month(node: str, start: dt.date, end: dt.date, yyyymm: str) -> tuple[list[dict[str, str]], str | None]:
    def keep(row: dict[str, str]) -> bool:
        row_date = parse_date(iso_date_from_emi(row.get("TradingDate", "")))
        return start <= row_date <= end and row.get("PointOfConnection", "").upper() == node

    return try_csv_rows(monthly_price_source_urls(yyyymm), keep)


def price_rows_from_day(node: str, day: dt.date) -> tuple[list[dict[str, str]], str | None]:
    day_iso = day.isoformat()

    def keep(row: dict[str, str]) -> bool:
        return iso_date_from_emi(row.get("TradingDate", "")) == day_iso and row.get("PointOfConnection", "").upper() == node

    return try_csv_rows(price_source_urls(day), keep)


def cmd_prices(args: argparse.Namespace) -> None:
    node = args.node.upper()
    if args.from_date:
        start = parse_date(args.from_date)
    elif args.to_date:
        start = parse_date(args.to_date)
    else:
        start = latest_daily_price_date()
    end = parse_date(args.to_date) if args.to_date else start
    if end < start:
        die("--to must be on or after --from")

    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    missing_sources: list[str] = []
    covered_dates: set[str] = set()

    for yyyymm in months_between(start, end):
        month_rows, source_url = price_rows_from_month(node, start, end, yyyymm)
        if source_url:
            rows.extend(month_rows)
            sources.append(source_url)
            covered_dates.update(iso_date_from_emi(row["TradingDate"]) for row in month_rows)
            continue

        year = int(yyyymm[:4])
        month = int(yyyymm[4:])
        for day in dates_between(max(start, dt.date(year, month, 1)), end):
            if day.year != year or day.month != month:
                continue
            day_rows, day_source = price_rows_from_day(node, day)
            if day_source:
                rows.extend(day_rows)
                sources.append(day_source)
                covered_dates.add(day.isoformat())
            else:
                missing_sources.append(day.isoformat())

    prices = []
    for row in rows:
        value = as_float(row.get("DollarsPerMegawattHour"))
        if value is None:
            continue
        prices.append(
            {
                "trading_date": iso_date_from_emi(row.get("TradingDate", "")),
                "trading_period": int(row.get("TradingPeriod") or 0),
                "point_of_connection": row.get("PointOfConnection"),
                "dollars_per_mwh": value,
            }
        )
    prices.sort(key=lambda x: (x["trading_date"], x["trading_period"]))
    values = [row["dollars_per_mwh"] for row in prices]
    summary = {
        "min": round2(min(values) if values else None),
        "max": round2(max(values) if values else None),
        "average": round2(statistics.fmean(values) if values else None),
    }
    data = {
        "source": "EMI Final and Interim Energy Prices CSV datasets",
        "source_url": EMI_FINAL_PRICES,
        "node": node,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "count": len(prices),
        "summary": summary,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "sources": sorted(set(sources)),
        "missing_dates": sorted(set(missing_sources)),
        "prices": prices,
    }
    emit(data, args.json, render_prices)


def generation_url(yyyymm: str) -> str:
    return f"{EMI_GENERATION_MD}/{yyyymm}_Generation_MD.csv"


def normalise_fuel(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    return FUEL_ALIASES.get(key, raw.strip())


def row_kwh(row: dict[str, str]) -> float:
    total = 0.0
    for key, value in row.items():
        if not key.startswith("TP"):
            continue
        parsed = as_float(value)
        if parsed is not None:
            total += parsed
    return total


def cmd_generation(args: argparse.Namespace) -> None:
    yyyymm = parse_month(args.month) if args.month else latest_generation_month()
    fuel_filter = normalise_fuel(args.type)
    started = time.perf_counter()

    try:
        rows, source_url = fetch_csv_rows(generation_url(yyyymm), lambda row: True)
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} fetching EMI generation file for {month_label(yyyymm)}")

    fuel_totals: dict[str, float] = defaultdict(float)
    tech_totals: dict[str, float] = defaultdict(float)
    plant_totals: dict[tuple[str, str, str, str], float] = defaultdict(float)
    input_rows = 0
    matched_rows = 0
    for row in rows:
        input_rows += 1
        fuel = row.get("Fuel_Code") or "Unknown"
        if fuel_filter and fuel.lower() != fuel_filter.lower():
            continue
        matched_rows += 1
        kwh = row_kwh(row)
        fuel_totals[fuel] += kwh
        tech_totals[row.get("Tech_Code") or "Unknown"] += kwh
        key = (
            row.get("Gen_Code") or "unknown",
            row.get("Fuel_Code") or "Unknown",
            row.get("Tech_Code") or "Unknown",
            row.get("Site_Code") or "",
        )
        plant_totals[key] += kwh

    total_kwh = sum(fuel_totals.values())
    fuel_items = [
        {
            "fuel_type": fuel,
            "gwh": round(kwh / 1_000_000, 3),
            "share_pct": round((kwh / total_kwh) * 100, 2) if total_kwh else 0,
        }
        for fuel, kwh in sorted(fuel_totals.items(), key=lambda item: item[1], reverse=True)
    ]
    tech_items = [
        {
            "technology": tech,
            "gwh": round(kwh / 1_000_000, 3),
            "share_pct": round((kwh / total_kwh) * 100, 2) if total_kwh else 0,
        }
        for tech, kwh in sorted(tech_totals.items(), key=lambda item: item[1], reverse=True)
    ]
    plant_items = [
        {
            "plant": key[0],
            "fuel_type": key[1],
            "technology": key[2],
            "site_code": key[3],
            "gwh": round(kwh / 1_000_000, 3),
        }
        for key, kwh in sorted(plant_totals.items(), key=lambda item: item[1], reverse=True)
    ]
    limit = args.limit if args.limit is not None else 20
    data = {
        "source": "EMI Generation output by plant CSV dataset",
        "source_url": source_url,
        "month": month_label(yyyymm),
        "fuel_filter": fuel_filter,
        "input_rows": input_rows,
        "matched_rows": matched_rows,
        "total_gwh": round(total_kwh / 1_000_000, 3),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "fuel_totals": fuel_items,
        "technology_totals": tech_items,
        "returned_plants": min(len(plant_items), limit),
        "total_plants": len(plant_items),
        "plants": plant_items[:limit],
    }
    emit(data, args.json, render_generation)


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def render_spot(data: dict[str, Any]) -> str:
    prices = data.get("prices") or []
    if not prices:
        return "No regional spot prices returned."
    first = prices[0]
    lines = [
        f"EM6 regional spot prices: {len(prices)} region(s) ({data.get('elapsed_ms')} ms)",
        f"Timestamp: {first.get('timestamp')}  TP{first.get('trading_period')}",
        "",
    ]
    for item in prices:
        lines.append(
            f"{str(item.get('grid_zone_id')).rjust(2)}  "
            f"{str(item.get('grid_zone_name')).ljust(14)} "
            f"{money(item.get('dollars_per_mwh'))}/MWh"
        )
    return "\n".join(lines)


def render_carbon(data: dict[str, Any]) -> str:
    readings = data.get("readings") or []
    if not readings:
        return "No carbon intensity readings returned."
    latest = readings[0]
    lines = [
        f"EM6 current carbon intensity ({data.get('elapsed_ms')} ms)",
        f"Timestamp: {latest.get('timestamp')}  TP{latest.get('trading_period')}",
        f"Carbon intensity: {latest.get('nz_carbon_gkwh')} gCO2/kWh",
        f"Renewable generation: {latest.get('nz_renewable')}%",
        f"24h range: {latest.get('min_24hrs_gkwh')} - {latest.get('max_24hrs_gkwh')} gCO2/kWh",
    ]
    return "\n".join(lines)


def render_demand(data: dict[str, Any]) -> str:
    rows = data.get("demand") or []
    summary = data.get("summary") or {}
    lines = [
        f"EMI demand for {data.get('region_filter')}: {data.get('count')} trading periods ({data.get('elapsed_ms')} ms)",
        f"Range: {data.get('from')} to {data.get('to')}",
    ]
    if rows:
        lines.append(
            f"Total {summary.get('total_gwh')} GWh  "
            f"peak {summary.get('peak_gwh')} GWh ({summary.get('peak_average_mw')} MW avg) "
            f"at {summary.get('peak_period_start')}"
        )
    lines.append("")
    for item in rows[:24]:
        lines.append(
            f"{item.get('period_start')}  {item.get('region_id', '').ljust(3)}  "
            f"{item.get('demand_gwh'):.3f} GWh  {item.get('average_mw'):,.1f} MW avg"
        )
    if len(rows) > 24:
        lines.append(f"... {len(rows) - 24} more rows; use --json for full output")
    return "\n".join(lines).rstrip()


def render_prices(data: dict[str, Any]) -> str:
    prices = data.get("prices") or []
    lines = [
        f"EMI prices for {data.get('node')}: {data.get('count')} trading periods ({data.get('elapsed_ms')} ms)",
        f"Range: {data.get('from')} to {data.get('to')}",
    ]
    summary = data.get("summary") or {}
    if prices:
        lines.append(
            f"Average {money(summary.get('average'))}/MWh  "
            f"min {money(summary.get('min'))}  max {money(summary.get('max'))}"
        )
    if data.get("missing_dates"):
        lines.append(f"Missing source files: {', '.join(data['missing_dates'])}")
    lines.append("")
    for item in prices[:24]:
        lines.append(
            f"{item.get('trading_date')} TP{str(item.get('trading_period')).rjust(2)}  "
            f"{money(item.get('dollars_per_mwh'))}/MWh"
        )
    if len(prices) > 24:
        lines.append(f"... {len(prices) - 24} more rows; use --json for full output")
    return "\n".join(lines).rstrip()


def render_generation(data: dict[str, Any]) -> str:
    lines = [
        f"EMI generation output by plant: {data.get('month')} ({data.get('elapsed_ms')} ms)",
        f"Total: {data.get('total_gwh')} GWh",
    ]
    if data.get("fuel_filter"):
        lines.append(f"Fuel filter: {data.get('fuel_filter')}")
    lines.append("")
    lines.append("Fuel totals")
    for item in data.get("fuel_totals") or []:
        lines.append(f"{item['fuel_type'].ljust(14)} {item['gwh']:>10,.3f} GWh  {item['share_pct']:>5.2f}%")
    lines.append("")
    lines.append(f"Top plants ({data.get('returned_plants')} of {data.get('total_plants')})")
    for item in data.get("plants") or []:
        lines.append(f"{item['plant'].ljust(24)} {item['fuel_type'].ljust(12)} {item['gwh']:>10,.3f} GWh")
    return "\n".join(lines).rstrip()


def emit(data: dict[str, Any], as_json: bool, render: Callable[[dict[str, Any]], str]) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected positive integer, received: {raw}")
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected positive integer, received: {raw}")
    return value


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Read-only NZ electricity data CLI using public EM6 JSON feeds and EMI CSV/report data."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("spot", help="current EM6 regional wholesale spot prices")
    sp.add_argument("--region", help="grid zone id or name, e.g. auckland, wellington, 2")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_spot)

    sp = sub.add_parser("carbon", help="current EM6 NZ carbon intensity and renewable percentage")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_carbon)

    sp = sub.add_parser("demand", help="EMI grid demand by New Zealand or zone region")
    sp.add_argument("--region", help="NZ, UNI, CNI, LNI, USI, or LSI; default NZ")
    sp.add_argument("--from", dest="from_date", help="start date YYYY-MM-DD; defaults to today")
    sp.add_argument("--to", dest="to_date", help="end date YYYY-MM-DD; defaults to --from")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_demand)

    sp = sub.add_parser("prices", help="historical EMI final/interim energy prices for a node")
    sp.add_argument("--node", required=True, help="point of connection code, e.g. BEN2201")
    sp.add_argument("--from", dest="from_date", help="start date YYYY-MM-DD; defaults to latest available daily file")
    sp.add_argument("--to", dest="to_date", help="end date YYYY-MM-DD; defaults to --from")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_prices)

    sp = sub.add_parser("generation", help="monthly EMI generation output by fuel type and plant")
    sp.add_argument("--type", choices=sorted(FUEL_ALIASES), help="fuel type filter")
    sp.add_argument("--month", help="month YYYY-MM; defaults to latest available EMI Generation_MD month")
    sp.add_argument("--limit", type=positive_int, help="limit returned top plants; default 20")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_generation)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
