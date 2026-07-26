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
import html
import io
import json
import math
import pathlib
import re
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

SHARING_SEARCH = "https://www.arcgis.com/sharing/rest/search"
SHARING_ITEM = "https://www.arcgis.com/sharing/rest/content/items/"
SENSOR_BUCKET = "https://gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com/"
SENSOR_META_URL = SENSOR_BUCKET + "transport_sensors/countline_meta_info/csv/countline_meta_info.csv"
SENSOR_HOST = "gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com"

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
    "mapping1.gw.govt.nz",
    "maps.gw.govt.nz",
    "gis.wellingtonwater.co.nz",
}
COUNCIL_ORG_IDS = {portal["org_id"] for portal in PORTALS.values()}
# ArcGIS Online normally uses the org id as the tenant path. XTtANUDT8Va4DLwI is
# the Eagle Technologies tenant that hosts the MetService weather CAP and NZTA
# highway warning feeds referenced by Wellington emergency-management datasets.
COUNCIL_TENANT_IDS = COUNCIL_ORG_IDS | {"XTtANUDT8Va4DLwI"}
ATTRIBUTION = "CC BY 4.0 — attribute the owning council"
SOURCE_NAME = "Wellington councils ArcGIS open data"
SERVICE_HOSTS = ARCGIS_SERVICE_HOSTS | COUNCIL_SERVICE_HOSTS
FETCH_HOSTS = sorted(SERVICE_HOSTS | {"www.arcgis.com"})
ITEM_ID = re.compile(r"^[0-9a-fA-F]{32}$")
ARCGIS_FIELD = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
SERVICE_ITEM_TYPES = {"Feature Service", "Map Service"}
COUNCIL_PATH_PREFIXES = {
    "gis.wcc.govt.nz": ["arcgis", "rest", "services"],
    "giswebprd.gw.govt.nz": ["arcgis", "rest", "services"],
    "mapping.gw.govt.nz": ["arcgis", "rest", "services"],
    "mapping1.gw.govt.nz": ["arcgis", "rest", "services"],
    "maps.gw.govt.nz": ["portal", "rest", "services"],
    "gis.wellingtonwater.co.nz": ["server1", "rest", "services"],
}


def die(message: str, code: int = 1, category: str = "invalid_input") -> None:
    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "skill": "wcc-arcgis-nz",
                    "category": category,
                    "exit_code": code,
                    "message": message,
                },
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    raise SystemExit(code)


def _service_base_from_operation(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(("/query", "/identify")):
        path = path.rsplit("/", 1)[0]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def validate_redirect(requested_url: str, final_url: str) -> None:
    """Reapply source restrictions after redirects, including tenant paths."""
    try:
        requested = urllib.parse.urlparse(requested_url)
        final = urllib.parse.urlparse(final_url)
    except ValueError:
        die("upstream redirect returned an invalid URL", 7, "blocked_host")
    if (requested.hostname or "").lower() != (final.hostname or "").lower():
        die(
            f"upstream redirect changed host from {requested.hostname!r} to {final.hostname!r}",
            7,
            "blocked_host",
        )
    host = (final.hostname or "").lower()
    if host in SERVICE_HOSTS:
        check_layer_host(_service_base_from_operation(final_url))
    elif host == "www.arcgis.com":
        if not final.path.startswith("/sharing/rest/"):
            die(f"unsupported ArcGIS redirect path {final.path!r}", 7, "blocked_host")
    else:
        die(f"unsupported redirect host {host!r}", 7, "blocked_host")


def fetch_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    if params:
        url += "?" + urllib.parse.urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=45,
            accept="application/json,*/*",
            expect_json=True,
            allowed_hosts=FETCH_HOSTS,
        )
    except nzfetch.RateLimited as exc:
        die(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            4,
            "rate_limited",
        )
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4, "blocked")
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5, "upstream_http_failure")
    validate_redirect(url, final_url)
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        die(
            f"source schema failure: malformed ArcGIS JSON ({exc})",
            6,
            "malformed_response",
        )
    if isinstance(data, dict) and data.get("error"):
        error = data["error"]
        detail = error.get("message") if isinstance(error, dict) else None
        die(
            f"ArcGIS error: {detail or json.dumps(error, ensure_ascii=False)[:200]}",
            5,
            "upstream_http_failure",
        )
    return data, final_url


