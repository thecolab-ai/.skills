#!/usr/bin/env python3
"""Bounded WFS reader for GNS Science Auckland urban geological units."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from provenance import error_envelope, geojson_envelope, parse_bbox, provenance, result_envelope

SOURCE_URL = "https://data.gns.cri.nz/webmaps/gns/wfs"
HOST = "data.gns.cri.nz"
PATH = "/webmaps/gns/wfs"
PUBLISHER = "GNS Science"
LICENCE = "Creative Commons Attribution 3.0 New Zealand (CC-BY 3.0)"
TYPE_NAME = "gns:NZL-Urban_Auckland_geological_units"
CRS84 = "urn:ogc:def:crs:OGC:1.3:CRS84"
USER_AGENT = "TheColab-gns-auckland-geology/1 (public WFS; bounded GetFeature)"
TIMEOUT_SECONDS = 15
MAX_BYTES = 524_288
MAX_LIMIT = 5
MAX_JSON_DEPTH = 40
MAX_POSITIONS = 20_000
MAX_TEXT = 500
ACCEPTED_CRS = {
    "urn:ogc:def:crs:CRS::84",
    "urn:ogc:def:crs:EPSG::4326",
    "urn:ogc:def:crs:OGC:1.3:CRS84",
    "EPSG:4326",
    "CRS:84",
}
STRING_FIELDS = ("strat_unit", "strat_age", "descriptio", "old_unit_c", "source")
NUMBER_FIELDS = ("area", "perimeter", "geol_units", "geol_uni_1", "scale")
FEATURE_ID_RE = re.compile(r"^NZL-Urban_Auckland_geological_units\.[A-Za-z0-9_.-]{1,40}$")
# All 2639 features on 2026-10-12 (103 codes) used letters, digits, "_", "+",
# "~", and a leading "?" on ?Pks~. "?" is the GNS uncertainty marker and is
# rejected anywhere else. The whole code is at most 41 characters. "." "/" "-"
# were absent from that read and remain allowed only after the first letter
# or digit. A leading "~" or "+" is still rejected.
UNIT_CODE_RE = re.compile(
    r"^(?:\?[A-Za-z0-9][A-Za-z0-9_./~+-]{0,39}|[A-Za-z0-9][A-Za-z0-9_./~+-]{0,40})$"
)
# The 92 features for bbox 174.9,-37.05,174.98,-36.98 included three envelopes
# outside the box. The farthest was 0.000809 degrees (90 m). The server bbox
# filter is authoritative inside this slack. A quarter-degree miss still fails
# when every feature is that far outside.
BBOX_SLACK_DEGREES = 0.002
FIXTURE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
RETRY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9, :+-]{0,63}$")
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class InputError(ValueError):
    """Caller input that must be a JSON invalid_input error, not a traceback."""


class BlockedError(Exception):
    def __init__(self, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamError(Exception):
    pass


class SchemaError(Exception):
    pass


class UnsafeError(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    """Follow at most one redirect, and only back to the pinned WFS URL."""

    max_redirections = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        try:
            assert_official(newurl)
        except UnsafeError as exc:
            raise UnsafeError(
                "refusing a redirect outside https://data.gns.cri.nz/webmaps/gns/wfs"
            ) from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def source_meta(url: str) -> dict[str, str]:
    return provenance(url, PUBLISHER, licence=LICENCE)


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[1-5]", value):
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 5")
    return int(value)


def parse_fixture(value: str) -> str:
    if not FIXTURE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("--fixture must be a fixture name, not a path")
    return value


def format_coord(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def machine_requested(argv: list[str]) -> bool:
    if "--json" in argv:
        return True
    for index, argument in enumerate(argv):
        if argument == "--format=geojson":
            return True
        if argument == "--format" and index + 1 < len(argv) and argv[index + 1] == "geojson":
            return True
    return False


def assert_official(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or host != HOST
        or parsed.path.rstrip("/") != PATH
    ):
        raise UnsafeError("refusing a request outside https://data.gns.cri.nz/webmaps/gns/wfs")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    names = query.get("typeNames", [])
    if names and names != [TYPE_NAME]:
        raise UnsafeError("refusing a request for a feature type other than the Auckland units layer")


def feature_url(box: tuple[float, float, float, float], limit: int) -> str:
    min_lon, min_lat, max_lon, max_lat = box
    bbox = ",".join(
        (
            format_coord(min_lon),
            format_coord(min_lat),
            format_coord(max_lon),
            format_coord(max_lat),
            CRS84,
        )
    )
    query = urllib.parse.urlencode(
        (
            ("service", "WFS"),
            ("version", "2.0.0"),
            ("request", "GetFeature"),
            ("typeNames", TYPE_NAME),
            ("outputFormat", "application/json"),
            ("count", str(limit)),
            ("srsName", CRS84),
            ("bbox", bbox),
        )
    )
    return f"{SOURCE_URL}?{query}"


def json_nesting_depth(text: str) -> int:
    depth = 0
    maximum = 0
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            maximum = max(maximum, depth)
            if maximum > MAX_JSON_DEPTH:
                return maximum
        elif char in "}]":
            depth = max(0, depth - 1)
    return maximum


def parse_json_document(text: str) -> Any:
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError("upstream JSON exceeds the supported nesting depth") from exc
    except ValueError as exc:
        raise SchemaError("upstream returned malformed JSON") from exc


def _reject_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant {value}")


def read_bounded(response: Any) -> tuple[bytes, bool]:
    data = bytearray()
    while len(data) < MAX_BYTES:
        chunk = response.read(min(65536, MAX_BYTES - len(data)))
        if not chunk:
            return bytes(data), False
        data.extend(chunk)
    return bytes(data), bool(response.read(1))


def clean_retry_after(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if RETRY_RE.fullmatch(text):
        return text
    return None


def live_fetch(url: str) -> tuple[int, bytes, str, bool, str | None]:
    """GET one official WFS URL. Returns status, body, final URL, truncated, retry-after."""
    assert_official(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(OfficialRedirect)
    try:
        response = opener.open(request, timeout=TIMEOUT_SECONDS)
    except UnsafeError:
        raise
    except urllib.error.HTTPError as exc:
        response = exc
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if "timed out" in reason.lower():
            raise UpstreamError("network error: source request timed out") from exc
        raise UpstreamError(f"network error: upstream unavailable: {reason}") from exc
    try:
        final_url = response.geturl()
        assert_official(final_url)
        status = int(getattr(response, "status", None) or response.getcode())
        retry_after = clean_retry_after(response.headers.get("Retry-After"))
        body, truncated = read_bounded(response)
    finally:
        response.close()
    return status, body, final_url, truncated, retry_after


def load_fixture(name: str, request_url: str) -> tuple[int, bytes, str, bool, str | None]:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        raise InputError(f"unknown fixture: {name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError("fixture file was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SchemaError("fixture file was not a JSON object")
    error = payload.get("error")
    if error == "timeout":
        raise UpstreamError("network error: source request timed out")
    if isinstance(error, str):
        raise UpstreamError(f"network error: upstream unavailable: {error}")
    status = payload.get("status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise SchemaError("fixture status was not an integer")
    final_url = payload.get("final_url") or request_url
    if not isinstance(final_url, str):
        raise SchemaError("fixture final_url was not a string")
    assert_official(final_url)
    truncated = payload.get("truncated")
    if not isinstance(truncated, bool):
        raise SchemaError("fixture truncated flag was not a boolean")
    body = payload.get("body", "")
    if isinstance(body, str):
        encoded = body.encode("utf-8")
    else:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    retry_after = payload.get("retry_after")
    if retry_after is not None and not isinstance(retry_after, str):
        raise SchemaError("fixture retry_after was not a string")
    return status, encoded, final_url, truncated, clean_retry_after(retry_after)


def exception_message(text: str) -> str:
    code_match = re.search(r'exceptionCode="([^"]{1,80})"', text)
    text_match = re.search(r"ExceptionText>([^<]{1,240})", text)
    code = code_match.group(1) if code_match else "ExceptionReport"
    detail = text_match.group(1).strip() if text_match else "the WFS returned an exception report"
    return f"WFS exception {code}: {detail}"


def interpret(
    status: int,
    body: bytes,
    truncated: bool,
    retry_after: str | None,
    limit: int,
    box: tuple[float, float, float, float],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if truncated:
        raise UpstreamError(f"upstream unavailable: response exceeded {MAX_BYTES} bytes")
    if status == 429:
        raise BlockedError("network error: rate_limited: http 429", retry_after=retry_after)
    if status in {500, 502, 503, 504}:
        raise UpstreamError(f"upstream unavailable: http {status}")
    if status in {301, 302, 303, 307, 308}:
        raise UnsafeError("refusing a redirect that did not resolve on the GNS WFS endpoint")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError("upstream body was not UTF-8") from exc
    folded = text.lower()
    if "<!doctype" in folded or "<!entity" in folded:
        raise SchemaError("upstream XML contained a forbidden declaration")
    stripped = text.lstrip()
    if status != 200:
        if "ExceptionReport" in text or "ExceptionText" in text:
            raise SchemaError(exception_message(text))
        raise UpstreamError(f"upstream unavailable: http {status}")
    if stripped.startswith("<"):
        if "ExceptionReport" in text or "ExceptionText" in text:
            raise SchemaError(exception_message(text))
        raise SchemaError("upstream returned XML, not GeoJSON")
    payload = parse_json_document(text)
    return normalise_collection(payload, limit, box)


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SchemaError(f"{label} was not a finite number")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{label} was not a string")
    if len(value) > MAX_TEXT:
        raise SchemaError(f"{label} exceeds the supported length")
    return value


def _position(value: Any, bounds: list[float]) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise SchemaError("coordinate position was not a longitude, latitude pair")
    lon, lat = value
    if (
        isinstance(lon, bool)
        or isinstance(lat, bool)
        or not isinstance(lon, (int, float))
        or not isinstance(lat, (int, float))
        or not math.isfinite(lon)
        or not math.isfinite(lat)
    ):
        raise SchemaError("coordinate position was not a finite number pair")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise SchemaError("coordinates were not WGS84 longitude and latitude")
    bounds[0] = min(bounds[0], float(lon))
    bounds[1] = min(bounds[1], float(lat))
    bounds[2] = max(bounds[2], float(lon))
    bounds[3] = max(bounds[3], float(lat))
    return [float(lon), float(lat)]


def _ring(value: Any, bounds: list[float], counter: list[int]) -> list[list[float]]:
    if not isinstance(value, list) or len(value) < 4:
        raise SchemaError("polygon ring was shorter than four positions")
    points = [_position(item, bounds) for item in value]
    counter[0] += len(points)
    if counter[0] > MAX_POSITIONS:
        raise SchemaError("feature exceeds the supported position cap")
    if points[0] != points[-1]:
        raise SchemaError("polygon ring was not closed")
    return points


def _polygon(value: Any, bounds: list[float], counter: list[int]) -> list[list[list[float]]]:
    if not isinstance(value, list) or not value:
        raise SchemaError("polygon coordinates were empty")
    return [_ring(ring, bounds, counter) for ring in value]


def validate_geometry(geometry: Any) -> tuple[dict[str, Any], list[float]]:
    if not isinstance(geometry, dict):
        raise SchemaError("feature geometry was not an object")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    counter = [0]
    if kind == "Polygon":
        parsed = _polygon(coordinates, bounds, counter)
    elif kind == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise SchemaError("multipolygon coordinates were empty")
        parsed = [_polygon(polygon, bounds, counter) for polygon in coordinates]
    else:
        raise SchemaError("feature geometry was not a Polygon or MultiPolygon")
    return {"type": kind, "coordinates": parsed}, bounds


def _envelope_outside(bounds: list[float], box: tuple[float, float, float, float]) -> bool:
    """True when the envelope is farther than BBOX_SLACK_DEGREES from the box."""
    min_lon, min_lat, max_lon, max_lat = box
    slack = BBOX_SLACK_DEGREES
    return (
        bounds[2] < min_lon - slack
        or bounds[0] > max_lon + slack
        or bounds[3] < min_lat - slack
        or bounds[1] > max_lat + slack
    )


def _properties(properties: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(properties, dict):
        raise SchemaError("feature properties were not an object")
    record: dict[str, Any] = {}
    unit_code = properties.get("unit_code")
    if not isinstance(unit_code, str) or not UNIT_CODE_RE.fullmatch(unit_code):
        raise SchemaError("unit_code was missing or not a map-unit code")
    record["unit_code"] = unit_code
    record["uncertain"] = unit_code.startswith("?")
    for label in STRING_FIELDS:
        if label not in properties or properties[label] is None:
            continue
        record[label] = _text(properties[label], label)
    for label in NUMBER_FIELDS:
        if label not in properties or properties[label] is None:
            continue
        record[label] = _number(properties[label], label)
    warnings: list[str] = []
    known = {"unit_code", *STRING_FIELDS, *NUMBER_FIELDS}
    for label in sorted(set(properties) - known):
        value = properties[label]
        if value is None or isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if isinstance(value, str):
                record[label] = _text(value, label)
            elif isinstance(value, (int, float)):
                record[label] = _number(value, label)
            else:
                record[label] = None
            warnings.append(f"preserved unknown property {label}")
            continue
        raise SchemaError(f"unknown property {label} was not a scalar")
    return record, warnings


def _crs_name(payload: dict[str, Any], has_features: bool) -> None:
    crs = payload.get("crs")
    if not has_features and crs is None:
        return
    if not isinstance(crs, dict):
        raise SchemaError("feature collection crs was missing")
    properties = crs.get("properties")
    name = properties.get("name") if isinstance(properties, dict) else None
    if not isinstance(name, str) or name not in ACCEPTED_CRS:
        raise SchemaError("feature collection crs was not WGS84 longitude and latitude")


def _count(payload: dict[str, Any], label: str) -> int:
    value = payload.get(label)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaError(f"{label} was not a non-negative integer")
    return value


def normalise_collection(
    payload: Any,
    limit: int,
    box: tuple[float, float, float, float],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise SchemaError("upstream response was not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SchemaError("features was not a list")
    matched = _count(payload, "numberMatched")
    returned = _count(payload, "numberReturned")
    if "totalFeatures" in payload and payload.get("totalFeatures") != matched:
        raise SchemaError("totalFeatures did not match numberMatched")
    if returned != len(features):
        raise SchemaError("numberReturned did not match the feature list")
    if returned > limit or len(features) > limit:
        raise SchemaError("server returned more features than the requested count")
    if matched < returned:
        raise SchemaError("numberMatched was smaller than numberReturned")
    _crs_name(payload, bool(features))
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    dropped = 0
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise SchemaError("feature was not a GeoJSON Feature")
        feature_id = feature.get("id")
        if not isinstance(feature_id, str) or not FEATURE_ID_RE.fullmatch(feature_id):
            raise SchemaError("feature id was not an Auckland geological unit id")
        geometry, bounds = validate_geometry(feature.get("geometry"))
        properties, extra = _properties(feature.get("properties"))
        geometry_name = feature.get("geometry_name")
        if geometry_name is not None:
            if not isinstance(geometry_name, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", geometry_name):
                raise SchemaError("geometry_name was not a short field name")
        if _envelope_outside(bounds, box):
            dropped += 1
            continue
        warnings.extend(extra)
        record: dict[str, Any] = {"feature_id": feature_id, **properties, "geometry": geometry}
        if geometry_name is not None:
            record["geometry_name"] = geometry_name
        records.append(record)
    if features and not records:
        raise SchemaError("feature geometry does not intersect the requested bounding box")
    if matched > returned:
        warnings.append(
            f"returned {returned} of {matched} intersecting units; "
            "this command does not page the remaining matches"
        )
    if dropped:
        noun = "feature" if dropped == 1 else "features"
        warnings.append(f"dropped {dropped} {noun} outside the requested bounding box")
    page = {
        "matched": matched,
        "returned": len(records),
        "limit": limit,
        "truncated": matched > returned,
        "dropped_outside_bbox": dropped,
    }
    return records, page, warnings


def features_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for record in records:
        properties = {key: value for key, value in record.items() if key != "geometry"}
        features.append(
            {
                "type": "Feature",
                "id": record["feature_id"],
                "geometry": record["geometry"],
                "properties": properties,
            }
        )
    return features


def human(payload: dict[str, Any]) -> str:
    page = payload["page"]
    lines = [
        "GNS Science Auckland urban geological units",
        f"matched {page['matched']}, returned {page['returned']}, limit {page['limit']}",
    ]
    for warning in payload.get("warnings", []):
        lines.append(f"warning: {warning}")
    if not payload["results"]:
        lines.append("no geological units intersect this bounding box")
    for record in payload["results"]:
        age = record.get("strat_age") or ""
        name = record.get("strat_unit") or ""
        scale = record.get("scale")
        scale_text = "" if scale is None else str(scale)
        uncertain = " | uncertain" if record.get("uncertain") else ""
        lines.append(f"{record['unit_code']} | {name} | age {age} | scale {scale_text}{uncertain}")
    lines.append(f"licence: {payload['meta'].get('licence', 'unspecified')}")
    lines.append("Attribute GNS Science. Geometry is available in --json and --format geojson.")
    return "\n".join(lines)


def fail(
    code: int,
    message: str,
    machine: bool,
    *,
    url: str | None = None,
    retry_after: str | None = None,
) -> int:
    payload = error_envelope(code, message, source_meta(url or SOURCE_URL), retry_after=retry_after)
    if machine:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"gns-auckland-geology: {message}", file=sys.stderr)
    return code


def run_units(box: tuple[float, float, float, float], limit: int, fixture: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    url = feature_url(box, limit)
    assert_official(url)
    if fixture:
        status, body, _final_url, truncated, retry_after = load_fixture(fixture, url)
    else:
        status, body, _final_url, truncated, retry_after = live_fetch(url)
    records, page, warnings = interpret(status, body, truncated, retry_after, limit, box)
    if fixture:
        warnings.insert(0, f"fixture: {fixture}; rows are not a live retrieval")
    meta = source_meta(url)
    payload = result_envelope(records, meta)
    payload["page"] = page
    payload["warnings"] = warnings
    collection = geojson_envelope(features_from_records(records), meta)
    collection["page"] = page
    collection["warnings"] = warnings
    return payload, collection


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="GNS Science Auckland urban geological units")
    sub = parser.add_subparsers(dest="command", required=True)
    units = sub.add_parser("units", help="geological units intersecting a WGS84 bounding box")
    units.add_argument(
        "--bbox",
        required=True,
        type=parse_bbox,
        metavar="minLon,minLat,maxLon,maxLat",
        help="WGS84 bounding box; the WFS intersects features with this box",
    )
    units.add_argument("--limit", required=True, type=parse_limit, help="WFS count, from 1 to 5")
    units.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    units.add_argument(
        "--format",
        choices=("json", "geojson"),
        default="json",
        help="output format; geojson implies machine-readable output",
    )
    units.add_argument(
        "--fixture",
        type=parse_fixture,
        help="read a named local fixture instead of the network",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        return fail(2, str(exc), machine_requested(argv))
    machine = bool(args.json or args.format == "geojson")
    try:
        if args.command != "units":
            raise UnsafeError("unsupported command")
        payload, collection = run_units(args.bbox, args.limit, args.fixture)
    except InputError as exc:
        return fail(2, str(exc), machine)
    except BlockedError as exc:
        return fail(4, str(exc), machine, retry_after=exc.retry_after)
    except UpstreamError as exc:
        return fail(5, str(exc), machine)
    except SchemaError as exc:
        return fail(6, str(exc), machine)
    except UnsafeError as exc:
        return fail(7, str(exc), machine)
    document = collection if args.format == "geojson" else payload
    if machine:
        json.dump(document, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(human(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
