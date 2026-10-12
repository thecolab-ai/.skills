#!/usr/bin/env python3
"""Bounded BKG heavy-rain WMS layer list and one extraordinary-event velocity point."""
from __future__ import annotations

import argparse
import json
import math
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from provenance import error_envelope, provenance, result_envelope

SOURCE_URL = "https://sgx.geodatenzentrum.de/wms_starkregen"
PUBLISHER = "Bundesamt für Kartographie und Geodäsie (BKG)"
LICENCE = "Datenlizenz Deutschland – Namensnennung – Version 2.0"
OFFICIAL_HOST = "sgx.geodatenzentrum.de"
USER_AGENT = "thecolab-bkg-starkregen-wms/1.0 (+https://github.com/thecolab-ai/.skills)"
TIMEOUT_SECONDS = 10
CAPABILITIES_BYTE_CAP = 750_000
FEATUREINFO_BYTE_CAP = 20_000
MAX_NAMED_LAYERS = 160
MAX_TITLE_CHARS = 240
QUERY_LAYER = "geschwindigkeit_agw"
WMS_VERSION = "1.3.0"
CRS = "EPSG:4326"
CRS_AXIS_ORDER = "latitude,longitude"
GRID_SIZE = 101
PIXEL_I = 50
PIXEL_J = 50
HALF_SPAN_DEGREES = 0.0005
NODATA_SENTINEL = -9999.0
NO_FEATURE_BODY = "no features were found"


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class SkillError(Exception):
    """A typed operational failure with a stable exit code."""

    def __init__(self, code: int, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class OfficialHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Stay on the official HTTPS host. Do not follow off-site redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host != OFFICIAL_HOST:
            raise SkillError(4, f"blocked: redirect left the official host {OFFICIAL_HOST}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def source_meta(*, source_url: str = SOURCE_URL, licence: str | None = LICENCE) -> dict[str, str]:
    return provenance(source_url, PUBLISHER, licence=licence)


def attribution(retrieved_at: str) -> str:
    year = retrieved_at[:4]
    return f"© BKG ({year}) dl-de/by-2-0"


def fees_state_licence(fees: str) -> bool:
    text = " ".join(fees.split())
    return (
        "Datenlizenz Deutschland" in text
        and "Namensnennung" in text
        and "2.0" in text
        and "govdata.de/dl-de/by-2-0" in text
    )


def parse_coordinate(value: str, name: str, low: float, high: float) -> float:
    message = f"{name} must be a finite WGS84 decimal degree from {low:g} to {high:g}"
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(message) from exc
    if not math.isfinite(number) or number < low or number > high:
        raise argparse.ArgumentTypeError(message)
    return number


def parse_latitude(value: str) -> float:
    return parse_coordinate(value, "latitude", -90, 90)


def parse_longitude(value: str) -> float:
    return parse_coordinate(value, "longitude", -180, 180)


def format_degree(value: float) -> str:
    return f"{value:.4f}"


def point_bbox(lat: float, lon: float) -> dict[str, float]:
    """Centre a 0.001-degree box on the WGS84 point without crossing world limits."""
    min_lat = lat - HALF_SPAN_DEGREES
    max_lat = lat + HALF_SPAN_DEGREES
    min_lon = lon - HALF_SPAN_DEGREES
    max_lon = lon + HALF_SPAN_DEGREES
    if min_lat < -90 or max_lat > 90 or min_lon < -180 or max_lon > 180:
        raise SkillError(
            2,
            "latitude/longitude is too close to a pole or the antimeridian for the fixed point window",
        )
    return {
        "min_latitude": float(format_degree(min_lat)),
        "min_longitude": float(format_degree(min_lon)),
        "max_latitude": float(format_degree(max_lat)),
        "max_longitude": float(format_degree(max_lon)),
    }


def bbox_parameter(box: dict[str, float]) -> str:
    """WMS 1.3.0 EPSG:4326 axis order is latitude, then longitude."""
    return ",".join(
        format_degree(box[key])
        for key in ("min_latitude", "min_longitude", "max_latitude", "max_longitude")
    )


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in list(element):
        if local_name(child.tag) == name:
            text = "".join(child.itertext()).strip()
            return text or None
    return None


def parse_capabilities(xml_bytes: bytes) -> tuple[list[dict[str, object]], str]:
    if not xml_bytes.strip():
        raise SkillError(6, "GetCapabilities body was empty")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SkillError(6, f"GetCapabilities was not XML: {exc}") from exc
    if local_name(root.tag) != "WMS_Capabilities":
        raise SkillError(6, "GetCapabilities root was not WMS_Capabilities")
    fees = ""
    for element in root.iter():
        if local_name(element.tag) == "Fees":
            fees = "".join(element.itertext()).strip()
            break
    if not fees_state_licence(fees):
        raise SkillError(
            6,
            "capabilities Fees did not state Datenlizenz Deutschland Namensnennung 2.0",
        )
    confirm_epsg4326_axis(root)
    layers: list[dict[str, object]] = []
    seen: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "Layer":
            continue
        name = _child_text(element, "Name")
        if not name:
            continue
        if len(name) > 80 or any(char.isspace() for char in name):
            raise SkillError(6, f"layer name is not a bounded token: {name[:40]}")
        if name in seen:
            raise SkillError(6, f"duplicate layer name: {name}")
        seen.add(name)
        title = _child_text(element, "Title") or ""
        if len(title) > MAX_TITLE_CHARS:
            raise SkillError(6, f"layer title exceeds {MAX_TITLE_CHARS} characters: {name}")
        queryable_raw = element.attrib.get("queryable")
        if queryable_raw is None:
            queryable: bool | None = None
        elif queryable_raw == "1":
            queryable = True
        elif queryable_raw == "0":
            queryable = False
        else:
            raise SkillError(6, f"layer queryable flag was not 0 or 1: {name}")
        layers.append({"name": name, "title": title, "queryable": queryable})
        if len(layers) > MAX_NAMED_LAYERS:
            raise SkillError(
                7,
                f"capabilities named-layer count exceeds the bound of {MAX_NAMED_LAYERS}",
            )
    if not layers:
        raise SkillError(6, "GetCapabilities contained no named layers")
    if not any(layer["name"] == QUERY_LAYER for layer in layers):
        raise SkillError(6, f"GetCapabilities did not name {QUERY_LAYER}")
    return layers, CRS_AXIS_ORDER


def confirm_epsg4326_axis(root: ET.Element) -> str:
    """Refuse a point query when the advertised EPSG:4326 box is not latitude-first."""
    layer = None
    for element in root.iter():
        if local_name(element.tag) == "Layer" and _child_text(element, "Name") == QUERY_LAYER:
            layer = element
            break
    if layer is None:
        raise SkillError(6, f"GetCapabilities did not name {QUERY_LAYER}")
    box = None
    for child in list(layer):
        if local_name(child.tag) == "BoundingBox" and child.attrib.get("CRS") == CRS:
            box = child.attrib
            break
    if box is None:
        raise SkillError(6, f"{QUERY_LAYER} has no EPSG:4326 bounding box")
    try:
        minx = float(box["minx"])
        miny = float(box["miny"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SkillError(6, "EPSG:4326 bounding box coordinates were not numeric") from exc
    # Published Germany coverage: latitude about 48.8–55.1, longitude about 5.4–15.9.
    # On this service the EPSG:4326 minx/miny pair is latitude then longitude.
    if 47 <= minx <= 56 and 5 <= miny <= 16 and minx > miny:
        return CRS_AXIS_ORDER
    if 5 <= minx <= 16 and 47 <= miny <= 56:
        raise SkillError(
            6,
            "EPSG:4326 bounding box is longitude-first; refusing a latitude-first point query",
        )
    raise SkillError(6, "EPSG:4326 bounding box does not show Germany latitude/longitude axes")


def parse_feature_info(body: str) -> dict[str, object]:
    stripped = body.strip()
    if not stripped:
        raise SkillError(6, "GetFeatureInfo body was empty")
    if "ServiceException" in stripped:
        raise SkillError(6, "GetFeatureInfo returned a service exception")
    if stripped == NO_FEATURE_BODY:
        return {
            "feature_type": None,
            "state": "no_data",
            "geschwindigkeit": None,
            "geschwindigkeit_text": None,
            "no_data_reason": "no_feature",
            "source_token": None,
        }
    feature_match = None
    velocity_tokens: list[str] = []
    for line in body.splitlines():
        text = line.strip()
        if text.startswith("Results for FeatureType ") and text.endswith(":"):
            feature_match = text[len("Results for FeatureType ") : -1].strip("'")
        elif text.startswith("Geschwindigkeit = "):
            velocity_tokens.append(text[len("Geschwindigkeit = ") :].strip())
    if feature_match is None or len(velocity_tokens) != 1:
        raise SkillError(6, "GetFeatureInfo did not contain one feature type and one Geschwindigkeit")
    feature_type = feature_match.rsplit(":", 1)[-1]
    if not feature_type or any(char.isspace() for char in feature_type):
        raise SkillError(6, "GetFeatureInfo feature type was empty")
    token = velocity_tokens[0]
    try:
        value = float(token)
    except ValueError as exc:
        raise SkillError(6, "Geschwindigkeit was not a number") from exc
    if not math.isfinite(value):
        raise SkillError(6, "Geschwindigkeit was not a finite number")
    if value == NODATA_SENTINEL:
        return {
            "feature_type": feature_type,
            "state": "no_data",
            "geschwindigkeit": None,
            "geschwindigkeit_text": None,
            "no_data_reason": "sentinel",
            "source_token": token,
        }
    return {
        "feature_type": feature_type,
        "state": "value",
        "geschwindigkeit": value,
        "geschwindigkeit_text": token,
        "no_data_reason": None,
        "source_token": None,
    }


def read_fixture(path: str, cap: int) -> bytes:
    if path.startswith(("http://", "https://")):
        raise SkillError(2, "fixture must be a local file")
    file_path = Path(path)
    if not file_path.is_file():
        raise SkillError(2, "fixture file was not found")
    data = file_path.read_bytes()
    if len(data) > cap:
        raise SkillError(7, f"fixture exceeds the {cap} byte bound")
    return data


def _looks_blocked(body: bytes) -> bool:
    sample = body[:4000].lower()
    markers = (b"incapsula", b"cf-browser-verification", b"just a moment", b"access denied")
    return any(marker in sample for marker in markers)


def fetch_official(url: str, cap: int, accept: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != OFFICIAL_HOST:
        raise SkillError(4, f"blocked: request host is not {OFFICIAL_HOST}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    opener = urllib.request.build_opener(
        OfficialHostRedirectHandler,
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() != OFFICIAL_HOST:
                raise SkillError(4, f"blocked: response host is not {OFFICIAL_HOST}")
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            retry_after = response.headers.get("Retry-After")
            payload = response.read(cap + 1)
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if exc.code == 429:
            raise SkillError(4, "blocked: http 429", retry_after=retry_after) from exc
        if exc.code in {403, 451}:
            raise SkillError(4, f"blocked: http {exc.code}") from exc
        raise SkillError(5, f"upstream unavailable: http {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SkillError(5, f"network error: {exc}") from exc
    if status == 429:
        raise SkillError(4, "blocked: http 429", retry_after=retry_after)
    if status in {403, 451}:
        raise SkillError(4, f"blocked: http {status}")
    if status != 200:
        raise SkillError(5, f"upstream unavailable: http {status}")
    if len(payload) > cap:
        raise SkillError(7, f"response exceeds the {cap} byte bound")
    if _looks_blocked(payload):
        raise SkillError(4, "blocked: upstream returned an access challenge")
    return payload, content_type


def capabilities_url() -> str:
    query = urllib.parse.urlencode(
        {"SERVICE": "WMS", "REQUEST": "GetCapabilities"},
        quote_via=lambda value, safe, encoding, errors: urllib.parse.quote(
            str(value), safe=safe, encoding=encoding, errors=errors
        ),
    )
    return f"{SOURCE_URL}?{query}"


def featureinfo_url(lat: float, lon: float) -> tuple[str, dict[str, float]]:
    box = point_bbox(lat, lon)
    params = {
        "SERVICE": "WMS",
        "VERSION": WMS_VERSION,
        "REQUEST": "GetFeatureInfo",
        "LAYERS": QUERY_LAYER,
        "QUERY_LAYERS": QUERY_LAYER,
        "CRS": CRS,
        "BBOX": bbox_parameter(box),
        "WIDTH": str(GRID_SIZE),
        "HEIGHT": str(GRID_SIZE),
        "I": str(PIXEL_I),
        "J": str(PIXEL_J),
        "INFO_FORMAT": "text/plain",
        "FEATURE_COUNT": "1",
    }
    query = urllib.parse.urlencode(
        params,
        quote_via=lambda value, safe, encoding, errors: urllib.parse.quote(
            str(value), safe=f"{safe},", encoding=encoding, errors=errors
        ),
    )
    return f"{SOURCE_URL}?{query}", box


def load_layers(fixture: str | None) -> tuple[list[dict[str, object]], str, str]:
    if fixture:
        payload = read_fixture(fixture, CAPABILITIES_BYTE_CAP)
        request_url = SOURCE_URL
    else:
        request_url = capabilities_url()
        payload, content_type = fetch_official(request_url, CAPABILITIES_BYTE_CAP, "text/xml, application/xml")
        if "xml" not in content_type.lower() and not payload.lstrip().startswith(b"<?xml"):
            raise SkillError(6, "GetCapabilities content type was not XML")
    layers, axis = parse_capabilities(payload)
    return layers, axis, request_url


def load_velocity(lat: float, lon: float, fixture: str | None) -> tuple[dict[str, object], dict[str, float], str]:
    box = point_bbox(lat, lon)
    if fixture:
        payload = read_fixture(fixture, FEATUREINFO_BYTE_CAP)
        request_url = SOURCE_URL
        text = payload.decode("utf-8")
    else:
        request_url, box = featureinfo_url(lat, lon)
        payload, content_type = fetch_official(request_url, FEATUREINFO_BYTE_CAP, "text/plain")
        if content_type and "text/plain" not in content_type.lower() and b"ServiceException" not in payload:
            raise SkillError(6, "GetFeatureInfo content type was not text/plain")
        text = payload.decode("utf-8")
    parsed = parse_feature_info(text)
    return parsed, box, request_url


def velocity_record(
    parsed: dict[str, object],
    box: dict[str, float],
    lat: float,
    lon: float,
    retrieved_at: str,
) -> dict[str, object]:
    return {
        "query_layer": QUERY_LAYER,
        "feature_type": parsed["feature_type"],
        "state": parsed["state"],
        "geschwindigkeit": parsed["geschwindigkeit"],
        "geschwindigkeit_text": parsed["geschwindigkeit_text"],
        "no_data_reason": parsed["no_data_reason"],
        "source_token": parsed["source_token"],
        "crs": CRS,
        "crs_axis_order": CRS_AXIS_ORDER,
        "wms_version": WMS_VERSION,
        "lat": lat,
        "lon": lon,
        "bbox": box,
        "width": GRID_SIZE,
        "height": GRID_SIZE,
        "i": PIXEL_I,
        "j": PIXEL_J,
        "attribution": attribution(retrieved_at),
    }


def emit_success(results: list[object], meta: dict[str, str], human: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result_envelope(results, meta), indent=2, ensure_ascii=False))
    else:
        print(human)
    return 0


def emit_error(exc: SkillError | InputError, as_json: bool) -> int:
    code = exc.code if isinstance(exc, SkillError) else 2
    message = str(exc)
    retry_after = exc.retry_after if isinstance(exc, SkillError) else None
    if as_json:
        print(
            json.dumps(
                error_envelope(code, message, source_meta(licence=None), retry_after=retry_after),
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"bkg-starkregen-wms: {message}", file=sys.stderr)
    return code


def format_layers(layers: list[dict[str, object]], axis: str) -> str:
    lines = [
        f"{len(layers)} named layers; EPSG:4326 axis order {axis}; no map download",
    ]
    for layer in layers:
        flag = layer["queryable"]
        marker = "queryable" if flag is True else "not queryable" if flag is False else "queryable unset"
        lines.append(f"{layer['name']}: {layer['title']} ({marker})")
    return "\n".join(lines)


def format_velocity(record: dict[str, object]) -> str:
    state = record["state"]
    feature = record["feature_type"] or "no feature"
    if state == "value" and record["geschwindigkeit"] == 0:
        detail = f"{record['geschwindigkeit_text']} (measured zero)"
    elif state == "value":
        detail = f"{record['geschwindigkeit_text']} (measured value)"
    elif record["no_data_reason"] == "sentinel":
        detail = f"no data; source sentinel {record['source_token']} is not a velocity and is not zero"
    else:
        detail = "no data; no Land feature at this point, so Geschwindigkeit is absent and is not zero"
    return (
        f"{feature}: Geschwindigkeit {detail}; "
        f"CRS {record['crs']} axis {record['crs_axis_order']}; "
        f"bbox {bbox_parameter(record['bbox'])}"
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="BKG Hinweiskarte Starkregengefahren WMS")
    sub = parser.add_subparsers(dest="command", required=True)
    layers = sub.add_parser("layers", help="list named WMS layers from GetCapabilities")
    layers.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    layers.add_argument("--fixture", help="read a local GetCapabilities file instead of the WMS")
    velocity = sub.add_parser("velocity", help="one extraordinary-event flow-velocity point")
    velocity.add_argument("--lat", required=True, type=parse_latitude, help="WGS84 latitude in decimal degrees")
    velocity.add_argument("--lon", required=True, type=parse_longitude, help="WGS84 longitude in decimal degrees")
    velocity.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    velocity.add_argument("--fixture", help="read a local GetFeatureInfo text/plain file instead of the WMS")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "layers":
            layers, axis, request_url = load_layers(args.fixture)
            meta = source_meta(source_url=request_url)
            meta["crs"] = CRS
            meta["crs_axis_order"] = axis
            meta["attribution"] = attribution(meta["retrieved_at"])
            human = format_layers(layers, axis)
            return emit_success(layers, meta, human, args.json)
        parsed, box, request_url = load_velocity(args.lat, args.lon, args.fixture)
        meta = source_meta(source_url=request_url)
        record = velocity_record(parsed, box, args.lat, args.lon, meta["retrieved_at"])
        return emit_success([record], meta, format_velocity(record), args.json)
    except (SkillError, InputError) as exc:
        return emit_error(exc, "--json" in argv)


if __name__ == "__main__":
    raise SystemExit(main())