def validate_item_id(reference: str) -> str:
    if not ITEM_ID.fullmatch(reference):
        die(
            f"invalid ArcGIS item id {reference!r}: expected 32 hexadecimal characters",
            2,
        )
    return reference


def validate_item_org(
    item: dict[str, Any],
    reference: str,
    expected_org: str | None = None,
) -> None:
    allowed_orgs = {expected_org} if expected_org else COUNCIL_ORG_IDS
    if item.get("orgId") not in allowed_orgs:
        scope = (
            "the selected Wellington council organisation"
            if expected_org
            else "the verified WCC/GWRC organisations"
        )
        die(
            f"ArcGIS item {reference!r} is not owned by {scope}",
            7,
            "blocked_organisation",
        )


def _plain_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]*>", " ", str(value))
    text = " ".join(html.unescape(text).split())
    return text or None


def normalise_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "owner": item.get("owner"),
        "organisation": item.get("orgId"),
        "url": item.get("url"),
        "snippet": item.get("snippet"),
        "tags": item.get("tags") or [],
        "modified_epoch_ms": item.get("modified"),
    }


def normalise_catalogue_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_url = item.get("url") or None
    service_url = raw_url if item.get("type") in SERVICE_ITEM_TYPES else None
    if service_url:
        check_layer_host(str(service_url))
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "owner": item.get("owner"),
        "organisation": item.get("orgId"),
        "access": item.get("access"),
        "licence": _plain_text(item.get("licenseInfo")),
        "description": _plain_text(item.get("description")),
        "tags": item.get("tags") or [],
        "created_epoch_ms": item.get("created"),
        "modified_epoch_ms": item.get("modified"),
        "size_bytes": item.get("size"),
        "url": raw_url,
        "service_url": service_url,
    }


