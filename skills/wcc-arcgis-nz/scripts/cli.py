#!/usr/bin/env python3
"""Search and query Wellington City Council / Greater Wellington ArcGIS open data.

Org-scoped dataset search through the public ArcGIS sharing API, layer listing
and GeoJSON queries against the councils' FeatureServer/MapServer endpoints, and
the Pōneke Travel Insights transport sensor countlines and counts published to a
public S3 bucket. Read-only, no authentication. Data is CC BY 4.0 — attribute
the owning council.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SHARING_SEARCH = "https://www.arcgis.com/sharing/rest/search"
SHARING_ITEM = "https://www.arcgis.com/sharing/rest/content/items/"
SENSOR_BUCKET = "https://gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com/"
SENSOR_META_URL = SENSOR_BUCKET + "transport_sensors/countline_meta_info/csv/countline_meta_info.csv"

# ArcGIS Hub portal search is only trustworthy when scoped to the owning
# organisation — the hub-wide APIs return the global catalogue. Org IDs verified
# via https://hub.arcgis.com/api/v3/domains/<hostname> on 2026-07-22.
PORTALS = {
    "wcc": {
        "org_id": "CPYspmTk3abe6d7i",
        "title": "Wellington City Council",
        "site": "https://data-wcc.opendata.arcgis.com/",
    },
    "gwrc": {
        "org_id": "RS7BXJAO6ksvblJm",
        "title": "Greater Wellington Regional Council",
        "site": "https://data-gwrc.opendata.arcgis.com/",
    },
}
# Layer queries may only leave for the councils' verified infrastructure. ArcGIS
# Online service URLs also carry the owning organisation id as their first path
# segment, so enforce that rather than trusting every tenant on *.arcgis.com.
ARCGIS_SERVICE_HOSTS = {"services.arcgis.com", "services1.arcgis.com", "services2.arcgis.com"}
COUNCIL_SERVICE_HOSTS = {
    "gis.wcc.govt.nz",
    "giswebprd.gw.govt.nz",
    "mapping.gw.govt.nz",
    "maps.gw.govt.nz",
}
COUNCIL_ORG_IDS = {portal["org_id"] for portal in PORTALS.values()}
# ArcGIS Online normally uses the org id as the tenant path. GWRC retains one
# verified legacy tenant id on services.arcgis.com.
COUNCIL_TENANT_IDS = COUNCIL_ORG_IDS | {"XTtANUDT8Va4DLwI"}
ATTRIBUTION = "CC BY 4.0 — attribute the owning council"


def die(message: str, code: int = 1) -> None:
    print(f"wcc-arcgis-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        host = urllib.parse.urlparse(url).hostname
        data = nzfetch.fetch_json(url, timeout=45, allowed_hosts=[host] if host else None)
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    if isinstance(data, dict) and data.get("error"):
        detail = data["error"].get("message") or json.dumps(data["error"])[:200]
        die(f"ArcGIS error: {detail}", 5)
    return data, url


def normalise_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "owner": item.get("owner"),
        "url": item.get("url"),
        "snippet": item.get("snippet"),
        "tags": item.get("tags") or [],
        "modified_epoch_ms": item.get("modified"),
    }


def check_layer_host(url: str) -> None:
    parsed = urllib.parse.urlparse("")
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        invalid_authority = parsed.port is not None or parsed.username is not None or parsed.password is not None
    except ValueError:
        host = ""
        invalid_authority = True
    allowed = parsed.scheme == "https" and not invalid_authority and host in (ARCGIS_SERVICE_HOSTS | COUNCIL_SERVICE_HOSTS)
    if allowed and host in ARCGIS_SERVICE_HOSTS:
        path_parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
        allowed = bool(path_parts and path_parts[0] in COUNCIL_TENANT_IDS)
    if not allowed:
        die(
            f"unsupported layer URL {url!r}: use HTTPS and a verified WCC/GWRC service host or ArcGIS organisation",
            7,
        )


def validate_item_org(item: dict[str, Any], reference: str) -> None:
    if item.get("orgId") not in COUNCIL_ORG_IDS:
        die(f"ArcGIS item {reference!r} is not owned by the verified WCC/GWRC organisations", 7)


def resolve_layer_url(reference: str, layer_id: int | None) -> str:
    """Accept a full layer URL, a service URL, or an ArcGIS item id."""
    if reference.startswith(("http://", "https://")):
        url = reference.rstrip("/")
    else:
        if not reference.replace("-", "").isalnum() or len(reference) < 8:
            die(f"invalid layer reference {reference!r}: pass an item id or a service/layer URL", 2)
        item, _ = fetch_json(SHARING_ITEM + urllib.parse.quote(reference), {"f": "json"})
        validate_item_org(item, reference)
        url = (item.get("url") or "").rstrip("/")
        if not url:
            die(f"item {reference} has no service URL (type {item.get('type')!r}); pick a Feature/Map Service item", 2)
    check_layer_host(url)
    last = url.rsplit("/", 1)[-1]
    if last.isdigit():
        if layer_id is not None and str(layer_id) != last:
            die(f"layer reference already targets layer {last}; drop --layer-id or make them agree", 2)
        return url
    if layer_id is not None:
        return f"{url}/{layer_id}"
    # No layer given: ask the service for its first layer (services do not
    # always start at 0).
    service, _ = fetch_json(url, {"f": "json"})
    layers = parse_service_layers(service)
    if not layers:
        die(f"service {url} exposes no layers or tables", 2)
    return f"{url}/{layers[0]['id']}"


def parse_service_layers(service: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for kind in ("layers", "tables"):
        for layer in service.get(kind) or []:
            rows.append(
                {
                    "id": layer.get("id"),
                    "name": layer.get("name"),
                    "kind": "table" if kind == "tables" else "layer",
                    "geometry_type": layer.get("geometryType"),
                }
            )
    return rows


def parse_bbox(raw: str) -> dict[str, str]:
    parts = raw.split(",")
    if len(parts) != 4:
        die(f"invalid --bbox {raw!r}: expected minLon,minLat,maxLon,maxLat in WGS84", 2)
    try:
        minx, miny, maxx, maxy = (float(p) for p in parts)
    except ValueError:
        die(f"invalid --bbox {raw!r}: expected four numbers", 2)
    if not (minx < maxx and miny < maxy):
        die(f"invalid --bbox {raw!r}: min values must be smaller than max values", 2)
    return {
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_search(args: argparse.Namespace) -> None:
    portal = PORTALS[args.portal]
    q = f"({args.keyword}) orgid:{portal['org_id']}"
    if args.type:
        q += f' type:"{args.type}"'
    data, url = fetch_json(
        SHARING_SEARCH,
        {"f": "json", "q": q, "num": args.limit, "sortField": "modified", "sortOrder": "desc"},
    )
    items = [normalise_item(r) for r in data.get("results", [])]
    payload = {
        "kind": "search",
        "source": portal["title"] + " ArcGIS open data",
        "source_url": url,
        "portal_site": portal["site"],
        "licence": ATTRIBUTION,
        "keyword": args.keyword,
        "type_filter": args.type,
        "total_matches": data.get("total"),
        "items": items,
    }
    lines = [f"{portal['title']} datasets matching {args.keyword!r}: {len(items)} shown of {data.get('total')}"]
    for it in items:
        lines.append(f"- {it['id']} | {it['title']} ({it['type']})")
        if it["url"]:
            lines.append(f"    {it['url']}")
    emit(payload, args.json, lines)


def cmd_layers(args: argparse.Namespace) -> None:
    reference = args.item
    if reference.startswith(("http://", "https://")):
        service_url = reference.rstrip("/")
    else:
        item, _ = fetch_json(SHARING_ITEM + urllib.parse.quote(reference), {"f": "json"})
        validate_item_org(item, reference)
        service_url = (item.get("url") or "").rstrip("/")
        if not service_url:
            die(f"item {reference} has no service URL (type {item.get('type')!r})", 2)
    check_layer_host(service_url)
    if service_url.rsplit("/", 1)[-1].isdigit():
        service_url = service_url.rsplit("/", 1)[0]
    service, url = fetch_json(service_url, {"f": "json"})
    rows = parse_service_layers(service)
    payload = {
        "kind": "layers",
        "source_url": url,
        "service_url": service_url,
        "licence": ATTRIBUTION,
        "description": (service.get("serviceDescription") or "")[:300] or None,
        "layers": rows,
    }
    lines = [f"Layers at {service_url}: {len(rows)}"]
    for r in rows:
        geom = f", {r['geometry_type']}" if r["geometry_type"] else ""
        lines.append(f"- [{r['id']}] {r['name']} ({r['kind']}{geom})")
    emit(payload, args.json, lines)


def cmd_query(args: argparse.Namespace) -> None:
    bbox_params = parse_bbox(args.bbox) if args.bbox else {}
    layer_url = resolve_layer_url(args.layer, args.layer_id)
    params: dict[str, Any] = {
        "where": args.where or "1=1",
        "outFields": args.fields or "*",
        "resultRecordCount": args.limit,
        "outSR": "4326",
        "f": "geojson",
    }
    params.update(bbox_params)
    data, url = fetch_json(layer_url + "/query", params)
    features = data.get("features") if isinstance(data, dict) else None
    if features is None:
        die(f"source schema failure: layer query returned no GeoJSON FeatureCollection: {str(data)[:200]}", 6)
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    payload = {
        "kind": "query",
        "source_url": url,
        "layer_url": layer_url,
        "licence": ATTRIBUTION,
        "where": params["where"],
        "bbox": args.bbox,
        "feature_count": len(features),
        "truncated": truncated,
        "features": features,
    }
    lines = [
        f"{len(features)} feature(s) from {layer_url}"
        + (" (truncated; narrow the query for more)" if truncated else "")
    ]
    for feature in features[:20]:
        props = feature.get("properties") or {}
        preview = ", ".join(f"{k}={v}" for k, v in list(props.items())[:4])
        lines.append(f"- {preview}")
    if len(features) > 20:
        lines.append(f"... {len(features) - 20} more (use --json for full output)")
    emit(payload, args.json, lines)


def fetch_csv_rows(url: str, timeout: int = 120) -> list[dict[str, str]]:
    try:
        text = nzfetch.fetch_text(url, timeout=timeout, accept="text/csv,*/*")
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    return list(csv.DictReader(io.StringIO(text)))


def parse_sensor_meta(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if not row.get("COUNTLINE_ID"):
            continue
        out.append(
            {
                "countline_id": row["COUNTLINE_ID"],
                "name": row.get("NAME"),
                "latitude": parse_optional_float(row.get("LATITUDE_START_LINE")),
                "longitude": parse_optional_float(row.get("LONGITUDE_START_LINE")),
                "earliest": row.get("EARLIEST"),
                "latest": row.get("LATEST"),
            }
        )
    return out


def parse_optional_float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw else None
    except (TypeError, ValueError):
        return None


def summarise_mobility(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Counts for the latest date in the file plus a daily average for context."""
    daily: dict[tuple[str, str, str], int] = {}
    for row in rows:
        date = row.get("COUNTLINE_DATE")
        countline = row.get("COUNTLINE_ID")
        klass = row.get("COUNTLINE_TRANSPORT_CLASS")
        if not date or not countline or not klass:
            continue
        try:
            count = int(row.get("DIRECTION_COUNT") or 0)
        except ValueError:
            continue
        key = (countline, klass, date)
        daily[key] = daily.get(key, 0) + count
    if not daily:
        return {"latest_date": None, "rows": []}
    latest_date = max(date for (_, _, date) in daily)
    summary: dict[tuple[str, str], dict[str, Any]] = {}
    for (countline, klass, date), count in daily.items():
        entry = summary.setdefault(
            (countline, klass),
            {
                "countline_id": countline,
                "transport_class": klass,
                "latest_date_count": None,
                "latest_observed_date": date,
                "day_totals": [],
            },
        )
        entry["day_totals"].append(count)
        entry["latest_observed_date"] = max(entry["latest_observed_date"], date)
        if date == latest_date:
            entry["latest_date_count"] = count
    rows_out = []
    for entry in summary.values():
        totals = entry.pop("day_totals")
        entry["daily_average"] = round(sum(totals) / len(totals), 1)
        entry["days_observed"] = len(totals)
        entry["stale"] = entry["latest_observed_date"] != latest_date
        rows_out.append(entry)
    return {"latest_date": latest_date, "rows": rows_out}


