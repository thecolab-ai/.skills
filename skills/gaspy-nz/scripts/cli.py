#!/usr/bin/env python3
"""Gaspy NZ lightweight public stats CLI.

Self-contained stdlib wrapper around Gaspy's public website stats feed.
No login, price reporting, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE_FEED = "https://gaspy-datamine-stats.firebaseio.com/.json"
UA = os.environ.get(
    "GASPY_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

FUEL_TYPES: dict[str, dict[str, str | None]] = {
    "1": {"fuel": "91", "label": "Unleaded 91", "unit": "c/L", "datamine_key": "91"},
    "2": {"fuel": "diesel", "label": "Diesel", "unit": "c/L", "datamine_key": "Diesel"},
    "3": {"fuel": "95", "label": "Unleaded 95", "unit": "c/L", "datamine_key": "95"},
    "5": {"fuel": "98", "label": "Unleaded 98", "unit": "c/L", "datamine_key": "98"},
    "17": {"fuel": "lpg", "label": "LPG", "unit": "c/L", "datamine_key": "LPG"},
    "18": {"fuel": "100", "label": "100 Octane", "unit": "c/L", "datamine_key": "100"},
    # The public feed includes this numeric type but the website does not label it.
    "21": {"fuel": "type-21", "label": "Fuel type 21", "unit": "c/unit", "datamine_key": None},
}
FUEL_ORDER = ["1", "2", "3", "5", "18", "17", "21"]
FUEL_ALIASES = {info["fuel"]: fuel_id for fuel_id, info in FUEL_TYPES.items()}


def die(message: str, code: int = 1) -> None:
    print(f"gaspy-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(url: str = BASE_FEED, timeout: int = 20) -> Any:
    headers = {
        "Accept": "application/json",
        "Referer": "https://www.gaspy.nz/stats.html",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} from {url}: {raw[:300]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def timestamp_ms_to_iso(value: Any) -> str | None:
    try:
        millis = int(value)
    except Exception:
        return None
    return dt.datetime.fromtimestamp(millis / 1000, tz=dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def number(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def fmt_price_cents(value: Any, unit: str = "c/L") -> str:
    cents = number(value)
    if cents is None:
        return "-"
    if unit == "c/L":
        return f"${cents / 100:.3f}/L"
    return f"{cents:.1f} {unit}"


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "-"


def fuel_id_from_arg(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    if key in FUEL_ALIASES:
        return str(FUEL_ALIASES[key])
    if key in FUEL_TYPES:
        return key
    die(f"unknown fuel '{raw}'. Expected one of: {', '.join(sorted(FUEL_ALIASES))}")


def metadata_from(feed: dict[str, Any]) -> dict[str, Any]:
    datamine = feed.get("datamine") or {}
    gaspy = feed.get("gaspy") or {}
    return {
        "source": BASE_FEED,
        "fetched_at": now_utc(),
        "database_updated_text": datamine.get("Updated"),
        "timestamp": gaspy.get("timestamp"),
        "timestamp_iso": timestamp_ms_to_iso(gaspy.get("timestamp")),
        "station_count": datamine.get("StationCount"),
        "brand_count": datamine.get("BrandCount"),
        "total_gas_spies": gaspy.get("usercount"),
        "price_confirmations_last_7_days": datamine.get("PriceConfirmationsInLast7Days"),
    }


def fuel_type_rows(feed: dict[str, Any]) -> list[dict[str, Any]]:
    national = ((feed.get("gaspy") or {}).get("national") or {})
    rows = []
    ordered_ids = [fuel_id for fuel_id in FUEL_ORDER if fuel_id in national]
    ordered_ids.extend(sorted(fuel_id for fuel_id in national if fuel_id not in ordered_ids))
    for fuel_id in ordered_ids:
        info = FUEL_TYPES.get(str(fuel_id), {})
        rows.append(
            {
                "fuel_type_id": str(fuel_id),
                "fuel": info.get("fuel") or f"type-{fuel_id}",
                "label": info.get("label") or f"Fuel type {fuel_id}",
                "unit": info.get("unit") or "c/unit",
                "has_28_day_change": bool(info.get("datamine_key")),
            }
        )
    return rows


def price_rows(feed: dict[str, Any], fuel_id: str | None = None) -> list[dict[str, Any]]:
    datamine = feed.get("datamine") or {}
    averages = datamine.get("Averages") or {}
    national = ((feed.get("gaspy") or {}).get("national") or {})
    rows = []
    ordered_ids = [fuel_id for fuel_id in FUEL_ORDER if fuel_id in national]
    ordered_ids.extend(sorted(fuel_id for fuel_id in national if fuel_id not in ordered_ids))
    for current_id in ordered_ids:
        if fuel_id and current_id != fuel_id:
            continue
        info = FUEL_TYPES.get(str(current_id), {})
        stats = national.get(current_id) or {}
        datamine_key = info.get("datamine_key")
        change = averages.get(datamine_key) if datamine_key else None
        if not isinstance(change, dict):
            change = {}
        rows.append(
            {
                "fuel_type_id": str(current_id),
                "fuel": info.get("fuel") or f"type-{current_id}",
                "label": info.get("label") or f"Fuel type {current_id}",
                "unit": info.get("unit") or "c/unit",
                "average": stats.get("average"),
                "minimum": stats.get("minimum"),
                "maximum": stats.get("maximum"),
                "standard_deviation": stats.get("std"),
                "station_count": stats.get("count"),
                "change_28d_cents": change.get("28DayChange"),
                "change_28d_percent": change.get("28DayPercent"),
            }
        )
    return rows


def cheapest_91_rows(feed: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = []
    top = (feed.get("datamine") or {}).get("Top91") or []
    for item in top[: max(1, min(limit, 5))]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "fuel": "91",
                "label": "Unleaded 91",
                "station_name": item.get("StationName"),
                "region": item.get("Region"),
                "price": item.get("Price"),
                "unit": "c/L",
            }
        )
    return rows


def load_view() -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    feed = request_json()
    if not isinstance(feed, dict):
        die("unexpected feed shape")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return feed, elapsed_ms


def cmd_summary(args: argparse.Namespace) -> None:
    feed, elapsed_ms = load_view()
    data = {
        "metadata": metadata_from(feed),
        "elapsed_ms": elapsed_ms,
        "prices": price_rows(feed),
        "cheapest_91": cheapest_91_rows(feed, 5),
    }
    emit_summary(data, args.json)


def cmd_prices(args: argparse.Namespace) -> None:
    feed, elapsed_ms = load_view()
    fuel_id = fuel_id_from_arg(args.fuel)
    rows = price_rows(feed, fuel_id)
    data = {
        "metadata": metadata_from(feed),
        "elapsed_ms": elapsed_ms,
        "filters": {"fuel": args.fuel},
        "count": len(rows),
        "prices": rows,
    }
    emit_prices(data, args.json)


def cmd_cheapest(args: argparse.Namespace) -> None:
    fuel_id = fuel_id_from_arg(args.fuel)
    if fuel_id and fuel_id != "1":
        die("the public Gaspy stats feed only exposes top cheapest stations for 91")
    feed, elapsed_ms = load_view()
    rows = cheapest_91_rows(feed, args.limit)
    data = {
        "metadata": metadata_from(feed),
        "elapsed_ms": elapsed_ms,
        "filters": {"fuel": "91", "limit": max(1, min(args.limit, 5))},
        "count": len(rows),
        "stations": rows,
    }
    emit_cheapest(data, args.json)


def cmd_metadata(args: argparse.Namespace) -> None:
    feed, elapsed_ms = load_view()
    data = metadata_from(feed)
    data["elapsed_ms"] = elapsed_ms
    emit_metadata(data, args.json)


def cmd_fuel_types(args: argparse.Namespace) -> None:
    feed, elapsed_ms = load_view()
    rows = fuel_type_rows(feed)
    data = {
        "metadata": metadata_from(feed),
        "elapsed_ms": elapsed_ms,
        "count": len(rows),
        "fuel_types": rows,
    }
    emit_fuel_types(data, args.json)


def emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def print_header(data: dict[str, Any]) -> None:
    meta = data.get("metadata") or data
    updated = meta.get("database_updated_text") or meta.get("timestamp_iso") or "unknown"
    print(f"Gaspy NZ public stats feed ({updated})")
    print(f"Source: {meta.get('source', BASE_FEED)}")
    print()


def emit_summary(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        emit_json(data)
        return
    print_header(data)
    meta = data.get("metadata") or {}
    print(f"Stations: {fmt_int(meta.get('station_count'))} | Brands: {fmt_int(meta.get('brand_count'))} | Gas Spies: {fmt_int(meta.get('total_gas_spies'))}")
    print(f"Confirmations last 7 days: {fmt_int(meta.get('price_confirmations_last_7_days'))}")
    print()
    print("National observed prices:")
    for row in data.get("prices") or []:
        unit = str(row.get("unit") or "c/L")
        change = row.get("change_28d_cents")
        change_text = f"; 28d {change:+.2f}c" if isinstance(change, (int, float)) else ""
        print(f"  {row.get('label')}: {fmt_price_cents(row.get('average'), unit)} avg ({fmt_int(row.get('station_count'))} stations{change_text})")
    print()
    print("Top cheapest 91:")
    for row in data.get("cheapest_91") or []:
        print(f"  {row.get('station_name')} - {row.get('region') or 'N/A'} - {fmt_price_cents(row.get('price'), 'c/L')}")


def emit_prices(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        emit_json(data)
        return
    print_header(data)
    for row in data.get("prices") or []:
        unit = str(row.get("unit") or "c/L")
        print(f"{row.get('label')} ({row.get('fuel')}): {fmt_price_cents(row.get('average'), unit)} avg")
        print(f"  min {fmt_price_cents(row.get('minimum'), unit)} | max {fmt_price_cents(row.get('maximum'), unit)} | stations {fmt_int(row.get('station_count'))}")
        if row.get("change_28d_cents") is not None:
            print(f"  28 day change: {row.get('change_28d_cents'):+.2f}c / {row.get('change_28d_percent'):+.2f}%")


def emit_cheapest(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        emit_json(data)
        return
    print_header(data)
    print("Top cheapest stations for 91:")
    for row in data.get("stations") or []:
        print(f"  {row.get('station_name')} - {row.get('region') or 'N/A'} - {fmt_price_cents(row.get('price'), 'c/L')}")


def emit_metadata(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        emit_json(data)
        return
    print("Gaspy NZ public stats metadata")
    print(f"Database updated: {data.get('database_updated_text') or data.get('timestamp_iso') or 'unknown'}")
    print(f"Stations: {fmt_int(data.get('station_count'))}")
    print(f"Brands: {fmt_int(data.get('brand_count'))}")
    print(f"Gas Spies: {fmt_int(data.get('total_gas_spies'))}")
    print(f"Confirmations last 7 days: {fmt_int(data.get('price_confirmations_last_7_days'))}")
    print(f"Source: {data.get('source')}")


def emit_fuel_types(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        emit_json(data)
        return
    print_header(data)
    print("Observed fuel types:")
    for row in data.get("fuel_types") or []:
        suffix = " with 28d change" if row.get("has_28_day_change") else ""
        print(f"  {row.get('fuel'):>7}  id {row.get('fuel_type_id'):>2}  {row.get('label')} ({row.get('unit')}){suffix}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Gaspy NZ public crowd-sourced fuel stats CLI (no login required).")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("summary", help="show national price stats, feed metadata, and top cheapest 91")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("prices", help="show national observed price stats by fuel")
    sp.add_argument("--fuel", choices=sorted(FUEL_ALIASES), help="filter by fuel")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_prices)

    sp = sub.add_parser("cheapest", help="show public top cheapest stations for 91")
    sp.add_argument("--fuel", choices=["91"], default="91")
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cheapest)

    sp = sub.add_parser("metadata", help="show public feed metadata and activity counts")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_metadata)

    sp = sub.add_parser("fuel-types", help="list fuel type ids observed in the public feed")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_fuel_types)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
