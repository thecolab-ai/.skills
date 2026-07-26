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
import math
import pathlib
import re
import sys
import urllib.error
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

HOST = "gis.gns.cri.nz"
SHAKINGLAYERS_HOST = "shakinglayers.geonet.org.nz"
FETCH_HOSTS = [HOST, SHAKINGLAYERS_HOST]
BASE = f"https://{HOST}/server/rest/services"
SHAKINGLAYERS_BASE = f"https://{SHAKINGLAYERS_HOST}/api/v1"
FAULTS_SERVICE = BASE + "/Active_Faults/NZActiveFaultDatasets/MapServer"
SHAKING_SERVICE = BASE + "/ShakingLayers/ShakingLayers/FeatureServer"
SOURCE_NAME = "GNS Science hazard services"
ARCGIS_ATTRIBUTION = "CC BY 4.0 — attribute GNS Science"
ARCHIVE_ATTRIBUTION = "CC BY 3.0 New Zealand — attribute GeoNet"
# Layer ids verified against the live ShakingLayers FeatureServer 2026-07-24.
SHAKING_MEASURES = {
    "mmi": 1,      # Modified Mercalli Intensity, mean contours
    "pga": 4,      # peak ground acceleration (g)
    "pgv": 7,      # peak ground velocity (cm/s)
    "psa0.3": 10,  # pseudo-spectral acceleration, 0.3 s
    "psa1.0": 13,  # pseudo-spectral acceleration, 1.0 s
    "psa3.0": 16,  # pseudo-spectral acceleration, 3.0 s
}
EVENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._+-]{0,99}")
FILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
ARCGIS_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)
ARCGIS_ORDER_CLAUSE_PATTERN = re.compile(
    rf"({ARCGIS_IDENTIFIER_PATTERN.pattern})(?:\s+(ASC|DESC))?",
    re.IGNORECASE,
)
MEASURE_FILES = {
    "mmi": {
        "file_name": "intensity_mmi_contour_lines.json",
        "units": "MMI",
        "description": "Modified Mercalli Intensity",
    },
    "pga": {
        "file_name": "pga_g_contour_lines.json",
        "units": "g",
        "description": "peak ground acceleration",
    },
    "pgv": {
        "file_name": "pgv_cms_contour_lines.json",
        "units": "cm/s",
        "description": "peak ground velocity",
    },
    "psa0.3": {
        "file_name": "psa_0p3_g_contour_lines.json",
        "units": "g",
        "description": "pseudo-spectral acceleration at 0.3 seconds",
    },
    "psa1.0": {
        "file_name": "psa_1p0_g_contour_lines.json",
        "units": "g",
        "description": "pseudo-spectral acceleration at 1.0 second",
    },
    "psa3.0": {
        "file_name": "psa_3p0_g_contour_lines.json",
        "units": "g",
        "description": "pseudo-spectral acceleration at 3.0 seconds",
    },
}