def cmd_sensors(args: argparse.Namespace) -> None:
    sensors = parse_sensor_meta(fetch_csv_rows(SENSOR_META_URL, timeout=60))
    if args.search:
        needle = args.search.casefold()
        sensors = [s for s in sensors if needle in (s["name"] or "").casefold()]
    total = len(sensors)
    if args.limit:
        sensors = sensors[: args.limit]
    payload = {
        "kind": "sensors",
        "source": "WCC Pōneke Travel Insights transport sensors",
        "source_url": SENSOR_META_URL,
        "licence": ATTRIBUTION,
        "total_countlines": total,
        "sensors": sensors,
    }
    lines = [f"Transport sensor countlines: {len(sensors)} shown of {total}"]
    for s in sensors:
        lines.append(
            f"- {s['countline_id']} {s['name']} ({s['latitude']}, {s['longitude']}) data {s['earliest']} → {s['latest']}"
        )
    emit(payload, args.json, lines)


def cmd_sensors_latest(args: argparse.Namespace) -> None:
    meta = parse_sensor_meta(fetch_csv_rows(SENSOR_META_URL, timeout=60))
    names = {s["countline_id"]: s for s in meta}
    if args.month:
        parts = args.month.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or not parts[0].isdigit() or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 12:
            die(f"invalid --month {args.month!r}: expected YYYY-MM", 2)
        months = [(parts[0], parts[1].zfill(2))]
    else:
        latest = max((s["latest"] or "" for s in meta), default="")
        if len(latest) < 7:
            die("source schema failure: countline metadata has no usable LATEST dates", 6)
        year, month = latest[:4], latest[5:7]
        if month == "01":
            months = [(year, month), (str(int(year) - 1), "12")]
        else:
            months = [(year, month), (year, f"{int(month) - 1:02d}")]
    rows = None
    used = None
    for year, month in months:
        url = SENSOR_BUCKET + (
            f"transport_sensors/countline_mobility/csv/{year}/{month}/countline_mobility_{year}_{month}.csv"
        )
        try:
            rows = fetch_csv_rows(url)
            used = (year, month, url)
            break
        except SystemExit as exc:
            # Only a missing file (upstream 404 → exit 5) falls back a month;
            # blocked/rate-limited states must surface for the month they hit.
            if exc.code != 5 or (year, month) == months[-1]:
                raise
    summary = summarise_mobility(rows)
    out_rows = summary["rows"]
    for row in out_rows:
        info = names.get(row["countline_id"]) or {}
        row["name"] = info.get("name")
        row["latitude"] = info.get("latitude")
        row["longitude"] = info.get("longitude")
        row["metadata_latest_date"] = info.get("latest")
    if args.search:
        needle = args.search.casefold()
        out_rows = [r for r in out_rows if needle in (r.get("name") or "").casefold()]
    out_rows.sort(
        key=lambda r: (r["latest_date_count"] is not None, r["latest_date_count"] or 0),
        reverse=True,
    )
    total = len(out_rows)
    if args.limit:
        out_rows = out_rows[: args.limit]
    payload = {
        "kind": "sensors-latest",
        "source": "WCC Pōneke Travel Insights transport sensor counts",
        "source_url": used[2],
        "licence": ATTRIBUTION,
        "month": f"{used[0]}-{used[1]}",
        "latest_date": summary["latest_date"],
        "note": "counts refresh no less than monthly; null latest_date_count means the countline/class did not report on latest_date",
        "total_rows": total,
        "counts": out_rows,
    }
    lines = [
        f"Sensor counts for {summary['latest_date']} (file {used[0]}-{used[1]}; "
        f"{len(out_rows)} shown of {total}, busiest first):"
    ]
    for r in out_rows:
        if r["latest_date_count"] is None:
            reading = f"no observation on {summary['latest_date']} (last observed {r['latest_observed_date']})"
        else:
            reading = str(r["latest_date_count"])
        lines.append(
            f"- {r['name'] or r['countline_id']} [{r['transport_class']}]: {reading} "
            f"(daily avg {r['daily_average']} over {r['days_observed']} observed days)"
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Wellington council ArcGIS open data and transport sensor counts")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search a council's open data catalogue")
    s.add_argument("keyword", help="search keyword(s), e.g. flood, coastal hazard, road network")
    s.add_argument("--portal", choices=sorted(PORTALS), default="wcc", help="which council portal to search (default wcc)")
    s.add_argument("--type", help='ArcGIS item type filter, e.g. "Feature Service"')
    s.add_argument("--limit", type=positive_int(100), default=10, help="maximum items (default 10)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("layers", help="list layers/tables of a service item or URL")
    s.add_argument("item", help="ArcGIS item id from search, or a service URL")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_layers)

    s = sub.add_parser("query", help="query a layer and return GeoJSON features")
    s.add_argument("layer", help="item id, service URL, or layer URL ending /<layerId>")
    s.add_argument("--layer-id", type=int, help="layer id when passing an item/service (default 0)")
    s.add_argument("--where", help="SQL attribute filter, e.g. \"Status='Active'\"")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    s.add_argument("--fields", help="comma-separated output fields (default all)")
    s.add_argument("--limit", type=positive_int(2000), default=50, help="maximum features (default 50)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("sensors", help="list transport sensor countlines with coordinates")
    s.add_argument("--search", help="case-insensitive countline-name filter")
    s.add_argument("--limit", type=positive_int(2000), help="maximum countlines")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sensors)

    s = sub.add_parser("sensors-latest", help="latest published counts per countline and transport class")
    s.add_argument("--month", help="fetch a specific month's file (YYYY-MM) instead of the latest")
    s.add_argument("--search", help="case-insensitive countline-name filter")
    s.add_argument("--limit", type=positive_int(2000), default=30, help="maximum rows (default 30)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sensors_latest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
