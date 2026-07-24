#!/usr/bin/env python3
"""Query GNS Science public ArcGIS hazard services (read-only, no login).

Wraps two services on gis.gns.cri.nz:
- NZ Active Faults Database (fault traces, recurrence, slip rates, avoidance
  and awareness zones)
- ShakingLayers ground-motion contours (MMI, PGA, PGV, PSA) published after
  significant New Zealand earthquakes
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

HOST = "gis.gns.cri.nz"
BASE = f"https://{HOST}/server/rest/services"
FAULTS_SERVICE = BASE + "/Active_Faults/NZActiveFaultDatasets/MapServer"
SHAKING_SERVICE = BASE + "/ShakingLayers/ShakingLayers/FeatureServer"
SOURCE_NAME = "GNS Science ArcGIS hazard services"
ATTRIBUTION = "CC BY 4.0 — attribute GNS Science"
# Layer ids verified against the live ShakingLayers FeatureServer 2026-07-24.
SHAKING_MEASURES = {
    "mmi": 1,      # Modified Mercalli Intensity, mean contours
    "pga": 4,      # peak ground acceleration (g)
    "pgv": 7,      # peak ground velocity (cm/s)
    "psa0.3": 10,  # pseudo-spectral acceleration, 0.3 s
    "psa1.0": 13,  # pseudo-spectral acceleration, 1.0 s
    "psa3.0": 16,  # pseudo-spectral acceleration, 3.0 s
}


def die(message: str, code: int = 1) -> None:
    print(f"gns-hazards-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def fetch_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        data = nzfetch.fetch_json(url, timeout=45, allowed_hosts=[HOST])
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


def query_layer(layer_url: str, where: str, bbox: str | None, fields: str | None, limit: int) -> tuple[dict[str, Any], str]:
    params: dict[str, Any] = {
        "where": where,
        "outFields": fields or "*",
        "resultRecordCount": limit,
        "outSR": "4326",
        "f": "geojson",
    }
    if bbox:
        params.update(parse_bbox(bbox))
    data, url = fetch_json(layer_url + "/query", params)
    if not isinstance(data, dict) or data.get("features") is None:
        die(f"source schema failure: layer query returned no GeoJSON FeatureCollection: {str(data)[:200]}", 6)
    return data, url


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def feature_lines(features: list[dict[str, Any]], truncated: bool, layer_url: str) -> list[str]:
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
    return lines


def cmd_layers(args: argparse.Namespace) -> None:
    service_url = FAULTS_SERVICE if args.service == "faults" else SHAKING_SERVICE
    service, url = fetch_json(service_url, {"f": "json"})
    rows = parse_service_layers(service)
    if not rows:
        die(f"source schema failure: no layers listed at {service_url}", 6)
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


def cmd_faults(args: argparse.Namespace) -> None:
    layer_url = f"{FAULTS_SERVICE}/{args.layer_id}"
    data, url = query_layer(layer_url, args.where or "1=1", args.bbox, args.fields, args.limit)
    features = data["features"]
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    payload = {
        "kind": "faults",
        "source": "NZ Active Faults Database (GNS Science)",
        "source_url": url,
        "layer_url": layer_url,
        "licence": ATTRIBUTION,
        "where": args.where or "1=1",
        "bbox": args.bbox,
        "feature_count": len(features),
        "truncated": truncated,
        "features": features,
    }
    emit(payload, args.json, feature_lines(features, truncated, layer_url))


def cmd_shaking(args: argparse.Namespace) -> None:
    layer_id = SHAKING_MEASURES[args.measure]
    layer_url = f"{SHAKING_SERVICE}/{layer_id}"
    where = "1=1" if args.min_contour is None else f"Contour >= {float(args.min_contour)}"
    data, url = query_layer(layer_url, where, args.bbox, None, args.limit)
    features = data["features"]
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    contours = sorted(
        {p.get("Contour") for f in features if (p := f.get("properties") or {}).get("Contour") is not None}
    )
    payload = {
        "kind": "shaking",
        "source": "GNS ShakingLayers ground-motion contours",
        "source_url": url,
        "layer_url": layer_url,
        "licence": ATTRIBUTION,
        "measure": args.measure,
        "note": (
            "contours reflect the most recently published ShakingLayers model for a "
            "significant earthquake, not a permanent hazard map; absence of features "
            "is not proof of no shaking"
        ),
        "where": where,
        "bbox": args.bbox,
        "contour_values": contours,
        "feature_count": len(features),
        "truncated": truncated,
        "features": features,
    }
    lines = [
        f"{len(features)} {args.measure} contour feature(s)"
        + (f", contour values {contours}" if contours else "")
        + (" (truncated)" if truncated else "")
    ]
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
    parser = argparse.ArgumentParser(description="GNS Science active fault and ShakingLayers hazard data (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("layers", help="list layers of the faults or shaking service")
    s.add_argument("--service", choices=["faults", "shaking"], default="faults", help="which service (default faults)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_layers)

    s = sub.add_parser("faults", help="query NZ Active Faults Database features as GeoJSON")
    s.add_argument("--layer-id", type=int, default=0, help="layer id from `layers` (default 0, 1:250k fault traces)")
    s.add_argument("--where", help="SQL attribute filter, e.g. \"name LIKE '%%Wellington%%'\"")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    s.add_argument("--fields", help="comma-separated output fields (default all)")
    s.add_argument("--limit", type=positive_int(2000), default=50, help="maximum features (default 50)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_faults)

    s = sub.add_parser("shaking", help="query ShakingLayers ground-motion contours as GeoJSON")
    s.add_argument("--measure", choices=sorted(SHAKING_MEASURES), default="mmi", help="ground-motion measure (default mmi)")
    s.add_argument("--min-contour", type=float, help="only contours at or above this value")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    s.add_argument("--limit", type=positive_int(2000), default=100, help="maximum features (default 100)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_shaking)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