def die(message: str, code: int = 1, *, category: str | None = None) -> None:
    default_categories = {
        1: "error",
        2: "invalid_input",
        4: "blocked",
        5: "upstream_unavailable",
        6: "source_schema",
        7: "unsafe_source",
    }
    print(
        json.dumps(
            {
                "skill": "gns-hazards-nz",
                "error": {
                    "code": code,
                    "category": category or default_categories.get(code, "error"),
                    "message": message,
                },
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    raise SystemExit(code)


def fetch_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    parsed = urllib.parse.urlparse(url)
    if (parsed.hostname or "").lower() == SHAKINGLAYERS_HOST:
        return fetch_archive_json(url)
    return fetch_arcgis_json(url)


def fetch_arcgis_json(url: str) -> tuple[Any, str]:
    try:
        data = nzfetch.fetch_json(url, timeout=45, allowed_hosts=[HOST])
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5)
    if isinstance(data, dict) and data.get("error"):
        error = data["error"]
        detail = (
            error.get("message") or json.dumps(error)[:200]
            if isinstance(error, dict)
            else str(error)[:200]
        )
        die(f"ArcGIS error: {detail}", 5)
    return data, url


def _archive_resource_label(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    marker = "/api/v1/events"
    if not path.startswith(marker):
        return "archive resource"
    tail = [part for part in path[len(marker):].split("/") if part]
    if len(tail) == 1:
        return "event"
    if len(tail) == 2:
        return "event version"
    if len(tail) >= 3:
        return "event file"
    return "events endpoint"


def _fetch_error_http_status(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, urllib.error.HTTPError):
            return current.code
        current = current.__cause__
    return None


def validate_archive_final_url(requested_url: str, final_url: str) -> None:
    validate_shakinglayers_url(final_url)
    requested = urllib.parse.urlparse(requested_url)
    final = urllib.parse.urlparse(final_url)
    if urllib.parse.unquote(final.path) != urllib.parse.unquote(requested.path):
        die(
            f"unsafe ShakingLayers redirect path {final.path!r}: "
            f"expected {requested.path!r}",
            7,
            category="unsafe_source",
        )


def fetch_archive_json(url: str) -> tuple[Any, str]:
    validate_shakinglayers_url(url)
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=45,
            accept="application/json,*/*",
            expect_json=True,
            allowed_hosts=[SHAKINGLAYERS_HOST],
        )
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        if _fetch_error_http_status(exc) == 404:
            label = _archive_resource_label(url)
            die(
                f"GeoNet ShakingLayers {label} not found (HTTP 404): {url}",
                5,
                category="not_found",
            )
        die(f"GeoNet ShakingLayers upstream unavailable: {exc}", 5)
    validate_archive_final_url(url, final_url)
    raw = body.decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(
            f"source schema failure: GeoNet ShakingLayers returned malformed JSON: {exc}",
            6,
            category="source_schema",
        )
    if isinstance(data, dict) and data.get("error"):
        error = data["error"]
        detail = (
            error.get("message") or json.dumps(error)[:200]
            if isinstance(error, dict)
            else str(error)[:200]
        )
        if "not found" in detail.lower():
            die(
                f"GeoNet ShakingLayers {_archive_resource_label(url)} not found: {detail}",
                5,
                category="not_found",
            )
        die(f"GeoNet ShakingLayers API error: {detail}", 5)
    return data, final_url


def validate_event_id(event_id: str) -> str:
    if not EVENT_ID_PATTERN.fullmatch(event_id or ""):
        die(
            f"invalid event ID {event_id!r}: expected one safe GeoNet public identifier",
            2,
        )
    return event_id


def validate_version(version: str) -> str:
    if not VERSION_PATTERN.fullmatch(version or ""):
        die(
            f"invalid version {version!r}: expected 'latest' or one safe version path",
            2,
        )
    return version


def validate_file_name(file_name: str) -> str:
    if not FILE_NAME_PATTERN.fullmatch(file_name or ""):
        die(f"invalid file name {file_name!r}: expected one safe file name", 2)
    return file_name


def validate_shakinglayers_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        die(f"unsafe ShakingLayers URL {url!r}", 7)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != SHAKINGLAYERS_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path.startswith("/api/v1/")
    ):
        die(f"unsafe ShakingLayers URL {url!r}: exact HTTPS API host required", 7)


def archive_url(*segments: str) -> str:
    encoded = "/".join(urllib.parse.quote(segment, safe="") for segment in segments)
    url = f"{SHAKINGLAYERS_BASE}/{encoded}"
    validate_shakinglayers_url(url)
    return url


def normalise_events(data: Any, *, year: int | None, source_url: str) -> dict[str, Any]:
    if not isinstance(data, list) or not all(isinstance(value, str) and value for value in data):
        die(f"source schema failure: events response is not a list of event IDs: {str(data)[:200]}", 6)
    return {
        "kind": "events",
        "source": "GeoNet ShakingLayers archive",
        "source_url": source_url,
        "licence": ARCHIVE_ATTRIBUTION,
        "year": year,
        "event_count": len(data),
        "event_ids": data,
    }


def normalise_versions(
    data: Any,
    *,
    requested_event_id: str,
    source_url: str,
) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
        die(f"source schema failure: versions response is malformed: {str(data)[:200]}", 6)
    event_id = data.get("publicID") or data.get("eventid") or requested_event_id
    versions = []
    for row in data["versions"]:
        if not isinstance(row, dict) or not row.get("versionpath"):
            die(f"source schema failure: malformed version entry: {str(row)[:200]}", 6)
        versions.append(
            {
                "versionpath": row.get("versionpath"),
                "status": row.get("status"),
                "issue_time": row.get("issue_time"),
                "type": row.get("type"),
            }
        )
    return {
        "kind": "versions",
        "source": "GeoNet ShakingLayers archive",
        "source_url": source_url,
        "licence": ARCHIVE_ATTRIBUTION,
        "event_id": event_id,
        "requested_event_id": requested_event_id,
        "version_count": len(versions),
        "versions": versions,
    }


def _published_measures(file_names: list[str]) -> list[dict[str, str]]:
    published = set(file_names)
    return [
        {
            "measure": measure,
            "units": metadata["units"],
            "description": metadata["description"],
            "file_name": metadata["file_name"],
        }
        for measure, metadata in MEASURE_FILES.items()
        if metadata["file_name"] in published
    ]


def normalise_event_files(
    data: Any,
    *,
    event_id: str,
    requested_version: str,
) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        die(f"source schema failure: event files response is malformed: {str(data)[:200]}", 6)
    versionpath = data.get("versionpath")
    if not isinstance(versionpath, str) or not VERSION_PATTERN.fullmatch(versionpath):
        die(f"source schema failure: unsafe or missing versionpath: {versionpath!r}", 6)
    file_names = data["files"]
    if not all(isinstance(name, str) and FILE_NAME_PATTERN.fullmatch(name) for name in file_names):
        die("source schema failure: event files included an unsafe file name", 6)
    files = [
        {
            "name": name,
            "source_url": archive_url("events", event_id, versionpath, name),
        }
        for name in file_names
    ]
    measures = _published_measures(file_names)
    by_file = {row["file_name"]: row for row in measures}
    for row in files:
        measure = by_file.get(row["name"])
        if measure:
            row.update({"measure": measure["measure"], "units": measure["units"]})
    return {
        "kind": "event-files",
        "source": "GeoNet ShakingLayers archive",
        "source_url": archive_url("events", event_id, versionpath),
        "licence": ARCHIVE_ATTRIBUTION,
        "event_id": event_id,
        "requested_version": requested_version,
        "versionpath": versionpath,
        "status": data.get("status"),
        "issue_time": data.get("issue_time"),
        "type": data.get("type"),
        "file_count": len(files),
        "files": files,
        "available_measures": measures,
    }


def normalise_description(
    data: Any,
    *,
    service: str,
    layer_id: int,
    layer_url: str,
    source_url: str,
) -> dict[str, Any]:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("name"), str)
        or not data["name"].strip()
        or not isinstance(data.get("geometryType"), str)
        or not data["geometryType"].strip()
        or not isinstance(data.get("fields"), list)
        or not data["fields"]
    ):
        die(f"source schema failure: ArcGIS layer description is malformed: {str(data)[:200]}", 6)
    fields = []
    for field in data["fields"]:
        if not isinstance(field, dict) or not field.get("name"):
            die(f"source schema failure: malformed ArcGIS field: {str(field)[:200]}", 6)
        fields.append(
            {
                key: field.get(key)
                for key in ("name", "alias", "type", "description", "unit", "length", "domain")
                if field.get(key) is not None
            }
        )
    raw_extent = data.get("extent") if isinstance(data.get("extent"), dict) else None
    extent = None
    if raw_extent is not None:
        spatial_reference = raw_extent.get("spatialReference")
        extent = {
            "xmin": raw_extent.get("xmin"),
            "ymin": raw_extent.get("ymin"),
            "xmax": raw_extent.get("xmax"),
            "ymax": raw_extent.get("ymax"),
            "spatial_reference": {
                "wkid": spatial_reference.get("wkid"),
                "latest_wkid": spatial_reference.get("latestWkid"),
            }
            if isinstance(spatial_reference, dict)
            else None,
        }
    object_id_field = data.get("objectIdField") or data.get("objectIdFieldName")
    if not object_id_field:
        object_id_field = next(
            (
                field.get("name")
                for field in data["fields"]
                if isinstance(field, dict) and field.get("type") == "esriFieldTypeOID"
            ),
            None,
        )
    return {
        "kind": "describe",
        "source": SOURCE_NAME,
        "source_url": source_url,
        "layer_url": layer_url,
        "licence": ARCGIS_ATTRIBUTION,
        "service": service,
        "layer_id": layer_id,
        "name": data.get("name"),
        "description": data.get("description"),
        "geometry_type": data.get("geometryType"),
        "object_id_field": object_id_field,
        "max_record_count": data.get("maxRecordCount"),
        "capabilities": data.get("capabilities"),
        "spatial_reference": data.get("sourceSpatialReference"),
        "extent": extent,
        "fields": fields,
    }


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
    if not all(math.isfinite(value) for value in (minx, miny, maxx, maxy)):
        die(f"invalid --bbox {raw!r}: coordinates must be finite", 2)
    if not (-180 <= minx <= 180 and -180 <= maxx <= 180):
        die(f"invalid --bbox {raw!r}: longitudes must be between -180 and 180", 2)
    if not (-90 <= miny <= 90 and -90 <= maxy <= 90):
        die(f"invalid --bbox {raw!r}: latitudes must be between -90 and 90", 2)
    if not (minx < maxx and miny < maxy):
        die(f"invalid --bbox {raw!r}: min values must be smaller than max values", 2)
    return {
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def arcgis_fields(raw: str) -> str:
    if raw == "*":
        return raw
    parts = [part.strip() for part in raw.split(",")]
    if (
        not raw.strip()
        or any(not part for part in parts)
        or any(not ARCGIS_IDENTIFIER_PATTERN.fullmatch(part) for part in parts)
    ):
        raise argparse.ArgumentTypeError(
            "expected comma-separated ArcGIS field identifiers "
            "(letters, digits, underscores, and well-formed dotted segments)"
        )
    return ",".join(parts)


def arcgis_order_by(raw: str) -> str:
    clauses = [clause.strip() for clause in raw.split(",")]
    normalised = []
    if not raw.strip() or any(not clause for clause in clauses):
        raise argparse.ArgumentTypeError(
            "expected comma-separated FIELD [ASC|DESC] clauses"
        )
    for clause in clauses:
        match = ARCGIS_ORDER_CLAUSE_PATTERN.fullmatch(clause)
        if not match:
            raise argparse.ArgumentTypeError(
                "expected comma-separated FIELD [ASC|DESC] clauses using safe identifiers"
            )
        identifier, direction = match.groups()
        normalised.append(
            identifier + (f" {direction.upper()}" if direction else "")
        )
    return ", ".join(normalised)


def build_query_params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "where": getattr(args, "where", None) or "1=1",
    }
    if getattr(args, "bbox", None):
        params.update(parse_bbox(args.bbox))
    if getattr(args, "offset", None) is not None:
        params["resultOffset"] = args.offset
    if getattr(args, "order_by", None):
        params["orderByFields"] = args.order_by
    if getattr(args, "geometry_precision", None) is not None:
        params["geometryPrecision"] = args.geometry_precision
    if getattr(args, "max_allowable_offset", None) is not None:
        params["maxAllowableOffset"] = args.max_allowable_offset
    if getattr(args, "no_geometry", False):
        params["returnGeometry"] = "false"
    if getattr(args, "count", False):
        params.update({"returnCountOnly": "true", "f": "json"})
    elif getattr(args, "ids_only", False):
        params.update({"returnIdsOnly": "true", "f": "json"})
    else:
        params.update(
            {
                "outFields": getattr(args, "fields", None) or "*",
                "resultRecordCount": args.limit,
                "outSR": "4326",
                "f": "geojson",
            }
        )
    return params