def check_layer_host(url: str) -> None:
    """Require an exact Wellington ArcGIS REST MapServer/FeatureServer path."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        invalid_authority = (
            parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
        )
    except ValueError:
        parsed = urllib.parse.urlparse("")
        host = ""
        invalid_authority = True
    path = urllib.parse.unquote(parsed.path)
    segments = [segment for segment in path.split("/") if segment]
    path_safe = (
        path.startswith("/")
        and not parsed.query
        and not parsed.fragment
        and "%" not in path
        and all(
            segment not in {".", ".."} and "\\" not in segment
            for segment in segments
        )
    )
    allowed = (
        parsed.scheme == "https"
        and not invalid_authority
        and host in SERVICE_HOSTS
        and path_safe
    )
    if allowed and host in ARCGIS_SERVICE_HOSTS:
        allowed = (
            len(segments) >= 6
            and segments[0] in COUNCIL_TENANT_IDS
            and segments[1:4] == ["arcgis", "rest", "services"]
        )
        tail = segments[4:]
    elif allowed:
        prefix = COUNCIL_PATH_PREFIXES.get(host, [])
        allowed = segments[: len(prefix)] == prefix and len(segments) >= len(prefix) + 2
        tail = segments[len(prefix) :]
    else:
        tail = []
    if allowed:
        server_indexes = [
            index
            for index, segment in enumerate(tail)
            if segment in {"MapServer", "FeatureServer"}
        ]
        allowed = (
            len(server_indexes) == 1
            and server_indexes[0] >= 1
            and (
                server_indexes[0] == len(tail) - 1
                or (
                    server_indexes[0] == len(tail) - 2
                    and tail[-1].isdigit()
                )
            )
        )
    if not allowed:
        die(
            f"unsupported layer URL {url!r}: use an exact HTTPS Wellington "
            "MapServer/FeatureServer REST path",
            7,
            "blocked_host",
        )


def fetch_item(
    reference: str,
    expected_org: str | None = None,
) -> tuple[dict[str, Any], str]:
    item_id = validate_item_id(reference)
    item, source_url = fetch_json(
        SHARING_ITEM + urllib.parse.quote(item_id, safe=""),
        {"f": "json"},
    )
    if not isinstance(item, dict):
        die(
            "source schema failure: ArcGIS item response is not an object",
            6,
            "malformed_response",
        )
    validate_item_org(item, reference, expected_org)
    return item, source_url


def resolve_service_url(reference: str) -> str:
    if reference.startswith(("http://", "https://")):
        url = reference.rstrip("/")
    else:
        item, _ = fetch_item(reference)
        url = str(item.get("url") or "").rstrip("/")
        if not url:
            die(
                f"item {reference} has no service URL (type {item.get('type')!r}); "
                "pick a Feature/Map Service item",
                2,
            )
    check_layer_host(url)
    return url


def _layer_number(url: str) -> int | None:
    last = url.rsplit("/", 1)[-1]
    return int(last) if last.isdigit() else None


def _service_root(url: str) -> str:
    return url.rsplit("/", 1)[0] if _layer_number(url) is not None else url


def resolve_describe_url(reference: str, layer_id: int | None) -> str:
    url = resolve_service_url(reference)
    current = _layer_number(url)
    if current is not None:
        if layer_id is not None and layer_id != current:
            die(
                f"service reference already targets layer {current}; "
                "drop --layer-id or make them agree",
                2,
            )
        return url
    return f"{url}/{layer_id}" if layer_id is not None else url


def resolve_layer_url(reference: str, layer_id: int | None) -> str:
    url = resolve_service_url(reference)
    current = _layer_number(url)
    if current is not None:
        if layer_id is not None and layer_id != current:
            die(
                f"layer reference already targets layer {current}; "
                "drop --layer-id or make them agree",
                2,
            )
        return url
    if layer_id is not None:
        return f"{url}/{layer_id}"
    service, _ = fetch_json(url, {"f": "json"})
    if not isinstance(service, dict):
        die(
            "source schema failure: ArcGIS service response is not an object",
            6,
            "malformed_response",
        )
    layers = parse_service_layers(service)
    if not layers:
        die(
            f"service {url} exposes no layers or tables",
            2,
            "empty_result",
        )
    return f"{url}/{layers[0]['id']}"


def parse_service_layers(service: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for kind in ("layers", "tables"):
        for layer in service.get(kind) or []:
            if not isinstance(layer, dict):
                continue
            rows.append(
                {
                    "id": layer.get("id"),
                    "name": layer.get("name"),
                    "kind": "table" if kind == "tables" else "layer",
                    "geometry_type": layer.get("geometryType"),
                }
            )
    return rows


def parse_point(raw: str) -> tuple[float, float]:
    parts = raw.split(",")
    if len(parts) != 2:
        die(f"invalid --point {raw!r}: expected LON,LAT in WGS84", 2)
    try:
        lon, lat = (float(part) for part in parts)
    except ValueError:
        die(f"invalid --point {raw!r}: expected two numbers", 2)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        die(f"invalid --point {raw!r}: coordinates must be finite", 2)
    if not -180 <= lon <= 180:
        die(f"invalid --point {raw!r}: longitude must be between -180 and 180", 2)
    if not -90 <= lat <= 90:
        die(f"invalid --point {raw!r}: latitude must be between -90 and 90", 2)
    return lon, lat


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


def non_negative_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer") from exc
        if not 0 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 0 and {maximum}")
        return value

    return parse


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        value = non_negative_int(maximum)(raw)
        if value == 0:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def non_negative_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a number") from exc
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(
            "must be a finite number greater than or equal to 0"
        )
    return value


def arcgis_fields(raw: str) -> str:
    if raw == "*":
        return raw
    fields = [part.strip() for part in raw.split(",")]
    if not fields or any(not ARCGIS_FIELD.fullmatch(field) for field in fields):
        raise argparse.ArgumentTypeError(
            "must be '*' or comma-separated ArcGIS field names; dotted names "
            "require non-empty identifier segments"
        )
    return ",".join(fields)


def arcgis_order_by(raw: str) -> str:
    clauses = [part.strip() for part in raw.split(",")]
    normalized = []
    for clause in clauses:
        parts = clause.split()
        if (
            len(parts) not in {1, 2}
            or not ARCGIS_FIELD.fullmatch(parts[0])
            or (len(parts) == 2 and parts[1].upper() not in {"ASC", "DESC"})
        ):
            raise argparse.ArgumentTypeError(
                "must be comma-separated ArcGIS field names with optional ASC or DESC"
            )
        normalized.append(
            parts[0] if len(parts) == 1 else f"{parts[0]} {parts[1].upper()}"
        )
    return ",".join(normalized)


def _field_description(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": field.get("name"),
        "alias": field.get("alias"),
        "type": field.get("type"),
        "description": field.get("description"),
        "unit": field.get("unit") or field.get("units"),
        "domain": field.get("domain"),
    }


def normalise_description(data: dict[str, Any]) -> dict[str, Any]:
    extent = data.get("extent") or data.get("fullExtent") or data.get("initialExtent")
    spatial_reference = data.get("spatialReference")
    if spatial_reference is None and isinstance(extent, dict):
        spatial_reference = extent.get("spatialReference")
    capabilities = data.get("capabilities")
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "type": data.get("type"),
        "description": _plain_text(
            data.get("description") or data.get("serviceDescription")
        ),
        "current_version": data.get("currentVersion"),
        "geometry_type": data.get("geometryType"),
        "object_id_field": data.get("objectIdField")
        or data.get("objectIdFieldName"),
        "fields": [
            _field_description(field)
            for field in (data.get("fields") or [])
            if isinstance(field, dict)
        ],
        "extent": extent,
        "spatial_reference": spatial_reference,
        "capabilities": (
            [part.strip() for part in capabilities.split(",") if part.strip()]
            if isinstance(capabilities, str)
            else capabilities or []
        ),
        "units": data.get("units"),
        "max_record_count": data.get("maxRecordCount"),
        "supported_query_formats": data.get("supportedQueryFormats"),
        "layers": parse_service_layers(data),
    }


def validate_description_payload(data: dict[str, Any], is_layer: bool) -> None:
    def plausible_child(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and isinstance(value.get("id"), int)
            and not isinstance(value.get("id"), bool)
            and isinstance(value.get("name"), str)
            and bool(value["name"].strip())
        )

    if is_layer:
        plausible = (
            isinstance(data.get("id"), int)
            and not isinstance(data.get("id"), bool)
            and isinstance(data.get("name"), str)
            and bool(data["name"].strip())
            and isinstance(data.get("type"), str)
            and bool(data["type"].strip())
            and (
                "fields" not in data
                or isinstance(data.get("fields"), list)
            )
            and (
                "extent" not in data
                or isinstance(data.get("extent"), dict)
            )
        )
    else:
        plausible = (
            isinstance(data.get("currentVersion"), (int, float))
            and not isinstance(data.get("currentVersion"), bool)
            and any(key in data for key in ("layers", "tables"))
            and all(
                isinstance(data[key], list)
                for key in ("layers", "tables")
                if key in data
            )
            and all(
                plausible_child(child)
                for key in ("layers", "tables")
                for child in (data.get(key) or [])
            )
        )
    if not plausible:
        kind = "layer" if is_layer else "service"
        die(
            f"source schema failure: ArcGIS {kind} metadata is implausible",
            6,
            "malformed_response",
        )


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
        {
            "f": "json",
            "q": q,
            "num": args.limit,
            "start": args.start,
            "sortField": "modified",
            "sortOrder": "desc",
        },
    )
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        die(
            "source schema failure: ArcGIS search returned no results list",
            6,
            "malformed_response",
        )
    verified_results: list[dict[str, Any]] = []
    for item in data["results"]:
        if not isinstance(item, dict):
            die(
                "source schema failure: ArcGIS search item is not an object",
                6,
                "malformed_response",
            )
        if item.get("orgId") is None:
            item, _ = fetch_item(
                str(item.get("id") or ""),
                expected_org=portal["org_id"],
            )
        validate_item_org(
            item,
            str(item.get("id") or "search result"),
            expected_org=portal["org_id"],
        )
        if item.get("url") and item.get("type") in {"Feature Service", "Map Service"}:
            check_layer_host(str(item["url"]))
        verified_results.append(item)
    items = [normalise_item(item) for item in verified_results]
    payload = {
        "kind": "search",
        "source": portal["title"] + " ArcGIS open data",
        "source_url": url,
        "portal_site": portal["site"],
        "licence": ATTRIBUTION,
        "keyword": args.keyword,
        "type_filter": args.type,
        "start": data.get("start", args.start),
        "next_start": data.get("nextStart"),
        "total_matches": data.get("total"),
        "items": items,
    }
    lines = [f"{portal['title']} datasets matching {args.keyword!r}: {len(items)} shown of {data.get('total')}"]
    for it in items:
        lines.append(f"- {it['id']} | {it['title']} ({it['type']})")
        if it["url"]:
            lines.append(f"    {it['url']}")
    if payload["next_start"] not in (None, -1):
        lines.append(f"Next page: --start {payload['next_start']}")
    emit(payload, args.json, lines)


def cmd_item(args: argparse.Namespace) -> None:
    item, url = fetch_item(args.item_id)
    metadata = normalise_catalogue_item(item)
    payload = {
        "kind": "item",
        "source": SOURCE_NAME,
        "source_url": url,
        "licence": ATTRIBUTION,
        "item": metadata,
    }
    lines = [
        f"{metadata['title']} ({metadata['type']})",
        f"ID: {metadata['id']} | owner: {metadata['owner']} | "
        f"access: {metadata['access']}",
    ]
    if metadata["service_url"]:
        lines.append(str(metadata["service_url"]))
    emit(payload, args.json, lines)


def cmd_layers(args: argparse.Namespace) -> None:
    service_url = _service_root(resolve_service_url(args.item))
    service, url = fetch_json(service_url, {"f": "json"})
    if not isinstance(service, dict):
        die(
            "source schema failure: ArcGIS service response is not an object",
            6,
            "malformed_response",
        )
    rows = parse_service_layers(service)
    payload = {
        "kind": "layers",
        "source_url": url,
        "service_url": service_url,
        "licence": ATTRIBUTION,
        "description": _plain_text(service.get("serviceDescription")),
        "layers": rows,
    }
    lines = [f"Layers at {service_url}: {len(rows)}"]
    for r in rows:
        geom = f", {r['geometry_type']}" if r["geometry_type"] else ""
        lines.append(f"- [{r['id']}] {r['name']} ({r['kind']}{geom})")
    emit(payload, args.json, lines)


def cmd_describe(args: argparse.Namespace) -> None:
    describe_url = resolve_describe_url(args.service, args.layer_id)
    data, url = fetch_json(describe_url, {"f": "json"})
    if not isinstance(data, dict):
        die(
            "source schema failure: ArcGIS metadata response is not an object",
            6,
            "malformed_response",
        )
    validate_description_payload(
        data,
        is_layer=_layer_number(describe_url) is not None,
    )
    description = normalise_description(data)
    payload = {
        "kind": "describe",
        "source": SOURCE_NAME,
        "source_url": url,
        "service_url": _service_root(describe_url),
        "layer_url": describe_url if _layer_number(describe_url) is not None else None,
        "licence": ATTRIBUTION,
        "description": description,
    }
    lines = [
        f"{description['name'] or description['description'] or describe_url}",
        f"Capabilities: {', '.join(description['capabilities']) or 'not supplied'}",
    ]
    if description["geometry_type"]:
        lines.append(
            f"Geometry: {description['geometry_type']} | object ID: "
            f"{description['object_id_field'] or 'not supplied'}"
        )
    emit(payload, args.json, lines)


def _query_payload_base(
    kind: str,
    source_url: str,
    layer_url: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "source": SOURCE_NAME,
        "source_url": source_url,
        "layer_url": layer_url,
        "licence": ATTRIBUTION,
        "where": args.where or "1=1",
        "bbox": args.bbox,
    }


def cmd_query(args: argparse.Namespace) -> None:
    bbox_params = parse_bbox(args.bbox) if args.bbox else {}
    layer_url = resolve_layer_url(args.layer, args.layer_id)
    params: dict[str, Any] = {
        "where": args.where or "1=1",
        "outFields": args.fields or "*",
        "resultRecordCount": args.limit,
        "resultOffset": args.offset,
        "orderByFields": args.order_by,
        "geometryPrecision": args.geometry_precision,
        "maxAllowableOffset": args.max_allowable_offset,
        "returnGeometry": "false" if args.no_geometry else "true",
        "outSR": "4326",
        "f": "json" if args.count or args.ids_only else "geojson",
    }
    if args.count:
        params["returnCountOnly"] = "true"
    if args.ids_only:
        params["returnIdsOnly"] = "true"
    params.update(bbox_params)
    data, url = fetch_json(layer_url + "/query", params)
    if not isinstance(data, dict):
        die(
            "source schema failure: layer query returned a non-object",
            6,
            "malformed_response",
        )
    if args.count:
        if not isinstance(data.get("count"), int):
            die(
                "source schema failure: count query returned no integer count",
                6,
                "malformed_response",
            )
        payload = _query_payload_base("query-count", url, layer_url, args)
        payload["count"] = data["count"]
        emit(
            payload,
            args.json,
            [f"{data['count']} matching feature(s) from {layer_url}"],
        )
        return
    if args.ids_only:
        object_ids = data.get("objectIds")
        if not isinstance(object_ids, list):
            die(
                "source schema failure: ID query returned no objectIds list",
                6,
                "malformed_response",
            )
        payload = _query_payload_base("query-ids", url, layer_url, args)
        payload.update(
            {
                "object_id_field": data.get("objectIdFieldName"),
                "object_ids": object_ids,
            }
        )
        emit(
            payload,
            args.json,
            [f"{len(object_ids)} matching object ID(s) from {layer_url}"],
        )
        return
    features = data.get("features")
    if not isinstance(features, list):
        die(
            f"source schema failure: layer query returned no GeoJSON "
            f"FeatureCollection: {str(data)[:200]}",
            6,
            "malformed_response",
        )
    truncated = bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))
    payload = _query_payload_base("query", url, layer_url, args)
    payload.update(
        {
            "feature_count": len(features),
            "truncated": truncated,
            "features": features,
        }
    )
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


def cmd_identify(args: argparse.Namespace) -> None:
    lon, lat = parse_point(args.point)
    service_url = resolve_service_url(args.service)
    if _layer_number(service_url) is not None:
        existing_layer = _layer_number(service_url)
        if args.layer_id is not None and args.layer_id != existing_layer:
            die(
                f"service reference already targets layer {existing_layer}; "
                "drop --layer-id or make them agree",
                2,
            )
        args.layer_id = existing_layer
        service_url = _service_root(service_url)
    if not service_url.endswith("/MapServer"):
        die("identify requires a MapServer service URL or item", 2)
    delta = 0.01
    params: dict[str, Any] = {
        "geometry": json.dumps(
            {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}},
            separators=(",", ":"),
        ),
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "mapExtent": (
            f"{max(-180.0, lon - delta)},{max(-90.0, lat - delta)},"
            f"{min(180.0, lon + delta)},{min(90.0, lat + delta)}"
        ),
        "imageDisplay": "800,600,96",
        "tolerance": args.tolerance,
        "layers": f"all:{args.layer_id}" if args.layer_id is not None else "all",
        "returnGeometry": "false" if args.no_geometry else "true",
        "f": "json",
    }
    data, url = fetch_json(service_url + "/identify", params)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        die(
            "source schema failure: identify returned no results list",
            6,
            "malformed_response",
        )
    results = data["results"]
    payload = {
        "kind": "identify",
        "source": SOURCE_NAME,
        "source_url": url,
        "service_url": service_url,
        "licence": ATTRIBUTION,
        "point": {
            "longitude": lon,
            "latitude": lat,
            "spatial_reference": 4326,
        },
        "layer_id": args.layer_id,
        "tolerance": args.tolerance,
        "result_count": len(results),
        "results": results,
    }
    emit(
        payload,
        args.json,
        [f"{len(results)} raw identify result(s) at {lon},{lat} from {service_url}"],
    )


def fetch_csv_rows(url: str, timeout: int = 120) -> list[dict[str, str]]:
    try:
        text = nzfetch.fetch_text(
            url,
            timeout=timeout,
            accept="text/csv,*/*",
            allowed_hosts=[SENSOR_HOST],
        )
    except nzfetch.RateLimited as exc:
        die(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            4,
            "rate_limited",
        )
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4, "blocked")
    except nzfetch.FetchError as exc:
        die(f"upstream unavailable: {exc}", 5, "upstream_http_failure")
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
        value = float(raw) if raw else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) else None


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


def _normalise_negative_values(argv: list[str]) -> list[str]:
    """Make negative-leading coordinate tuples safe at the argparse boundary."""
    result: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if (
            value in {"--point", "--bbox"}
            and index + 1 < len(argv)
            and argv[index + 1].startswith("-")
            and "," in argv[index + 1]
        ):
            result.append(f"{value}={argv[index + 1]}")
            index += 2
            continue
        result.append(value)
        index += 1
    return result


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        die(f"argument error: {message}", 2, "invalid_input")


def build_parser() -> argparse.ArgumentParser:
    parser = StructuredArgumentParser(
        description="Wellington council ArcGIS open data and transport sensor counts"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search a council's open data catalogue")
    s.add_argument(
        "keyword",
        help="search keyword(s), e.g. flood, coastal hazard, road network",
    )
    s.add_argument(
        "--portal",
        choices=sorted(PORTALS),
        default="wcc",
        help="which council portal to search (default wcc)",
    )
    s.add_argument("--type", help='ArcGIS item type filter, e.g. "Feature Service"')
    s.add_argument(
        "--limit",
        type=positive_int(100),
        default=10,
        help="maximum items (default 10)",
    )
    s.add_argument("--start", type=positive_int(10_000_000), default=1)
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("item", help="get normalized Wellington ArcGIS item metadata")
    s.add_argument("item_id", help="32-character ArcGIS item id")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_item)

    s = sub.add_parser("layers", help="list layers/tables of a service item or URL")
    s.add_argument("item", help="ArcGIS item id from search, or a service URL")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_layers)

    s = sub.add_parser("describe", help="describe a service or selected layer")
    s.add_argument(
        "service",
        help="ArcGIS item id or verified Wellington service/layer URL",
    )
    s.add_argument("--layer-id", type=non_negative_int(1_000_000))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser(
        "query",
        help="query a layer and return GeoJSON or a count/ID envelope",
    )
    s.add_argument("layer", help="item id, service URL, or layer URL ending /<layerId>")
    s.add_argument("--layer-id", type=non_negative_int(1_000_000))
    s.add_argument("--where", help="SQL attribute filter, e.g. \"Status='Active'\"")
    s.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat in WGS84")
    s.add_argument(
        "--fields",
        type=arcgis_fields,
        help="comma-separated output fields (default all)",
    )
    s.add_argument(
        "--limit",
        type=positive_int(2000),
        default=50,
        help="maximum features (default 50)",
    )
    modes = s.add_mutually_exclusive_group()
    modes.add_argument(
        "--count",
        action="store_true",
        help="return a normalized count envelope",
    )
    modes.add_argument(
        "--ids-only",
        action="store_true",
        help="return a normalized object-ID envelope",
    )
    s.add_argument("--no-geometry", action="store_true")
    s.add_argument("--offset", type=non_negative_int(10_000_000))
    s.add_argument(
        "--order-by",
        type=arcgis_order_by,
        help="ArcGIS orderByFields expression",
    )
    s.add_argument("--geometry-precision", type=non_negative_int(15))
    s.add_argument("--max-allowable-offset", type=non_negative_float)
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("identify", help="run a raw MapServer point identify")
    s.add_argument(
        "service",
        help="MapServer item id or verified Wellington MapServer URL",
    )
    s.add_argument("--point", required=True, help="LON,LAT in WGS84")
    s.add_argument("--layer-id", type=non_negative_int(1_000_000))
    s.add_argument("--tolerance", type=non_negative_int(100), default=3)
    s.add_argument("--no-geometry", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_identify)

    s = sub.add_parser("sensors", help="list transport sensor countlines with coordinates")
    s.add_argument("--search", help="case-insensitive countline-name filter")
    s.add_argument("--limit", type=positive_int(2000), help="maximum countlines")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sensors)

    s = sub.add_parser(
        "sensors-latest",
        help="latest published counts per countline and transport class",
    )
    s.add_argument(
        "--month",
        help="fetch a specific month's file (YYYY-MM) instead of the latest",
    )
    s.add_argument("--search", help="case-insensitive countline-name filter")
    s.add_argument(
        "--limit",
        type=positive_int(2000),
        default=30,
        help="maximum rows (default 30)",
    )
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_sensors_latest)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    values = list(sys.argv[1:] if argv is None else argv)
    return build_parser().parse_args(_normalise_negative_values(values))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
