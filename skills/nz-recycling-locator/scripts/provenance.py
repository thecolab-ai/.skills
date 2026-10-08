#!/usr/bin/env python3
"""Small stdlib output helpers; see the repository's docs/contracts.md."""
from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from typing import Any

ERROR_TYPES = {
    2: "invalid_input",
    3: "missing_configuration",
    4: "blocked",
    5: "upstream_unavailable",
    6: "schema_failure",
    7: "unsupported_operation",
}


def provenance(
    source_url: str,
    publisher: str,
    *,
    licence: str | None = None,
    latest_data: str | None = None,
    retrieved_at: str | None = None,
) -> dict[str, str]:
    """Use the original retrieval time for cached data; omit unknown source facts."""
    retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")) if retrieved_at else datetime.now(timezone.utc)
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    meta = {
        "source_url": source_url,
        "publisher": publisher,
        "retrieved_at": retrieved.astimezone(timezone.utc).isoformat(timespec="auto" if retrieved_at else "seconds").replace("+00:00", "Z"),
    }
    if licence:
        meta["licence"] = licence
    if latest_data:
        meta["latest_data"] = latest_data
    return meta


def result_envelope(results: list[Any], meta: dict[str, str]) -> dict[str, Any]:
    return {"meta": meta, "results": results}


def error_envelope(
    code: int,
    message: str,
    meta: dict[str, str],
    *,
    retry_after: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "type": ERROR_TYPES[code], "message": message}
    if retry_after is not None:
        error["retry_after"] = retry_after
    return {"meta": meta, "results": [], "error": error}


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """Parse a WGS84 box without accepting NaN, infinity or reversed bounds."""
    message = "--bbox must be minLon,minLat,maxLon,maxLat in WGS84 with increasing bounds"
    try:
        parts = tuple(float(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(message) from exc
    if len(parts) != 4 or not all(math.isfinite(part) for part in parts):
        raise argparse.ArgumentTypeError(message)
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise argparse.ArgumentTypeError(message)
    return min_lon, min_lat, max_lon, max_lat


def add_spatial_arguments(parser: argparse.ArgumentParser) -> None:
    """Call only on commands that implement spatial filtering and GeoJSON output."""
    parser.add_argument("--bbox", type=parse_bbox, metavar="minLon,minLat,maxLon,maxLat", help="filter by a WGS84 bounding box")
    parser.add_argument("--format", choices=("json", "geojson"), default="json", help="output format; geojson implies machine-readable output")


def geojson_envelope(features: list[dict[str, Any]], meta: dict[str, str]) -> dict[str, Any]:
    """Features must already use WGS84 longitude/latitude coordinates."""
    return {"type": "FeatureCollection", "features": features, "meta": meta}