def query_layer(
    layer_url: str,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], str]:
    params = build_query_params(args)
    data, url = fetch_json(layer_url + "/query", params)
    if getattr(args, "count", False):
        count = data.get("count") if isinstance(data, dict) else None
        if not isinstance(count, int):
            die(f"source schema failure: count query returned no integer count: {str(data)[:200]}", 6)
        return {"mode": "count", "count": count}, url
    if getattr(args, "ids_only", False):
        object_ids = data.get("objectIds") if isinstance(data, dict) else None
        if not isinstance(object_ids, list):
            die(f"source schema failure: IDs query returned no objectIds list: {str(data)[:200]}", 6)
        return {
            "mode": "ids",
            "object_id_field": data.get("objectIdFieldName"),
            "object_ids": object_ids,
        }, url
    features = data.get("features") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("type") != "FeatureCollection"
        or not isinstance(features, list)
    ):
        die(f"source schema failure: layer query returned no GeoJSON FeatureCollection: {str(data)[:200]}", 6)
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            die(
                f"source schema failure: feature {index} is not an object: "
                f"{str(feature)[:200]}",
                6,
            )
        properties = feature.get("properties")
        if properties is not None and not isinstance(properties, dict):
            die(
                f"source schema failure: feature {index} properties are not an object: "
                f"{str(properties)[:200]}",
                6,
            )
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
        "licence": ARCGIS_ATTRIBUTION,
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
    data, url = query_layer(layer_url, args)
    if data.get("mode") == "count":
        payload = {
            "kind": "faults-count",
            "source": "NZ Active Faults Database (GNS Science)",
            "source_url": url,
            "layer_url": layer_url,
            "licence": ARCGIS_ATTRIBUTION,
            "where": args.where or "1=1",
            "bbox": args.bbox,
            "count": data["count"],
        }
        emit(payload, args.json, [f"{data['count']} matching feature(s)"])
        return
    if data.get("mode") == "ids":
        payload = {
            "kind": "faults-ids",
            "source": "NZ Active Faults Database (GNS Science)",
            "source_url": url,
            "layer_url": layer_url,
            "licence": ARCGIS_ATTRIBUTION,
            "where": args.where or "1=1",
            "bbox": args.bbox,
            "object_id_field": data["object_id_field"],
            "object_ids": data["object_ids"],
        }
        emit(payload, args.json, [f"{len(data['object_ids'])} matching object ID(s)"])
        return
    features = data["features"]
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    payload = {
        "kind": "faults",
        "source": "NZ Active Faults Database (GNS Science)",
        "source_url": url,
        "layer_url": layer_url,
        "licence": ARCGIS_ATTRIBUTION,
        "where": args.where or "1=1",
        "bbox": args.bbox,
        "feature_count": len(features),
        "truncated": truncated,
        "features": features,
    }
    emit(payload, args.json, feature_lines(features, truncated, layer_url))


