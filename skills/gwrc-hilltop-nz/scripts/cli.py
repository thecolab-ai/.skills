#!/usr/bin/env python3
"""Query Greater Wellington Regional Council Hilltop environmental time series.

Rainfall gauges and river/stream levels and flows through the public Hilltop
REST endpoint. Read-only, no authentication. Timestamps are NZ local time as
published by the server. The base URL is parameterisable so the same Hilltop
query pattern works against other regional councils' servers.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

DEFAULT_BASE = "https://hilltop.gw.govt.nz/data.hts"
SOURCE_NAME = "Greater Wellington Regional Council Hilltop server"
RAINFALL_COLLECTION = "Rainfall"
RIVER_COLLECTION = "River and Stream Levels"
INVALID_INPUT_MARKERS = ("unknown", "not found", "invalid", "no such")


def die(message: str, code: int = 1) -> None:
    print(f"gwrc-hilltop-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def hilltop_url(base: str, request: str, **params: str | None) -> str:
    query = {"Service": "Hilltop", "Request": request}
    query.update({k: v for k, v in params.items() if v is not None})
    # Hilltop does not decode "+" as a space in every request type; use %20.
    return base + "?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)


def fetch_root(url: str, base: str) -> ET.Element:
    host = urllib.parse.urlparse(base).hostname
    if not host:
        die(f"invalid base URL: {base!r}", 2)
    try:
        text = nzfetch.fetch_text(url, timeout=45, accept="application/xml,text/xml,*/*", allowed_hosts=[host])
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        die(f"source schema failure: Hilltop response was not valid XML: {exc}", 6)
    error = root.findtext("Error")
    if error:
        message = error.strip()
        low = message.lower()
        code = 2 if any(marker in low for marker in INVALID_INPUT_MARKERS) else 5
        die(f"Hilltop error: {message}", code)
    return root


def parse_site_list(root: ET.Element) -> list[dict[str, Any]]:
    sites = []
    for node in root.findall("Site"):
        latitude = node.findtext("Latitude")
        longitude = node.findtext("Longitude")
        sites.append(
            {
                "name": node.get("Name"),
                "latitude": float(latitude) if latitude else None,
                "longitude": float(longitude) if longitude else None,
            }
        )
    return [s for s in sites if s["name"]]


def parse_measurement_list(root: ET.Element) -> list[dict[str, Any]]:
    rows = []
    for source in root.findall("DataSource"):
        for measurement in source.findall("Measurement"):
            rows.append(
                {
                    "data_source": source.get("Name"),
                    "measurement": measurement.get("Name"),
                    "request_as": measurement.findtext("RequestAs"),
                    "units": measurement.findtext("Units"),
                    "from": source.findtext("From"),
                    "to": source.findtext("To"),
                }
            )
    return rows


def parse_time_series(root: ET.Element) -> list[dict[str, Any]]:
    """Parse GetData responses into one row per site/data-source block."""
    blocks = []
    for measurement in root.findall("Measurement"):
        source = measurement.find("DataSource")
        item = source.find("ItemInfo") if source is not None else None
        points = []
        data = measurement.find("Data")
        for entry in data.findall("E") if data is not None else []:
            when = entry.findtext("T")
            raw = entry.findtext("I1")
            if when is None or raw is None:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            points.append({"time": when, "value": value})
        blocks.append(
            {
                "site": measurement.get("SiteName"),
                "data_source": source.get("Name") if source is not None else None,
                "item_name": item.findtext("ItemName") if item is not None else None,
                "units": item.findtext("Units") if item is not None else None,
                "points": points,
            }
        )
    return blocks


def parse_collections(root: ET.Element) -> list[str]:
    names = [node.get("Name") for node in root.findall("Collection")]
    return sorted({name for name in names if name})


def summarise_block(block: dict[str, Any]) -> dict[str, Any] | None:
    """Latest value plus min/max/trend across the fetched window."""
    points = block["points"]
    if not points:
        return None
    values = [p["value"] for p in points]
    low, high = min(values), max(values)
    latest = points[-1]
    reference = points[-4] if len(points) >= 4 else points[0]
    delta = latest["value"] - reference["value"]
    threshold = max((high - low) * 0.05, 1e-9)
    if delta > threshold:
        trend = "rising"
    elif delta < -threshold:
        trend = "falling"
    else:
        trend = "steady"
    return {
        "site": block["site"],
        "measurement": block["item_name"],
        "units": block["units"],
        "latest_value": latest["value"],
        "latest_time": latest["time"],
        "window_min": low,
        "window_max": high,
        "trend": trend,
        "change_from_reference": round(delta, 4),
        "reference_time": reference["time"],
    }


def is_backup(block: dict[str, Any]) -> bool:
    site = (block["site"] or "").lower()
    source = (block["data_source"] or "").lower()
    return "backup" in site or "backup" in source


def freshness_cutoff(times: list[str], hours: int) -> str | None:
    """A cutoff ISO timestamp: the freshest observation minus the window plus slack.

    Hilltop returns whatever a gauge last logged, so decommissioned sites answer a
    'last 24 hours' query with years-old totals. Timestamps are naive ISO strings
    in one timezone, so lexicographic comparison is safe.
    """
    if not times:
        return None
    freshest = max(times)
    try:
        anchor = datetime.fromisoformat(freshest)
    except ValueError:
        return None
    return (anchor - timedelta(hours=hours + 6)).isoformat()


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_collections(args: argparse.Namespace) -> None:
    url = hilltop_url(args.base_url, "CollectionList")
    names = parse_collections(fetch_root(url, args.base_url))
    payload = {"kind": "collections", "source": SOURCE_NAME, "source_url": url, "collections": names}
    emit(payload, args.json, [f"Hilltop collections: {len(names)}", *[f"- {n}" for n in names]])


def cmd_sites(args: argparse.Namespace) -> None:
    url = hilltop_url(args.base_url, "SiteList", Location="LatLong", Measurement=args.measurement)
    sites = parse_site_list(fetch_root(url, args.base_url))
    if args.search:
        needle = args.search.casefold()
        sites = [s for s in sites if needle in s["name"].casefold()]
    total = len(sites)
    if args.limit:
        sites = sites[: args.limit]
    payload = {
        "kind": "sites",
        "source": SOURCE_NAME,
        "source_url": url,
        "measurement_filter": args.measurement,
        "search": args.search,
        "total_matches": total,
        "sites": sites,
    }
    lines = [f"Hilltop sites: {len(sites)} shown of {total}"]
    for s in sites:
        where = f" ({s['latitude']}, {s['longitude']})" if s["latitude"] is not None else ""
        lines.append(f"- {s['name']}{where}")
    emit(payload, args.json, lines)


def cmd_measurements(args: argparse.Namespace) -> None:
    url = hilltop_url(args.base_url, "MeasurementList", Site=args.site)
    rows = parse_measurement_list(fetch_root(url, args.base_url))
    if not rows:
        die(f"no measurements found for site {args.site!r}; check the exact name with the sites command", 2)
    payload = {"kind": "measurements", "source": SOURCE_NAME, "source_url": url, "site": args.site, "measurements": rows}
    lines = [f"Measurements at {args.site}: {len(rows)}"]
    for r in rows:
        units = f" [{r['units']}]" if r["units"] else ""
        lines.append(f"- {r['measurement']}{units} ({r['data_source']}, {r['from']} → {r['to']})")
    emit(payload, args.json, lines)


def cmd_latest(args: argparse.Namespace) -> None:
    url = hilltop_url(
        args.base_url,
        "GetData",
        Site=args.site,
        Measurement=args.measurement,
        TimeInterval=f"PT{args.window_hours}H",
    )
    blocks = [b for b in parse_time_series(fetch_root(url, args.base_url)) if b["points"]]
    if not blocks:
        die(
            f"no observations for {args.measurement!r} at {args.site!r} in the last {args.window_hours}h; "
            "gauges upload every 2-3 hours, so try a wider --window-hours or check names with sites/measurements",
            2,
        )
    block = blocks[0]
    latest = block["points"][-1]
    payload = {
        "kind": "latest",
        "source": SOURCE_NAME,
        "source_url": url,
        "site": block["site"],
        "measurement": block["item_name"] or args.measurement,
        "units": block["units"],
        "window_hours": args.window_hours,
        "observations_in_window": len(block["points"]),
        "latest_value": latest["value"],
        "latest_time": latest["time"],
        "timezone": "NZ local time as published by Hilltop",
    }
    emit(
        payload,
        args.json,
        [
            f"{block['site']} — {payload['measurement']}: {latest['value']} {block['units'] or ''}".rstrip()
            + f" at {latest['time']} (NZ local time, {len(block['points'])} observations in {args.window_hours}h)"
        ],
    )


def cmd_rainfall(args: argparse.Namespace) -> None:
    url = hilltop_url(
        args.base_url,
        "GetData",
        Collection=RAINFALL_COLLECTION,
        Method="Total",
        Interval=f"{args.hours} hours",
        TimeInterval=f"PT{args.hours}H",
    )
    blocks = parse_time_series(fetch_root(url, args.base_url))
    rows = []
    for block in blocks:
        if is_backup(block) or not block["points"] or block["item_name"] != "Rainfall":
            continue
        rows.append(
            {
                "site": block["site"],
                "total_mm": block["points"][-1]["value"],
                "units": block["units"] or "mm",
                "to_time": block["points"][-1]["time"],
            }
        )
    cutoff = freshness_cutoff([r["to_time"] for r in rows], args.hours)
    stale = [r for r in rows if cutoff and r["to_time"] < cutoff]
    rows = [r for r in rows if not (cutoff and r["to_time"] < cutoff)]
    if args.search:
        needle = args.search.casefold()
        rows = [r for r in rows if needle in (r["site"] or "").casefold()]
    rows.sort(key=lambda r: r["total_mm"], reverse=True)
    total = len(rows)
    if args.limit:
        rows = rows[: args.limit]
    payload = {
        "kind": "rainfall",
        "source": SOURCE_NAME,
        "source_url": url,
        "hours": args.hours,
        "search": args.search,
        "total_sites": total,
        "stale_gauges_excluded": len(stale),
        "timezone": "NZ local time as published by Hilltop",
        "gauges": rows,
    }
    lines = [f"Rainfall totals, last {args.hours}h ({len(rows)} shown of {total} gauges, wettest first):"]
    for r in rows:
        lines.append(f"- {r['site']}: {r['total_mm']} {r['units']} (to {r['to_time']})")
    emit(payload, args.json, lines)


def cmd_rivers(args: argparse.Namespace) -> None:
    url = hilltop_url(
        args.base_url,
        "GetData",
        Collection=RIVER_COLLECTION,
        Method="Average",
        Interval="1 hour",
        TimeInterval=f"PT{args.hours}H",
    )
    blocks = parse_time_series(fetch_root(url, args.base_url))
    # Keep only the primary Stage/Flow items — the collection also carries
    # temperature, dissolved oxygen, turbidity, compliance and secondary sensors.
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for block in blocks:
        if is_backup(block) or block["item_name"] not in ("Stage", "Flow"):
            continue
        summary = summarise_block(block)
        if not summary:
            continue
        key = (summary["site"] or "", summary["measurement"])
        current = best.get(key)
        if current is None or summary["latest_time"] > current["latest_time"]:
            best[key] = summary
    rows = list(best.values())
    cutoff = freshness_cutoff([r["latest_time"] for r in rows], args.hours)
    stale = [r for r in rows if cutoff and r["latest_time"] < cutoff]
    rows = [r for r in rows if not (cutoff and r["latest_time"] < cutoff)]
    if args.search:
        needle = args.search.casefold()
        rows = [r for r in rows if needle in (r["site"] or "").casefold()]
    rows.sort(key=lambda r: (r["site"] or "", r["measurement"] or ""))
    total = len(rows)
    if args.limit:
        rows = rows[: args.limit]
    payload = {
        "kind": "rivers",
        "source": SOURCE_NAME,
        "source_url": url,
        "hours": args.hours,
        "search": args.search,
        "total_sites": total,
        "stale_sites_excluded": len(stale),
        "aggregation": "hourly averages over the window; latest_value is the most recent hourly average",
        "timezone": "NZ local time as published by Hilltop",
        "rivers": rows,
    }
    lines = [f"River and stream levels, last {args.hours}h ({len(rows)} shown of {total} sites):"]
    for r in rows:
        lines.append(
            f"- {r['site']}: {r['latest_value']} {r['units'] or ''} at {r['latest_time']} "
            f"[{r['trend']}; {args.hours}h range {r['window_min']}–{r['window_max']}]"
        )
    emit(payload, args.json, lines)


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="Hilltop server endpoint (defaults to GWRC; other councils' Hilltop servers work too)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query GWRC Hilltop rainfall and river monitoring time series")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("collections", help="list Hilltop collection names")
    add_common(s)
    s.set_defaults(func=cmd_collections)

    s = sub.add_parser("sites", help="list monitoring sites with coordinates")
    s.add_argument("--measurement", help="only sites exposing this measurement, e.g. Flow, Rainfall, Stage")
    s.add_argument("--search", help="case-insensitive site-name filter")
    s.add_argument("--limit", type=positive_int(2000), help="maximum sites to return")
    add_common(s)
    s.set_defaults(func=cmd_sites)

    s = sub.add_parser("measurements", help="list measurements available at one site")
    s.add_argument("--site", required=True, help="exact site name from the sites command")
    add_common(s)
    s.set_defaults(func=cmd_measurements)

    s = sub.add_parser("latest", help="latest observation for one site and measurement")
    s.add_argument("--site", required=True, help="exact site name from the sites command")
    s.add_argument("--measurement", required=True, help="measurement name, e.g. Stage, Flow, Rainfall")
    s.add_argument("--window-hours", type=positive_int(720), default=72, help="lookback window in hours (default 72)")
    add_common(s)
    s.set_defaults(func=cmd_latest)

    s = sub.add_parser("rainfall", help="rainfall totals for every gauge over a recent window")
    s.add_argument("--hours", type=positive_int(168), default=24, help="totalling window in hours (default 24)")
    s.add_argument("--search", help="case-insensitive site-name filter")
    s.add_argument("--limit", type=positive_int(500), help="maximum gauges to return")
    add_common(s)
    s.set_defaults(func=cmd_rainfall)

    s = sub.add_parser("rivers", help="current river/stream levels with trend over a recent window")
    s.add_argument("--hours", type=positive_int(168), default=24, help="trend window in hours (default 24)")
    s.add_argument("--search", help="case-insensitive site-name filter")
    s.add_argument("--limit", type=positive_int(500), help="maximum sites to return")
    add_common(s)
    s.set_defaults(func=cmd_rivers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
