#!/usr/bin/env python3
"""Search and query NIWA public ArcGIS open data (read-only, no login).

Org-scoped catalogue search plus GeoJSON layer queries for NIWA's national
coastal and climate datasets: Coastal Sensitivity Index (erosion and
inundation), beach exposure, coastal landform and hinterland classification,
and other layers NIWA publishes openly.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SHARING_SEARCH = "https://www.arcgis.com/sharing/rest/search"
SHARING_ITEM = "https://www.arcgis.com/sharing/rest/content/items/"
# Org id resolved via https://hub.arcgis.com/api/v3/domains/data-niwa.opendata.arcgis.com
# on 2026-07-24. Hub-wide search APIs return the global catalogue, so every
# search is scoped to this organisation.
NIWA_ORG_ID = "fp1tibNcN9mbExhG"
PORTAL_SITE = "https://data-niwa.opendata.arcgis.com/"
SOURCE_NAME = "NIWA ArcGIS open data"
ATTRIBUTION = "CC BY 4.0 — attribute NIWA"
# Layer queries may only leave for NIWA's verified infrastructure. ArcGIS
# Online service URLs carry the owning tenant id as their first path segment.
ARCGIS_SERVICE_HOSTS = {"services.arcgis.com", "services3.arcgis.com"}
NIWA_SERVICE_HOSTS = {"gis.niwa.co.nz"}
FETCH_HOSTS = sorted(
    ARCGIS_SERVICE_HOSTS | NIWA_SERVICE_HOSTS | {"www.arcgis.com"}
)


def die(message: str, code: int = 1) -> None:
    print(f"niwa-coastal-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        data = nzfetch.fetch_json(url, timeout=45, allowed_hosts=FETCH_HOSTS)
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
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        invalid_authority = parsed.port is not None or parsed.username is not None or parsed.password is not None
    except ValueError:
        parsed = urllib.parse.urlparse("")
        host = ""
        invalid_authority = True
    allowed = parsed.scheme == "https" and not invalid_authority and host in (ARCGIS_SERVICE_HOSTS | NIWA_SERVICE_HOSTS)
    if allowed and host in ARCGIS_SERVICE_HOSTS:
        path_parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
        allowed = bool(path_parts and path_parts[0] == NIWA_ORG_ID)
    if not allowed:
        die(
            f"unsupported layer URL {url!r}: use HTTPS and a verified NIWA service host or the NIWA ArcGIS organisation",
            7,
        )


def validate_item_org(item: dict[str, Any], reference: str) -> None:
    if item.get("orgId") != NIWA_ORG_ID:
        die(f"ArcGIS item {reference!r} is not owned by the verified NIWA organisation", 7)


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
    q = f"({args.keyword}) orgid:{NIWA_ORG_ID}"
    if args.type:
        q += f' type:"{args.type}"'
    data, url = fetch_json(
        SHARING_SEARCH,
        {"f": "json", "q": q, "num": args.limit, "sortField": "modified", "sortOrder": "desc"},
    )
    items = [normalise_item(r) for r in data.get("results", [])]
    payload = {
        "kind": "search",
        "source": SOURCE_NAME,
        "source_url": url,
        "portal_site": PORTAL_SITE,
        "licence": ATTRIBUTION,
        "keyword": args.keyword,
        "type_filter": args.type,
        "total_matches": data.get("total"),
        "items": items,
    }
    lines = [f"NIWA datasets matching {args.keyword!r}: {len(items)} shown of {data.get('total')}"]
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
        "source": SOURCE_NAME,
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
        "source": SOURCE_NAME,
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
    parser = argparse.ArgumentParser(description="NIWA ArcGIS open data: coastal sensitivity and classification (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search NIWA's open data catalogue")
    s.add_argument("keyword", help="search keyword(s), e.g. coastal sensitivity, beach exposure")
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
    s.add_argument("--layer-id", type=int, help="layer id when passing an item/service")
    s.add_argument("--where", help="SQL attribute filter")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    s.add_argument("--fields", help="comma-separated output fields (default all)")
    s.add_argument("--limit", type=positive_int(2000), default=50, help="maximum features (default 50)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_query)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