def distinct_contours(features: list[dict[str, Any]]) -> list[Any]:
    """Sorted distinct `Contour` values, skipping features that carry none.

    A feature without a Contour property is a real upstream possibility, and it
    must not become a `None` entry in the reported contour set.
    """
    values = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        value = properties.get("Contour") if isinstance(properties, dict) else None
        if value is not None:
            values.add(value)
    return sorted(values)


def expected_shaking_layer_name(measure: str) -> str:
    """The layer name the service must expose for `measure`.

    Lets a live probe detect upstream layer-id drift instead of trusting the
    hardcoded map, which would otherwise silently query the wrong measure.
    `psa0.3` -> `psa0p3_mean_cont`; `mmi` -> `mmi_mean_cont`.
    """
    return measure.replace(".", "p") + "_mean_cont"


def cmd_shaking(args: argparse.Namespace) -> None:
    layer_id = SHAKING_MEASURES[args.measure]
    layer_url = f"{SHAKING_SERVICE}/{layer_id}"
    where = "1=1" if args.min_contour is None else f"Contour >= {float(args.min_contour)}"
    args.where = where
    args.fields = None
    data, url = query_layer(layer_url, args)
    if data.get("mode") == "count":
        payload = {
            "kind": "shaking-count",
            "source": "GNS ShakingLayers modelled ground-motion contours",
            "source_url": url,
            "layer_url": layer_url,
            "licence": ARCGIS_ATTRIBUTION,
            "measure": args.measure,
            "where": where,
            "bbox": args.bbox,
            "count": data["count"],
        }
        emit(payload, args.json, [f"{data['count']} matching {args.measure} contour feature(s)"])
        return
    if data.get("mode") == "ids":
        payload = {
            "kind": "shaking-ids",
            "source": "GNS ShakingLayers modelled ground-motion contours",
            "source_url": url,
            "layer_url": layer_url,
            "licence": ARCGIS_ATTRIBUTION,
            "measure": args.measure,
            "where": where,
            "bbox": args.bbox,
            "object_id_field": data["object_id_field"],
            "object_ids": data["object_ids"],
        }
        emit(payload, args.json, [f"{len(data['object_ids'])} matching object ID(s)"])
        return
    features = data["features"]
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    contours = distinct_contours(features)
    payload = {
        "kind": "shaking",
        "source": "GNS ShakingLayers modelled ground-motion contours",
        "source_url": url,
        "layer_url": layer_url,
        "licence": ARCGIS_ATTRIBUTION,
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


def cmd_events(args: argparse.Namespace) -> None:
    params = {"year": args.year} if args.year is not None else None
    data, url = fetch_json(archive_url("events"), params)
    payload = normalise_events(data, year=args.year, source_url=url)
    emit(
        payload,
        args.json,
        [f"{payload['event_count']} ShakingLayers event(s)"]
        + [f"- {event_id}" for event_id in payload["event_ids"]],
    )


def cmd_versions(args: argparse.Namespace) -> None:
    event_id = validate_event_id(args.event_id)
    data, url = fetch_json(archive_url("events", event_id))
    payload = normalise_versions(
        data,
        requested_event_id=event_id,
        source_url=url,
    )
    lines = [f"{payload['version_count']} version(s) for {payload['event_id']}"]
    for row in payload["versions"]:
        lines.append(
            f"- {row['versionpath']} | {row['status']} | {row['type']} | {row['issue_time']}"
        )
    emit(payload, args.json, lines)


def fetch_event_files(event_id: str, version: str) -> dict[str, Any]:
    event_id = validate_event_id(event_id)
    version = validate_version(version)
    data, _ = fetch_json(archive_url("events", event_id, version))
    return normalise_event_files(
        data,
        event_id=event_id,
        requested_version=version,
    )


def cmd_event_files(args: argparse.Namespace) -> None:
    payload = fetch_event_files(args.event_id, args.version)
    lines = [
        f"{payload['file_count']} file(s) for {payload['event_id']} "
        f"version {payload['versionpath']}"
    ]
    lines.extend(f"- {row['name']}" for row in payload["files"])
    if payload["available_measures"]:
        lines.append(
            "Available contour measures: "
            + ", ".join(
                f"{row['measure']} ({row['units']})"
                for row in payload["available_measures"]
            )
        )
    emit(payload, args.json, lines)


def cmd_event_data(args: argparse.Namespace) -> None:
    event_id = validate_event_id(args.event_id)
    version = validate_version(args.version)
    measure = args.measure.lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,30}", measure):
        die(f"invalid measure {args.measure!r}", 2)
    files = fetch_event_files(event_id, version)
    available_by_measure = {
        row["measure"]: row for row in files["available_measures"]
    }
    selected = available_by_measure.get(measure)
    if selected is None:
        available = ", ".join(available_by_measure) or "none"
        file_names = ", ".join(row["name"] for row in files["files"]) or "none"
        die(
            f"measure {measure!r} is unavailable for event {event_id} "
            f"version {files['versionpath']}; available measures: {available}; "
            f"available files: {file_names}",
            2,
        )
    file_name = selected["file_name"]
    validate_file_name(file_name)
    data, url = fetch_json(
        archive_url("events", event_id, files["versionpath"], file_name)
    )
    if (
        not isinstance(data, dict)
        or data.get("type") != "FeatureCollection"
        or not isinstance(data.get("features"), list)
    ):
        die(f"source schema failure: contour file is not a GeoJSON FeatureCollection: {str(data)[:200]}", 6)
    payload = dict(data)
    payload["provenance"] = {
        "source": "GeoNet ShakingLayers archive",
        "source_url": url,
        "licence": ARCHIVE_ATTRIBUTION,
        "event_id": event_id,
        "requested_version": version,
        "versionpath": files["versionpath"],
        "status": files["status"],
        "issue_time": files["issue_time"],
        "type": files["type"],
        "measure": measure,
        "units": selected["units"],
        "description": selected["description"],
        "file_name": file_name,
    }
    emit(
        payload,
        args.json,
        [
            f"{len(payload['features'])} {measure} contour feature(s) for "
            f"{event_id} version {files['versionpath']} ({selected['units']})",
            f"Source: {url}",
        ],
    )


