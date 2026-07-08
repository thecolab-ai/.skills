#!/usr/bin/env python3
"""NZ electricity public-data CLI.

Read-only stdlib wrapper around public electricity JSON feeds and EMI CSV datasets.
No login, private API key, browser automation, cache, or data mutation.
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

import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

EM6_BASE = "https://api.em6.co.nz/ords/em6/data_api"
EMI_DATASETS = "https://www.emi.ea.govt.nz/Wholesale/Datasets"
EMI_FINAL_PRICES = EMI_DATASETS + "/DispatchAndPricing/FinalEnergyPrices"
EMI_GENERATION_MD = EMI_DATASETS + "/Generation/Generation_MD"
EMI_DEMAND_REPORT = "https://www.emi.ea.govt.nz/Wholesale/Download/DataReport/CSV/W_GD_C"
EMI_DG_REPORT = "https://www.emi.ea.govt.nz/Retail/Download/DataReport/CSV/GUEHMT"
EMI_DG_REPORT_PAGE = "https://www.emi.ea.govt.nz/retail/Reports/guehmt"
EA_ENERGY_MARGIN_DASHBOARD = "https://www.ea.govt.nz/data-and-insights/charts-and-dashboards/energy-margin/"
EA_ENERGY_MARGIN_ARTICLE = "https://www.ea.govt.nz/news/eye-on-electricity/gentailer-energy-margins-in-2024/"
TABLEAU_ENERGY_MARGIN_VIEW = "https://public.tableau.com/views/Energymargin/Energymargin?:showVizHome=no&:embed=y&:display_count=n&:origin=viz_share_link"
TABLEAU_ENERGY_MARGIN_PROFILE_API = "https://public.tableau.com/profile/api/single_workbook/Energymargin"
TABLEAU_ENERGY_MARGIN_VIZQL = (
    "https://public.tableau.com/vizql/w/Energymargin/v/Energymargin/startSession/viewing"
    "?%3AshowVizHome=no&%3Aembed=y&%3Adisplay_count=n&%3Aorigin=viz_share_link&%3Aredirect=auth"
)
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

DG_CAVEATS = [
    "Market segment breakdowns are not mutually exclusive; do not sum segments as unique ICP counts.",
    "Solar+Batteries and Wind+Batteries registry categories were added in November 2023; Solar and Other series can show category-change spikes around that period.",
    "Values are derived from registry Fuel Type and Generation Capacity fields populated by distributors.",
]

DG_FUEL_ALIASES = {
    "all": "All_Total",
    "all-total": "All_Total",
    "all_total": "All_Total",
    "all combined": "All_Total",
    "battery-standalone": "standalone batt",
    "standalone-battery": "standalone batt",
    "standalone batt": "standalone batt",
    "battery-ev": "electric vehicl",
    "ev-battery": "electric vehicl",
    "electric vehicl": "electric vehicl",
    "bio-mass": "bio-mass",
    "biomass": "bio-mass",
    "fresh-water": "fresh water",
    "fresh water": "fresh water",
    "geothermal": "geothermal",
    "industrial-processes": "industrial proc",
    "industrial proc": "industrial proc",
    "liquid-fuel": "liquid fuel",
    "liquid fuel": "liquid fuel",
    "natural-gas": "natural gas",
    "natural gas": "natural gas",
    "solar": "solar",
    "solar-without-battery": "solar",
    "solarplusbattery": "solarplusbattery",
    "solar-with-battery": "solarplusbattery",
    "solar_all": "solar_all",
    "solar-all": "solar_all",
    "tidal": "tidal",
    "wind": "wind",
    "other": "other",
    "undefined": "undefined",
}

DG_MARKET_SEGMENT_ALIASES = {
    "all": "All",
    "all-icps": "All",
    "all icps": "All",
    "res": "Res",
    "residential": "Res",
    "sme": "SME",
    "small-medium-enterprises": "SME",
    "small medium enterprises": "SME",
    "com": "Com",
    "commercial": "Com",
    "ind": "Ind",
    "industrial": "Ind",
}

DG_CAPACITY_ALIASES = {
    "all": "All_Total",
    "all-total": "All_Total",
    "all_total": "All_Total",
    "all-combined": "All_Total",
    "all combined": "All_Total",
    "small": "Small",
    "less-than-10kw": "Small",
    "less-than-or-equal-10kw": "Small",
    "<=10kw": "Small",
    "large": "Large",
    "more-than-10kw": "Large",
    ">10kw": "Large",
}

DG_REGION_TYPE_ALIASES = {
    "nz": "NZ",
    "new-zealand": "NZ",
    "new zealand": "NZ",
    "island": "ISLAND_1",
    "zone": "ZONE",
    "main-centre": "MAIN_CENTRE",
    "main-centres": "MAIN_CENTRE",
    "main centre": "MAIN_CENTRE",
    "main centres": "MAIN_CENTRE",
    "regional-council": "REG_COUNCIL",
    "regional council": "REG_COUNCIL",
    "network-reporting-region": "NWK_REPORTING_REGION_DIST",
    "network reporting region": "NWK_REPORTING_REGION_DIST",
    "network-participant": "NWKP",
    "network participant": "NWKP",
    "root-nsp": "NSP_ROOT",
    "root nsp": "NSP_ROOT",
    "nsp-root": "NSP_ROOT",
    "nsp root": "NSP_ROOT",
}

ENERGY_MARGIN_COMPANIES = {
    "contact": "Contact",
    "genesis": "Genesis",
    "manawa": "Manawa",
    "mercury": "Mercury",
    "meridian": "Meridian",
    "nova": "Nova",
}


def die(message: str, code: int = 1) -> None:
    print(f"nz-electricity: {message}", file=sys.stderr)
    raise SystemExit(code)


def request(
    url: str,
    timeout: int = 30,
    *,
    accept: str = "*/*",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
) -> tuple[bytes, str]:
    """Fetch *url* via the shared nzfetch helper (browser UA + proxy retry on a
    bot-block). Returns (body_bytes, final_url); raises nzfetch.Blocked /
    nzfetch.FetchError, which callers map to their own die/error contract."""
    body, _ct, final_url = nzfetch.fetch_bytes(
        url, timeout=timeout, accept=accept, headers=headers, data=data, method=method
    )
    return body, final_url


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    url = EM6_BASE + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    try:
        body, _final = request(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    raw = body.decode("utf-8", "replace")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def request_url_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> Any:
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    req_headers: dict[str, str] = {}
    if headers:
        req_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    method_arg = method if method and method.upper() != "GET" else None
    payload, _final = request(
        url,
        timeout=timeout,
        accept="application/json, */*",
        headers=req_headers or None,
        data=data,
        method=method_arg,
    )
    raw = payload.decode("utf-8", "replace")
    return json.loads(raw) if raw else None


def read_url_text(url: str, timeout: int = 30) -> str:
    try:
        body, _final = request(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    return body.decode("utf-8", "replace")


def fetch_csv_rows(
    url: str,
    keep: Callable[[dict[str, str]], bool],
    timeout: int = 60,
) -> tuple[list[dict[str, str]], str]:
    # nzfetch errors (Blocked/FetchError) propagate so callers such as
    # try_csv_rows can fall through to the next candidate URL, mirroring the
    # original HTTPError re-raise behaviour.
    body, final_url = request(url, timeout=timeout)
    text = body.decode("utf-8-sig", "replace")
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = [row for row in reader if keep(row)]
    except csv.Error as e:
        die(f"invalid CSV from {url}: {e}")
    return rows, final_url


def try_csv_rows(urls: Iterable[str], keep: Callable[[dict[str, str]], bool]) -> tuple[list[dict[str, str]], str | None]:
    for url in urls:
        try:
            return fetch_csv_rows(url, keep)
        except (nzfetch.Blocked, nzfetch.FetchError):
            continue
    return [], None


def fetch_report_csv_rows(url: str, timeout: int = 60) -> tuple[list[dict[str, str]], str]:
    try:
        body, final_url = request(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    text = body.decode("utf-8-sig", "replace")

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
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.replace(",", "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def as_int(raw: Any) -> int | None:
    value = as_float(raw)
    if value is None:
        return None
    return int(value)


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


def normalise_dg_option(raw: str, aliases: dict[str, str]) -> str:
    value = raw.strip()
    key = re.sub(r"\s+", " ", value.lower())
    for candidate in (key, key.replace("_", "-"), key.replace(" ", "-")):
        if candidate in aliases:
            return aliases[candidate]
    return value


def parse_emi_run_at(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return None


def parse_dg_report_csv(text: str, source_url: str) -> dict[str, Any]:
    lines = text.splitlines()
    header_idx = None
    metadata: dict[str, Any] = {
        "title": None,
        "source_statement": None,
        "run_at": None,
        "run_at_iso": None,
        "parameters": {},
        "source_url": source_url,
    }
    in_parameters = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lstrip("\ufeff").startswith("Month end,"):
            header_idx = idx
            break
        if not stripped:
            continue
        if stripped == "Parameters":
            in_parameters = True
            continue
        if stripped.startswith("Run at:"):
            run_at = stripped.split(":", 1)[1].strip()
            metadata["run_at"] = run_at
            metadata["run_at_iso"] = parse_emi_run_at(run_at)
            continue
        if stripped.startswith("From "):
            metadata["source_statement"] = stripped
            continue
        if in_parameters:
            try:
                parts = next(csv.reader([line]))
            except csv.Error as e:
                die(f"invalid GUEHMT metadata CSV from {source_url}: {e}")
            if len(parts) >= 2:
                metadata["parameters"][parts[0].strip()] = parts[1].strip()
            continue
        if metadata["title"] is None:
            metadata["title"] = stripped

    if header_idx is None:
        die(f"could not find GUEHMT CSV header in response from {source_url}")

    try:
        reader = csv.DictReader(lines[header_idx:])
        rows = []
        for row in reader:
            if not row or not row.get("Month end"):
                continue
            month_end = iso_date_from_emi(row.get("Month end", ""))
            rows.append(
                {
                    "month_end": month_end,
                    "region_id": row.get("Region ID"),
                    "region_name": row.get("Region name"),
                    "capacity_band": row.get("Capacity"),
                    "fuel_type": row.get("Fuel type"),
                    "icp_count": as_int(row.get("ICP count")),
                    "icp_uptake_rate_percent": as_float(row.get("ICP uptake rate (%)")),
                    "total_capacity_mw": as_float(row.get("Total capacity installed (MW)")),
                    "avg_capacity_kw": as_float(row.get("Avg. capacity installed (kW)")),
                    "new_installation_count": as_int(row.get("ICP count - new installations")),
                    "avg_new_installation_capacity_kw": as_float(row.get("Avg. capacity - new installations (kW)")),
                }
            )
    except csv.Error as e:
        die(f"invalid GUEHMT CSV from {source_url}: {e}")

    return {"metadata": metadata, "rows": rows}


def dg_report_url(
    fuel: str,
    market_segment: str,
    capacity: str,
    region_type: str,
    start: dt.date | None,
    end: dt.date | None,
) -> str:
    params: dict[str, str] = {
        "RegionType": region_type,
        "MarketSegment": market_segment,
        "Capacity": capacity,
        "FuelType": fuel,
        "Show": "Capacity",
        "_rsdr": "ALL",
        "_si": "v|4",
    }
    if start:
        params["DateFrom"] = start.strftime("%Y%m%d")
    if end:
        params["DateTo"] = end.strftime("%Y%m%d")
    return EMI_DG_REPORT + "?" + urllib.parse.urlencode(params)


def fetch_dg_report(url: str, timeout: int = 10) -> dict[str, Any]:
    try:
        body, final_url = request(url, timeout=timeout)
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    text = body.decode("utf-8-sig", "replace")
    return parse_dg_report_csv(text, final_url)


def resolve_dg_filters(args: argparse.Namespace) -> tuple[str, str, str, str, dt.date | None, dt.date | None]:
    fuel = normalise_dg_option(args.fuel, DG_FUEL_ALIASES)
    market_segment = normalise_dg_option(args.market_segment, DG_MARKET_SEGMENT_ALIASES)
    capacity = normalise_dg_option(args.capacity, DG_CAPACITY_ALIASES)
    region_type = normalise_dg_option(args.region_type, DG_REGION_TYPE_ALIASES)
    start = parse_date(args.from_date) if getattr(args, "from_date", None) else None
    end = parse_date(args.to_date) if getattr(args, "to_date", None) else None
    if start and end and end < start:
        die("--to must be on or after --from")
    return fuel, market_segment, capacity, region_type, start, end


def filter_dg_rows(rows: list[dict[str, Any]], start: dt.date | None, end: dt.date | None) -> list[dict[str, Any]]:
    if not start and not end:
        return rows
    filtered = []
    for row in rows:
        month_end = parse_date(row["month_end"])
        if start and month_end < start:
            continue
        if end and month_end > end:
            continue
        filtered.append(row)
    return filtered


def sum_number(rows: list[dict[str, Any]], key: str) -> float | int | None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    total = sum(values)
    return int(total) if all(isinstance(value, int) for value in values) else round(float(total), 3)


def summarise_dg_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "first_month_end": None,
            "latest_month_end": None,
            "region_count": 0,
            "latest_icp_count": None,
            "latest_total_capacity_mw": None,
            "icp_count_change": None,
            "capacity_change_mw": None,
            "total_new_installation_count": None,
        }
    ordered = sorted(rows, key=lambda row: (row["month_end"], row.get("region_id") or ""))
    first_month = ordered[0]["month_end"]
    latest_month = ordered[-1]["month_end"]
    first_rows = [row for row in ordered if row["month_end"] == first_month]
    latest_rows = [row for row in ordered if row["month_end"] == latest_month]
    first_icp = sum_number(first_rows, "icp_count")
    latest_icp = sum_number(latest_rows, "icp_count")
    first_capacity = sum_number(first_rows, "total_capacity_mw")
    latest_capacity = sum_number(latest_rows, "total_capacity_mw")
    return {
        "first_month_end": first_month,
        "latest_month_end": latest_month,
        "region_count": len({row.get("region_id") for row in rows if row.get("region_id")}),
        "latest_icp_count": latest_icp,
        "latest_total_capacity_mw": latest_capacity,
        "icp_count_change": latest_icp - first_icp if isinstance(first_icp, int) and isinstance(latest_icp, int) else None,
        "capacity_change_mw": round(latest_capacity - first_capacity, 3)
        if isinstance(first_capacity, (int, float)) and isinstance(latest_capacity, (int, float))
        else None,
        "total_new_installation_count": sum_number(rows, "new_installation_count"),
    }


def yearly_dg_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["month_end"][:4],
            row.get("region_id") or "",
            row.get("capacity_band") or "",
            row.get("fuel_type") or "",
        )
        grouped[key].append(row)

    summaries = []
    for key, group_rows in sorted(grouped.items()):
        ordered = sorted(group_rows, key=lambda row: row["month_end"])
        first = ordered[0]
        latest = ordered[-1]
        summaries.append(
            {
                "year": int(key[0]),
                "region_id": latest.get("region_id"),
                "region_name": latest.get("region_name"),
                "capacity_band": latest.get("capacity_band"),
                "fuel_type": latest.get("fuel_type"),
                "months": len(ordered),
                "first_month_end": first.get("month_end"),
                "last_month_end": latest.get("month_end"),
                "start_icp_count": first.get("icp_count"),
                "end_icp_count": latest.get("icp_count"),
                "icp_count_change": latest.get("icp_count") - first.get("icp_count")
                if first.get("icp_count") is not None and latest.get("icp_count") is not None
                else None,
                "end_total_capacity_mw": latest.get("total_capacity_mw"),
                "capacity_change_mw": round(latest.get("total_capacity_mw") - first.get("total_capacity_mw"), 3)
                if first.get("total_capacity_mw") is not None and latest.get("total_capacity_mw") is not None
                else None,
                "new_installation_count": sum_number(ordered, "new_installation_count"),
            }
        )
    return summaries


def dg_response_base(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    fuel, market_segment, capacity, region_type, start, end = resolve_dg_filters(args)
    started = time.perf_counter()
    url = dg_report_url(fuel, market_segment, capacity, region_type, start, end)
    parsed = fetch_dg_report(url)
    rows = filter_dg_rows(parsed["rows"], start, end)
    metadata = parsed["metadata"]
    base = {
        "source": "EMI Installed distributed generation trends CSV report",
        "report_code": "GUEHMT",
        "report_url": EMI_DG_REPORT_PAGE,
        "source_url": metadata.get("source_url"),
        "emi_run_at": metadata.get("run_at"),
        "emi_run_at_iso": metadata.get("run_at_iso"),
        "emi_metadata": metadata,
        "filters": {
            "fuel": fuel,
            "market_segment": market_segment,
            "capacity": capacity,
            "region_type": region_type,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
        },
        "caveats": DG_CAVEATS,
    }
    return base, rows, started


def cmd_dg_trends(args: argparse.Namespace) -> None:
    base, rows, started = dg_response_base(args)
    data = {
        **base,
        "count": len(rows),
        "summary": summarise_dg_rows(rows),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "trends": rows,
    }
    emit(data, args.json, render_dg_trends)


def cmd_dg_latest(args: argparse.Namespace) -> None:
    base, rows, started = dg_response_base(args)
    latest_month = max((row["month_end"] for row in rows), default=None)
    latest = [row for row in rows if row["month_end"] == latest_month] if latest_month else []
    data = {
        **base,
        "latest_month_end": latest_month,
        "count": len(latest),
        "summary": summarise_dg_rows(latest),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "latest": latest,
    }
    emit(data, args.json, render_dg_latest)


def cmd_dg_summary(args: argparse.Namespace) -> None:
    base, rows, started = dg_response_base(args)
    data = {
        **base,
        "count": len(rows),
        "summary": summarise_dg_rows(rows),
        "yearly": yearly_dg_summary(rows) if args.yearly else [],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    emit(data, args.json, render_dg_summary)


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
    except nzfetch.Blocked as e:
        die(f"network error fetching EMI generation file for {month_label(yyyymm)}: {e}")
    except nzfetch.FetchError as e:
        die(f"error fetching EMI generation file for {month_label(yyyymm)}: {e}")

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


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text or None


def first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def safe_int(value: Any) -> int | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return clean_text(value)


def join_parts(*parts: Any) -> str | None:
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = clean_text(part)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
    return ", ".join(cleaned) if cleaned else None


def parse_datetime_value(value: Any) -> dt.datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return dt.datetime.fromisoformat(text[:-1] + "+00:00")
        return dt.datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def is_active_window(start: Any, end: Any) -> bool:
    parsed_start = parse_datetime_value(start)
    parsed_end = parse_datetime_value(end)
    if not parsed_start or not parsed_end:
        return False
    now = dt.datetime.now(parsed_start.tzinfo) if parsed_start.tzinfo else dt.datetime.now()
    if parsed_end.tzinfo and not now.tzinfo:
        now = now.replace(tzinfo=parsed_end.tzinfo)
    return parsed_start <= now <= parsed_end


def epoch_ms_to_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return clean_text(value)
    if number <= 0:
        return None
    return dt.datetime.fromtimestamp(number / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def iter_geojson_lonlat(value: Any) -> Iterable[tuple[float, float]]:
    if not isinstance(value, list):
        return
    if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
        yield float(value[0]), float(value[1])
        return
    for item in value:
        yield from iter_geojson_lonlat(item)


def geojson_centroid(geometry: dict[str, Any] | None) -> dict[str, float] | None:
    if not geometry:
        return None
    coords = list(iter_geojson_lonlat(geometry.get("coordinates")))
    if not coords:
        return None
    lon = sum(item[0] for item in coords) / len(coords)
    lat = sum(item[1] for item in coords) / len(coords)
    return {"lat": round(lat, 6), "lng": round(lon, 6)}


def outage_record(
    company_key: str,
    company: str,
    status: str,
    location: str | None,
    customers: Any,
    cause: Any,
    estimated_restoration_time: Any,
    outage_start_time: Any,
    source_url: str,
    outage_id: Any = None,
    coordinates: dict[str, float] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "company_key": company_key,
        "company": company,
        "status": status,
        "location": location or "Unknown location",
        "customers_affected": safe_int(customers),
        "cause": clean_text(cause),
        "estimated_restoration_time": clean_text(estimated_restoration_time),
        "outage_start_time": clean_text(outage_start_time),
        "outage_id": clean_text(outage_id),
        "coordinates": coordinates,
        "source_url": source_url,
        "raw": raw or {},
    }


def group_customers(properties: dict[str, Any]) -> int | None:
    groups = properties.get("groupOutages")
    if not isinstance(groups, list):
        return None
    total = 0
    found = False
    for group in groups:
        if not isinstance(group, dict):
            continue
        value = safe_int(group.get("AffectedCustomers"))
        if isinstance(value, int):
            total += value
            found = True
    return total if found else None


def fetch_vector_outages(include_all: bool) -> list[dict[str, Any]]:
    feeds = [
        (
            "https://outagereporter.api.vector.co.nz/outagereporter/outages/shapes",
            "current",
            {"apikey": "o2AGN2LXeYbNvyE5cytNGX9INtcPLfj7"},
        )
    ]
    if include_all:
        feeds.append(
            (
                "https://outage-centre.api.vector.co.nz/v1/outages/planned-outages/shapes",
                "planned",
                {"apikey": "378657d8-674d-4e20-9fcc-4e23fdfdf224"},
            )
        )
    records: list[dict[str, Any]] = []
    for url, status, headers in feeds:
        payload = request_url_json(url, headers=headers)
        for feature in payload.get("features") or []:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            centroid = geojson_centroid(feature.get("geometry"))
            location = None
            if centroid:
                location = f"approx {centroid['lat']:.5f}, {centroid['lng']:.5f}"
            outage_type = clean_text(props.get("outageType")) or status
            records.append(
                outage_record(
                    "vector",
                    "Vector",
                    outage_type.lower(),
                    location,
                    None,
                    outage_type,
                    None,
                    None,
                    url,
                    coordinates=centroid,
                    raw={"properties": props, "geometry_type": (feature.get("geometry") or {}).get("type")},
                )
            )
    return records


def fetch_wellington_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://www.welectricity.co.nz/outages/getalloutages"
    payload = request_url_json(url)
    records: list[dict[str, Any]] = []
    for item in payload.get("unplannedOutages") or []:
        status = clean_text(item.get("timeBasedStatus") or item.get("status") or "current") or "current"
        if not include_all and status.lower() != "current":
            continue
        records.append(
            outage_record(
                "wellington",
                "Wellington Electricity",
                status.lower(),
                item.get("suburbsText"),
                item.get("lastUpdatedCustomersAffected"),
                item.get("lastUpdatedComments"),
                item.get("lastUpdatedEta"),
                item.get("timeOfFault"),
                url,
                outage_id=item.get("id"),
                coordinates=item.get("location") if isinstance(item.get("location"), dict) else None,
                raw=item,
            )
        )
    for item in payload.get("plannedOutages") or []:
        if clean_text(item.get("status")) == "Cancelled":
            continue
        start = item.get("alternateStartDateTime") if item.get("useAlternateDate") else item.get("outageStartDateTime")
        end = item.get("alternateEndDateTime") if item.get("useAlternateDate") else item.get("outageEndDateTime")
        if not include_all and not is_active_window(start, end):
            continue
        records.append(
            outage_record(
                "wellington",
                "Wellington Electricity",
                clean_text(item.get("timeBasedStatus") or item.get("status") or "planned") or "planned",
                item.get("suburbsText"),
                item.get("customersAffected"),
                item.get("reasonForOutage"),
                end,
                start,
                url,
                outage_id=item.get("distributorEventNumber") or item.get("id"),
                coordinates=item.get("location") if isinstance(item.get("location"), dict) else None,
                raw=item,
            )
        )
    return records


def fetch_orion_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://www.oriongroup.co.nz/outages-and-support/outages/refresh-outages"
    payload = request_url_json(url)
    groups = [("CurrentOutages", "current")]
    if include_all:
        groups.append(("PlannedOutages", "planned"))
    records: list[dict[str, Any]] = []
    for key, status in groups:
        for item in payload.get(key) or []:
            if clean_text(item.get("JobStatus")) == "Cancelled":
                continue
            start = item.get("PlannedStart") if status == "planned" else item.get("TimeDown")
            end = first_value(item.get("PlannedEnd"), item.get("EstTimeUp"), item.get("TimeUp"))
            customers = item.get("MaxNumberOff") if status == "planned" else first_value(item.get("TotalNumberOff"), item.get("MaxNumberOff"))
            records.append(
                outage_record(
                    "orion",
                    "Orion",
                    status,
                    join_parts(item.get("Areas"), item.get("Streets")),
                    customers,
                    first_value(item.get("OutageCause"), item.get("PublicComments")),
                    end,
                    start,
                    url,
                    outage_id=item.get("IncidentRef") or item.get("Id"),
                    coordinates={"lat": item.get("Latitude"), "lng": item.get("Longitude")}
                    if item.get("Latitude") is not None and item.get("Longitude") is not None
                    else None,
                    raw=item,
                )
            )
    return records


def fetch_powerco_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://outages.powerco.co.nz/server/rest/services/Hosted/Outages/FeatureServer/1/query"
    payload = request_url_json(
        url,
        params={
            "f": "json",
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "orderByFields": "interruption_start_date DESC",
        },
    )
    records: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        attrs = feature.get("attributes") or {}
        status = "planned" if attrs.get("planned_outage") else "current"
        records.append(
            outage_record(
                "powerco",
                "Powerco",
                status,
                join_parts(attrs.get("suburb"), attrs.get("town"), attrs.get("feeder")),
                attrs.get("number_of_detail_records"),
                attrs.get("interruption_reason"),
                epoch_ms_to_iso(attrs.get("interruption_restore_date")),
                epoch_ms_to_iso(attrs.get("interruption_start_date")),
                url,
                outage_id=attrs.get("distributor_event_number") or attrs.get("objectid"),
                raw=attrs,
            )
        )
    return records


def fetch_aurora_outages(include_all: bool) -> list[dict[str, Any]]:
    feeds = [
        ("https://www.auroraenergy.co.nz/Umbraco/Api/Outage/currentCenterPoints", "current"),
    ]
    if include_all:
        feeds.append(("https://www.auroraenergy.co.nz/Umbraco/Api/Outage/plannedCenterPoints", "planned"))
    records: list[dict[str, Any]] = []
    for url, status in feeds:
        payload = request_url_json(url)
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            if clean_text(props.get("eventStatus")) == "Cancelled":
                continue
            customers = first_value(
                props.get("currentAffectedCustomers"),
                props.get("plannedAffectedCustomers"),
                props.get("totalFaultAffectedCustomers"),
                group_customers(props),
            )
            if customers == 0:
                customers = group_customers(props) or customers
            records.append(
                outage_record(
                    "aurora",
                    "Aurora Energy",
                    status,
                    join_parts(props.get("suburbsAffected"), props.get("town"), props.get("streetsAffected")),
                    customers,
                    props.get("eventCause"),
                    props.get("endDateTime"),
                    props.get("startDateTime"),
                    url,
                    outage_id=props.get("eventNumber"),
                    coordinates=geojson_centroid(feature.get("geometry")),
                    raw=props,
                )
            )
    return records


def fetch_wel_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://server.ourpower.co.nz/api/?FETCH_GROUPED_FAULTS"
    payload = request_url_json(
        url,
        method="POST",
        body={"application": "outages", "emit": True, "type": "FETCH_GROUPED_FAULTS"},
    )
    grouped = (payload.get("payload") or {}).get("groupedFaults") or []
    records: list[dict[str, Any]] = []
    for group in grouped:
        coordinates = None
        if group.get("lat") is not None and group.get("lng") is not None:
            coordinates = {"lat": group.get("lat"), "lng": group.get("lng")}
        for incident in group.get("incidents") or []:
            planned = incident.get("faultType") == 1
            start = incident.get("start")
            end = incident.get("end")
            if not include_all and planned and not is_active_window(start, end):
                continue
            status = "planned" if planned else "current"
            records.append(
                outage_record(
                    "wel",
                    "WEL Networks",
                    status,
                    join_parts(incident.get("suburb"), incident.get("street")) or (
                        f"approx {coordinates['lat']:.5f}, {coordinates['lng']:.5f}" if coordinates else None
                    ),
                    incident.get("propertiesAffected"),
                    incident.get("reason"),
                    end,
                    start,
                    url,
                    outage_id=incident.get("incidentReference"),
                    coordinates=coordinates,
                    raw=incident,
                )
            )
    return records


def fetch_unison_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://www.unison.co.nz/api/outages"
    payload = request_url_json(url)
    records: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        state = clean_text(item.get("outageState") or item.get("outageStatus") or item.get("outageType")) or "unknown"
        state_key = state.lower()
        if state_key in ("cancelled", "completed", "recent"):
            continue
        if not include_all and state_key not in ("current", "ongoing"):
            continue
        records.append(
            outage_record(
                "unison",
                "Unison",
                state_key,
                join_parts(item.get("networkRegion"), item.get("areaAffected")),
                item.get("customersOff"),
                item.get("interruptionReason"),
                item.get("finishTime"),
                item.get("startTime"),
                url,
                outage_id=item.get("outageID"),
                raw={k: v for k, v in item.items() if k != "outageWindows"},
            )
        )
    return records


def fetch_counties_outages(include_all: bool) -> list[dict[str, Any]]:
    unplanned_url = "https://api.integration.countiesenergy.co.nz/user/v1.0/outages"
    planned_url = "https://api.integration.countiesenergy.co.nz/user/v1.0/shutdowns"
    records: list[dict[str, Any]] = []
    unplanned = request_url_json(unplanned_url)
    for item in unplanned.get("service_orders") or []:
        records.append(
            outage_record(
                "counties",
                "Counties Energy",
                "current",
                item.get("address"),
                item.get("customersAffected"),
                first_value(item.get("description"), item.get("crewStatus")),
                first_value(item.get("etrDateTime"), item.get("estimatedRestoration"), item.get("etrTime")),
                item.get("serviceOrderDateTime"),
                unplanned_url,
                outage_id=item.get("no"),
                coordinates={"lat": item.get("lat"), "lng": item.get("lng")}
                if item.get("lat") is not None and item.get("lng") is not None
                else None,
                raw={k: v for k, v in item.items() if k != "hull"},
            )
        )
    planned = request_url_json(planned_url)
    for item in planned.get("planned_outages") or []:
        periods = item.get("shutdownPeriods") or []
        start = periods[0].get("start") if periods and isinstance(periods[0], dict) else item.get("shutdownDateTime")
        end = periods[-1].get("end") if periods and isinstance(periods[-1], dict) else None
        if not include_all and not is_active_window(start, end):
            continue
        records.append(
            outage_record(
                "counties",
                "Counties Energy",
                "planned",
                item.get("address"),
                item.get("affectedCustomers"),
                first_value(item.get("projectType"), item.get("latestInformation")),
                end,
                start,
                planned_url,
                outage_id=item.get("id"),
                coordinates={"lat": item.get("lat"), "lng": item.get("lng")}
                if item.get("lat") is not None and item.get("lng") is not None
                else None,
                raw={k: v for k, v in item.items() if k != "hull"},
            )
        )
    return records


def fetch_top_outages(include_all: bool) -> list[dict[str, Any]]:
    url = "https://outages.topenergy.co.nz/api/outages/regions"
    payload = request_url_json(url)
    records: list[dict[str, Any]] = []
    for item in payload.get("active") or []:
        records.append(
            outage_record(
                "top",
                "Top Energy",
                "current",
                item.get("circuitName") or item.get("name"),
                item.get("customersCurrentlyOff"),
                first_value(item.get("additionalInformation"), "Unplanned outage"),
                item.get("endDateTime"),
                item.get("startDateTime"),
                url,
                outage_id=item.get("name"),
                raw=item,
            )
        )
    for item in payload.get("planned") or []:
        if not include_all and not item.get("isActive"):
            continue
        records.append(
            outage_record(
                "top",
                "Top Energy",
                "planned",
                item.get("circuitName") or item.get("name"),
                item.get("customersCurrentlyOff"),
                first_value(item.get("additionalInformation"), "Planned outage"),
                item.get("endDateTime"),
                item.get("startDateTime"),
                url,
                outage_id=item.get("name"),
                raw=item,
            )
        )
    return records


OUTAGE_FETCHERS: dict[str, tuple[str, Callable[[bool], list[dict[str, Any]]]]] = {
    "vector": ("Vector", fetch_vector_outages),
    "wellington": ("Wellington Electricity", fetch_wellington_outages),
    "orion": ("Orion", fetch_orion_outages),
    "powerco": ("Powerco", fetch_powerco_outages),
    "aurora": ("Aurora Energy", fetch_aurora_outages),
    "wel": ("WEL Networks", fetch_wel_outages),
    "unison": ("Unison", fetch_unison_outages),
    "counties": ("Counties Energy", fetch_counties_outages),
    "top": ("Top Energy", fetch_top_outages),
}

OUTAGE_COMPANY_ALIASES = {
    "welectricity": "wellington",
    "wellington-electricity": "wellington",
    "wel-networks": "wel",
    "counties-energy": "counties",
    "top-energy": "top",
    "topenergy": "top",
}

OUTAGE_UNSUPPORTED = {
    "northpower": "Northpower renders outage data through Livewire snapshots and websocket/update calls; no clean stable public JSON endpoint was found.",
    "mainpower": "not investigated in this pass",
    "marlborough": "not investigated in this pass",
    "marlborough-lines": "not investigated in this pass",
    "network-tasman": "not investigated in this pass",
    "electra": "not investigated in this pass",
    "westpower": "not investigated in this pass",
    "network-waitaki": "not investigated in this pass",
}


def resolve_outage_company(raw: str) -> str:
    key = raw.strip().lower().replace("_", "-").replace(" ", "-")
    return OUTAGE_COMPANY_ALIASES.get(key, key)


def fetch_company_outages(company_key: str, include_all: bool) -> tuple[list[dict[str, Any]], str | None]:
    label, fetcher = OUTAGE_FETCHERS[company_key]
    try:
        return fetcher(include_all), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:180]
        return [], f"{label}: HTTP {e.code} {detail}".strip()
    except urllib.error.URLError as e:
        return [], f"{label}: network error {e.reason}"
    except json.JSONDecodeError as e:
        return [], f"{label}: invalid JSON ({e})"
    except TimeoutError as e:
        return [], f"{label}: timeout ({e})"
    except Exception as e:
        return [], f"{label}: {type(e).__name__}: {e}"


def record_matches_region(record: dict[str, Any], region: str) -> bool:
    needle = region.strip().lower()
    haystack = [
        record.get("company"),
        record.get("location"),
        record.get("cause"),
        record.get("outage_id"),
        json.dumps(record.get("raw") or {}, ensure_ascii=False),
    ]
    return any(needle in str(value).lower() for value in haystack if value)


def cmd_outages(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    errors: list[str] = []
    if args.company:
        company_key = resolve_outage_company(args.company)
        if company_key in OUTAGE_UNSUPPORTED:
            data = {
                "source": "NZ lines-company public outage feeds",
                "count": 0,
                "companies_queried": [],
                "region_filter": args.region,
                "include_scheduled": args.all,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "outages": [],
                "errors": [f"{args.company}: {OUTAGE_UNSUPPORTED[company_key]}"],
            }
            emit(data, args.json, render_outages)
            return
        if company_key not in OUTAGE_FETCHERS:
            valid = ", ".join(sorted(OUTAGE_FETCHERS))
            die(f"unknown outage company '{args.company}'. Supported companies: {valid}")
        company_keys = [company_key]
    else:
        company_keys = list(OUTAGE_FETCHERS)

    outages: list[dict[str, Any]] = []
    for company_key in company_keys:
        company_outages, error = fetch_company_outages(company_key, args.all)
        if error:
            errors.append(error)
        outages.extend(company_outages)

    if args.region:
        outages = [record for record in outages if record_matches_region(record, args.region)]

    outages.sort(key=lambda item: (item.get("company") or "", item.get("status") or "", item.get("outage_start_time") or ""))
    data = {
        "source": "NZ lines-company public outage feeds",
        "count": len(outages),
        "companies_queried": [OUTAGE_FETCHERS[key][0] for key in company_keys],
        "region_filter": args.region,
        "include_scheduled": args.all,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "outages": outages,
        "errors": errors,
    }
    emit(data, args.json, render_outages)


def http_probe(
    url: str,
    *,
    timeout: int = 15,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> dict[str, Any]:
    req_headers = {
        "User-Agent": nzfetch.DEFAULT_UA,
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-NZ,en;q=0.8",
        "Accept-Encoding": "identity",
    }
    if headers:
        req_headers.update(headers)
    request_obj = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout) as response:
            body = response.read(6000)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            final_url = response.geturl()
    except urllib.error.HTTPError as e:
        body = e.read(6000)
        status = e.code
        content_type = e.headers.get("Content-Type", "")
        final_url = e.geturl()
    except urllib.error.URLError as e:
        return {"url": url, "ok": False, "error": f"network error: {e.reason}"}
    except TimeoutError as e:
        return {"url": url, "ok": False, "error": f"timeout: {e}"}

    text = body.decode("utf-8", "replace")
    lower = text.lower()
    signals = []
    if "where's the viz" in lower or "could not be found" in lower or "removed or renamed" in lower:
        signals.append("tableau_removed_or_renamed")
    if "awswaf" in lower or "captcha" in lower:
        signals.append("bot_challenge")
    return {
        "url": url,
        "final_url": final_url,
        "ok": 200 <= status < 300,
        "status_code": status,
        "content_type": content_type,
        "signals": signals,
    }


def energy_margin_checks(timeout: int) -> list[dict[str, Any]]:
    viz_location = (
        "https://public.tableau.com/views/Energymargin/Energymargin"
        "?%3AshowVizHome=no&%3Aembed=y&%3Adisplay_count=n&%3Aorigin=viz_share_link&%3Aredirect=auth"
    )
    return [
        http_probe(EA_ENERGY_MARGIN_DASHBOARD, timeout=timeout),
        http_probe(EA_ENERGY_MARGIN_ARTICLE, timeout=timeout),
        http_probe(TABLEAU_ENERGY_MARGIN_VIEW, timeout=timeout),
        http_probe(TABLEAU_ENERGY_MARGIN_PROFILE_API, timeout=timeout),
        http_probe(
            TABLEAU_ENERGY_MARGIN_VIZQL,
            timeout=timeout,
            method="POST",
            data=b"",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": TABLEAU_ENERGY_MARGIN_VIEW,
                "Tableau-Viz-Location": viz_location,
                "Tableau-Viz-Path": "/w/Energymargin#0",
            },
        ),
    ]


def cmd_energy_margin(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    from_date = parse_date(args.from_date).isoformat() if args.from_date else None
    to_date = parse_date(args.to_date).isoformat() if args.to_date else None
    if from_date and to_date and to_date < from_date:
        die("--to must be on or after --from")
    company_filter = None
    if args.company:
        key = args.company.strip().lower()
        company_filter = ENERGY_MARGIN_COMPANIES.get(key)
        if not company_filter:
            valid = ", ".join(sorted(ENERGY_MARGIN_COMPANIES))
            die(f"unknown energy-margin company '{args.company}'. Supported companies: {valid}")

    checks = energy_margin_checks(args.timeout)
    tableau_view = next((item for item in checks if item.get("url") == TABLEAU_ENERGY_MARGIN_VIEW), {})
    profile_api = next((item for item in checks if item.get("url") == TABLEAU_ENERGY_MARGIN_PROFILE_API), {})
    vizql = next((item for item in checks if item.get("url") == TABLEAU_ENERGY_MARGIN_VIZQL), {})
    removed = "tableau_removed_or_renamed" in (tableau_view.get("signals") or [])
    unavailable = removed or profile_api.get("status_code") == 404 or vizql.get("status_code") == 404

    status = "source_unavailable" if unavailable else "source_probe_inconclusive"
    reason = (
        "The official Authority-linked Tableau workbook/profile and VizQL session endpoints return 404. "
        "No official machine-readable per-company energy-margin rows are available from this public surface."
        if unavailable
        else "The official Tableau workbook did not yield machine-readable per-company rows from this probe."
    )
    data = {
        "source": "Electricity Authority gentailer energy margin dashboard/article",
        "source_url": EA_ENERGY_MARGIN_DASHBOARD,
        "article_url": EA_ENERGY_MARGIN_ARTICLE,
        "tableau_url": "https://public.tableau.com/app/profile/electricity.authority/viz/Energymargin/Energymargin",
        "status": status,
        "reason": reason,
        "company_filter": company_filter,
        "from": from_date,
        "to": to_date,
        "count": 0,
        "energy_margins": [],
        "source_checks": checks,
        "caveats": [
            "This command does not reconstruct margins from prices and generation volumes.",
            "This command does not ship copied chart values or third-party preserved data.",
            "When the Authority publishes an official CSV/API feed, wire that feed here before returning rows.",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    emit(data, args.json, render_energy_margin)


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


def number(value: Any, decimals: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{decimals}f}"
    return str(value)


def dg_filter_label(data: dict[str, Any]) -> str:
    filters = data.get("filters") or {}
    return (
        f"fuel={filters.get('fuel')} market_segment={filters.get('market_segment')} "
        f"capacity={filters.get('capacity')} region_type={filters.get('region_type')}"
    )


def render_dg_rows(rows: list[dict[str, Any]], limit: int = 24) -> list[str]:
    lines = []
    for item in rows[:limit]:
        lines.append(
            f"{item.get('month_end')}  {str(item.get('region_id') or '').ljust(6)} "
            f"{str(item.get('region_name') or '').ljust(22)[:22]} "
            f"ICPs {number(item.get('icp_count'), 0).rjust(8)}  "
            f"capacity {number(item.get('total_capacity_mw')).rjust(10)} MW  "
            f"new {number(item.get('new_installation_count'), 0).rjust(6)}"
        )
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more rows; use --json for full output")
    return lines


def render_dg_trends(data: dict[str, Any]) -> str:
    rows = data.get("trends") or []
    summary = data.get("summary") or {}
    lines = [
        f"EMI distributed generation trends: {data.get('count')} row(s) ({data.get('elapsed_ms')} ms)",
        dg_filter_label(data),
        f"EMI run: {data.get('emi_run_at') or '-'}",
        f"Range: {summary.get('first_month_end') or '-'} to {summary.get('latest_month_end') or '-'}",
        "",
    ]
    lines.extend(render_dg_rows(rows))
    lines.append("")
    lines.append("Caveat: market segments are not mutually exclusive; Solar+Batteries categories changed in Nov 2023.")
    return "\n".join(lines).rstrip()


def render_dg_latest(data: dict[str, Any]) -> str:
    rows = data.get("latest") or []
    lines = [
        f"EMI distributed generation latest month: {data.get('latest_month_end') or '-'} ({data.get('elapsed_ms')} ms)",
        dg_filter_label(data),
        f"EMI run: {data.get('emi_run_at') or '-'}",
        "",
    ]
    lines.extend(render_dg_rows(rows))
    return "\n".join(lines).rstrip()


def render_dg_summary(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    yearly = data.get("yearly") or []
    lines = [
        f"EMI distributed generation summary: {data.get('count')} row(s) ({data.get('elapsed_ms')} ms)",
        dg_filter_label(data),
        f"Range: {summary.get('first_month_end') or '-'} to {summary.get('latest_month_end') or '-'}",
        f"Latest ICPs: {number(summary.get('latest_icp_count'), 0)}  "
        f"capacity: {number(summary.get('latest_total_capacity_mw'))} MW  "
        f"new installations in rows: {number(summary.get('total_new_installation_count'), 0)}",
    ]
    if yearly:
        lines.append("")
        lines.append("Yearly")
        for item in yearly[:30]:
            lines.append(
                f"{item.get('year')} {str(item.get('region_id') or '').ljust(6)} "
                f"ICPs {number(item.get('end_icp_count'), 0).rjust(8)}  "
                f"change {number(item.get('icp_count_change'), 0).rjust(7)}  "
                f"capacity {number(item.get('end_total_capacity_mw')).rjust(10)} MW  "
                f"new {number(item.get('new_installation_count'), 0).rjust(7)}"
            )
        if len(yearly) > 30:
            lines.append(f"... {len(yearly) - 30} more rows; use --json for full output")
    lines.append("")
    lines.append("Caveat: market segments are not mutually exclusive; Solar+Batteries categories changed in Nov 2023.")
    return "\n".join(lines).rstrip()


def render_outages(data: dict[str, Any]) -> str:
    outages = data.get("outages") or []
    mode = "current, scheduled, and recent" if data.get("include_scheduled") else "current"
    if not outages:
        lines = [
            f"No {mode} outages returned from {len(data.get('companies_queried') or [])} supported company feed(s)"
            f" ({data.get('elapsed_ms')} ms)."
        ]
    else:
        lines = [
            f"NZ lines-company outages: {len(outages)} {mode} record(s) from "
            f"{len(data.get('companies_queried') or [])} feed(s) ({data.get('elapsed_ms')} ms)"
        ]
        if data.get("region_filter"):
            lines.append(f"Region filter: {data.get('region_filter')}")
        lines.append("")
        for item in outages:
            parts = [
                item.get("company") or "Unknown company",
                item.get("status") or "unknown",
                item.get("location") or "Unknown location",
            ]
            customers = item.get("customers_affected")
            if customers is not None:
                parts.append(f"{customers} customers")
            if item.get("cause"):
                parts.append(f"cause {item.get('cause')}")
            if item.get("outage_start_time"):
                parts.append(f"start {item.get('outage_start_time')}")
            if item.get("estimated_restoration_time"):
                parts.append(f"ETR {item.get('estimated_restoration_time')}")
            if item.get("outage_id"):
                parts.append(f"id {item.get('outage_id')}")
            lines.append(" | ".join(str(part) for part in parts if part))
    if data.get("errors"):
        lines.append("")
        lines.append("Warnings:")
        lines.extend(str(error) for error in data["errors"])
    return "\n".join(lines).rstrip()


def render_energy_margin(data: dict[str, Any]) -> str:
    rows = data.get("energy_margins") or []
    lines = [
        f"EA gentailer energy margins: {data.get('status')} ({data.get('elapsed_ms')} ms)",
        f"Source: {data.get('source_url')}",
    ]
    if data.get("company_filter"):
        lines.append(f"Company filter: {data.get('company_filter')}")
    if rows:
        lines.append("")
        for item in rows:
            lines.append(
                f"{item.get('period') or '-'}  {item.get('company') or '-'}  "
                f"{number(item.get('energy_margin_million_nzd'))} $m"
            )
    else:
        lines.append(data.get("reason") or "No official energy-margin rows returned.")
        lines.append("")
        lines.append("Checked official surfaces:")
        for check in data.get("source_checks") or []:
            status = check.get("status_code") if check.get("status_code") is not None else check.get("error")
            signals = ", ".join(check.get("signals") or [])
            suffix = f" [{signals}]" if signals else ""
            lines.append(f"- {status} {check.get('url')}{suffix}")
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


def add_dg_filter_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--fuel", default="solar_all", help="GUEHMT FuelType value or alias; default solar_all")
    sp.add_argument("--market-segment", default="All", help="All, Res, SME, Com, or Ind; default All")
    sp.add_argument("--capacity", default="All_Total", help="All_Total, Small, or Large; default All_Total")
    sp.add_argument("--region-type", default="NZ", help="NZ, ZONE, ISLAND_1, MAIN_CENTRE, REG_COUNCIL, NWKP, or NSP_ROOT")


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

    sp = sub.add_parser("dg-trends", help="EMI GUEHMT distributed-generation trends by month")
    add_dg_filter_args(sp)
    sp.add_argument("--from", dest="from_date", help="start date YYYY-MM-DD")
    sp.add_argument("--to", dest="to_date", help="end date YYYY-MM-DD")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_dg_trends)

    sp = sub.add_parser("dg-latest", help="latest EMI GUEHMT distributed-generation records")
    add_dg_filter_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_dg_latest)

    sp = sub.add_parser("dg-summary", help="summarise EMI GUEHMT distributed-generation records")
    add_dg_filter_args(sp)
    sp.add_argument("--from", dest="from_date", help="start date YYYY-MM-DD")
    sp.add_argument("--to", dest="to_date", help="end date YYYY-MM-DD")
    sp.add_argument("--yearly", action="store_true", help="include year-by-year summaries")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_dg_summary)

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

    sp = sub.add_parser("outages", help="current public outage records from supported NZ lines companies")
    sp.add_argument("--company", help="supported company key, e.g. vector, wellington, powerco, aurora, wel")
    sp.add_argument("--region", help="case-insensitive suburb, town, region, or street text filter")
    sp.add_argument("--all", action="store_true", help="include planned, scheduled, or recent outage records where feeds expose them")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_outages)

    sp = sub.add_parser("energy-margin", help="probe official EA gentailer energy-margin source availability")
    sp.add_argument("--company", help="Contact, Genesis, Manawa, Mercury, Meridian, or Nova")
    sp.add_argument("--from", dest="from_date", help="requested period start date YYYY-MM-DD; returned as metadata until an official data feed is available")
    sp.add_argument("--to", dest="to_date", help="requested period end date YYYY-MM-DD; returned as metadata until an official data feed is available")
    sp.add_argument("--timeout", type=positive_int, default=15, help="per-source probe timeout in seconds; default 15")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_energy_margin)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