def cmd_describe(args: argparse.Namespace) -> None:
    service_url = FAULTS_SERVICE if args.service == "faults" else SHAKING_SERVICE
    layer_id = args.layer_id
    if layer_id is None:
        layer_id = 0 if args.service == "faults" else SHAKING_MEASURES["mmi"]
    layer_url = f"{service_url}/{layer_id}"
    data, url = fetch_json(layer_url, {"f": "json"})
    payload = normalise_description(
        data,
        service=args.service,
        layer_id=layer_id,
        layer_url=layer_url,
        source_url=url,
    )
    lines = [
        f"[{layer_id}] {payload['name']} ({payload['geometry_type']})",
        f"Object ID: {payload['object_id_field']}; max records: {payload['max_record_count']}",
        f"Fields: {len(payload['fields'])}",
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


def nonnegative_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 0 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 0 and {maximum}")
        return value

    return parse


def nonnegative_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a number")
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number at or above 0")
    return value


def year_value(raw: str) -> int:
    if not re.fullmatch(r"\d{4}", raw):
        raise argparse.ArgumentTypeError("expected a four-digit year")
    return int(raw)


def normalise_coordinate_options(argv: list[str]) -> list[str]:
    """Let argparse accept a comma-separated coordinate value led by '-'."""
    result: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if (
            token == "--bbox"
            and index + 1 < len(argv)
            and argv[index + 1].startswith("-")
            and "," in argv[index + 1]
        ):
            result.append(f"--bbox={argv[index + 1]}")
            index += 2
            continue
        result.append(token)
        index += 1
    return result


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        die(message, 2)


def add_arcgis_query_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_limit: int,
    include_fields: bool,
) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--count", action="store_true", help="return only the matching feature count")
    modes.add_argument("--ids-only", action="store_true", help="return only matching ArcGIS object IDs")
    parser.add_argument("--no-geometry", action="store_true", help="request attributes without feature geometry")
    parser.add_argument("--offset", type=nonnegative_int(1_000_000), help="ArcGIS resultOffset for paging")
    parser.add_argument(
        "--order-by",
        type=arcgis_order_by,
        help="safe comma-separated ArcGIS FIELD [ASC|DESC] clauses",
    )
    parser.add_argument(
        "--geometry-precision",
        type=nonnegative_int(15),
        help="decimal places for returned geometry coordinates",
    )
    parser.add_argument(
        "--max-allowable-offset",
        type=nonnegative_float,
        help="ArcGIS geometry generalisation offset in output spatial-reference units",
    )
    if include_fields:
        parser.add_argument(
            "--fields",
            type=arcgis_fields,
            help="safe comma-separated output field identifiers (default all)",
        )
    parser.add_argument(
        "--limit",
        type=positive_int(2000),
        default=default_limit,
        help=f"maximum features (default {default_limit})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        description="GNS Science active fault and ShakingLayers hazard data (read-only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("layers", help="list layers of the faults or shaking service")
    s.add_argument("--service", choices=["faults", "shaking"], default="faults", help="which service (default faults)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_layers)

    s = sub.add_parser("faults", help="query NZ Active Faults Database features as GeoJSON")
    s.add_argument(
        "--layer-id",
        type=nonnegative_int(100_000),
        default=0,
        help="layer id from `layers` (0..100000; default 0, 1:250k fault traces)",
    )
    s.add_argument("--where", help="SQL attribute filter, e.g. \"name LIKE '%%Wellington%%'\"")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    add_arcgis_query_arguments(s, default_limit=50, include_fields=True)
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_faults)

    s = sub.add_parser("shaking", help="query ShakingLayers ground-motion contours as GeoJSON")
    s.add_argument("--measure", choices=sorted(SHAKING_MEASURES), default="mmi", help="ground-motion measure (default mmi)")
    s.add_argument("--min-contour", type=nonnegative_float, help="only contours at or above this value")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    add_arcgis_query_arguments(s, default_limit=100, include_fields=False)
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_shaking)

    s = sub.add_parser("events", help="list events published in the GeoNet ShakingLayers archive")
    s.add_argument("--year", type=year_value, help="four-digit event year (default: recent events)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_events)

    s = sub.add_parser("versions", help="list published ShakingLayers versions for an event")
    s.add_argument("event_id", help="GeoNet event public ID")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_versions)

    s = sub.add_parser("event-files", help="list files and contour measures for an event version")
    s.add_argument("event_id", help="GeoNet event public ID")
    s.add_argument("--version", default="latest", help="version path or latest (default latest)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_event_files)

    s = sub.add_parser("event-data", help="return one published event contour file as GeoJSON")
    s.add_argument("event_id", help="GeoNet event public ID")
    s.add_argument("--measure", required=True, help="published measure such as mmi, pga, pgv, or psa0.3")
    s.add_argument("--version", default="latest", help="version path or latest (default latest)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_event_data)

    s = sub.add_parser("describe", help="describe an ArcGIS faults or shaking layer")
    s.add_argument("service", choices=["faults", "shaking"], help="service to describe")
    s.add_argument("--layer-id", type=nonnegative_int(100_000), help="layer ID (default 0 for faults, 1 for shaking)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_describe)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args(normalise_coordinate_options(sys.argv[1:]))
    args.func(args)


if __name__ == "__main__":
    main()
