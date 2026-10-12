#!/usr/bin/env python3
"""Bounded reader for Paris permanent road-counter arc-hours."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from provenance import (
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    provenance,
    result_envelope,
)

HOST = "opendata.paris.fr"
DATASET_ID = "comptages-routiers-permanents"
ORIGIN = f"https://{HOST}"
DATASET_URL = f"{ORIGIN}/api/explore/v2.1/catalog/datasets/{DATASET_ID}"
RECORDS_URL = f"{DATASET_URL}/records"
LANDING_URL = f"{ORIGIN}/explore/dataset/{DATASET_ID}/information/"
PUBLISHER = "Direction de la Voirie et des Déplacements - Ville de Paris"
LICENCE_NAME = "Open Database License (ODbL)"
TIMEZONE_NAME = "Europe/Paris"
PARIS = ZoneInfo(TIMEZONE_NAME)
USER_AGENT = "thecolab-skills/paris-road-counters (+https://github.com/thecolab-ai/.skills)"
TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 1_048_576
MAX_JSON_DEPTH = 16
MAX_LIMIT = 20
MAX_HOUR_SPAN = 48
MAX_GEOMETRY_POSITIONS = 200
FIXTURE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,48}")
ARC_RE = re.compile(r"[0-9]{1,12}")
HOUR_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):00:00")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SELECT_FIELDS = (
    "iu_ac,libelle,t_1h,q,k,etat_trafic,etat_barre,iu_nd_amont,libelle_nd_amont,"
    "iu_nd_aval,libelle_nd_aval,date_debut,date_fin,geo_point_2d,geo_shape"
)
TRAFFIC_STATES = ("Inconnu", "Fluide", "Pré-saturé", "Saturé", "Bloqué")
ARC_STATES = ("Inconnu", "Ouvert", "Barré", "Invalide")
WARN_FLOW = (
    "q is the vehicle count at one loop during the hour ending at t_1h, "
    "in the amont to aval direction only. It is not a two-way total, "
    "not a vehicle-class split, and not a network total."
)
WARN_OCCUPANCY = (
    "k is the percent of that same hour the loop was occupied. "
    "It is not a vehicle count. Do not add k to q."
)
WARN_NULL = (
    "A null q or k is unobserved. It is not zero. "
    "The source states no small-count suppression rule."
)
WARN_HOUR = (
    "t_1h is the end of the counted hour in Europe/Paris, as published. "
    "derived_period_start is the 60 minutes before that stamp. "
    "The stamp is not a UTC label and not the start of the hour."
)
WARN_ODBL = (
    "Open Database License (ODbL): attribute the publisher. "
    "Share-alike applies to a database made from these records."
)


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


def source_meta(
    url: str,
    *,
    licence: str | None = None,
    latest_data: str | None = None,
    publisher: str = PUBLISHER,
) -> dict[str, str]:
    return provenance(url, publisher, licence=licence, latest_data=latest_data)


def licence_text(name: str, url: str | None) -> str:
    if url:
        return f"{name} {url}"
    return name


def wants_machine_output(argv: list[str], args: argparse.Namespace | None = None) -> bool:
    if args is not None and getattr(args, "format", "json") == "geojson":
        return True
    if "--json" in argv:
        return True
    for index, item in enumerate(argv):
        if item == "--format=geojson":
            return True
        if item == "--format" and index + 1 < len(argv) and argv[index + 1] == "geojson":
            return True
    return False


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def parse_arc(value: str) -> str:
    if not ARC_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("--arc must be a 1 to 12 digit iu_ac, without spaces or signs")
    return value


def parse_hour(value: str) -> datetime:
    match = HOUR_RE.fullmatch(value)
    if match is None:
        raise argparse.ArgumentTypeError(
            "hour filters must be Europe/Paris hour-ending stamps YYYY-MM-DDTHH:00:00, without a UTC offset"
        )
    year, month, day, hour = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, hour)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("hour filter is not a real calendar hour") from exc


def check_hour_window(start: datetime | None, end: datetime | None) -> None:
    if (start is None) ^ (end is None):
        raise InputError("pass both --from and --to, or neither; an open-ended hour range is not accepted")
    if start is None or end is None:
        return
    if end < start:
        raise InputError("--to is earlier than --from")
    span = int((end - start).total_seconds() // 3600) + 1
    if span > MAX_HOUR_SPAN:
        raise InputError(f"hour window covers {span} hour-ending stamps; the maximum is {MAX_HOUR_SPAN}")


def format_coord(value: float) -> str:
    text = format(value, ".8f").rstrip("0").rstrip(".")
    return text if text not in {"", "-0"} else "0"


def records_query(args: argparse.Namespace) -> str:
    clauses: list[str] = []
    if args.arc is not None:
        clauses.append(f'iu_ac="{args.arc}"')
    if args.flow == "observed":
        clauses.append("q is not null")
    elif args.flow == "missing":
        clauses.append("q is null")
    if args.traffic_state is not None:
        clauses.append(f'etat_trafic="{args.traffic_state}"')
    if args.arc_state is not None:
        clauses.append(f'etat_barre="{args.arc_state}"')
    if args.from_hour is not None and args.to_hour is not None:
        start = args.from_hour.strftime("%Y-%m-%dT%H:00:00")
        end = args.to_hour.strftime("%Y-%m-%dT%H:00:00")
        clauses.append(f"t_1h>=date'{start}' and t_1h<=date'{end}'")
    if args.bbox is not None:
        min_lon, min_lat, max_lon, max_lat = args.bbox
        # Explore v2.1 in_bbox is south, west, north, east. CLI --bbox stays lon, lat.
        clauses.append(
            "in_bbox(geo_point_2d, "
            f"{format_coord(min_lat)}, {format_coord(min_lon)}, "
            f"{format_coord(max_lat)}, {format_coord(max_lon)})"
        )
    params = {
        "limit": str(args.limit),
        "timezone": TIMEZONE_NAME,
        "select": SELECT_FIELDS,
        "order_by": "t_1h desc",
    }
    if clauses:
        params["where"] = " and ".join(clauses)
    return f"{RECORDS_URL}?{urllib.parse.urlencode(params)}"


def assert_allowed_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or host != HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise UnsafeError("refusing a request outside https://opendata.paris.fr")


class HostGuard(urllib.request.HTTPRedirectHandler):
    max_redirections = 2
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_allowed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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


def decode_body(raw: bytes, content_encoding: str | None) -> str:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpstreamError("upstream response exceeds the safety cap")
    encoded = (content_encoding or "").lower()
    if "gzip" in encoded or raw.startswith(b"\x1f\x8b"):
        try:
            decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
            raw = decompressor.decompress(raw, MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES or decompressor.unconsumed_tail or not decompressor.eof:
                raise UpstreamError("upstream response exceeds the safety cap")
        except UpstreamError:
            raise
        except (zlib.error, gzip.BadGzipFile, OSError, EOFError) as exc:
            raise SchemaError("upstream returned an unreadable response body") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError("upstream returned a response that is not UTF-8") from exc


def parse_json_document(text: str) -> Any:
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError("upstream JSON exceeds the supported nesting depth") from exc
    except ValueError as exc:
        raise SchemaError("upstream returned malformed or truncated JSON") from exc


def _reject_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant {value}")


def live_get(url: str) -> tuple[int, str]:
    assert_allowed_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(HostGuard)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            assert_allowed_url(final_url)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            encoding = response.headers.get("Content-Encoding")
            status = getattr(response, "status", 200)
    except UnsafeError:
        raise
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
        status = exc.code
        exc.close()
        if status == 429:
            detail = f"network error: rate_limited: retry_after={retry_after}: HTTP 429"
            raise BlockedError(detail, retry_after=retry_after if isinstance(retry_after, str) else None)
        if status in {401, 403, 451}:
            raise BlockedError(f"network error: blocked: HTTP {status}")
        if status in {408, 500, 502, 503, 504, 404}:
            raise UpstreamError(f"upstream unavailable (HTTP {status})")
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    except TimeoutError as exc:
        raise UpstreamError("network error: source request timed out") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            raise UpstreamError("network error: source request timed out") from exc
        raise UpstreamError(f"upstream unavailable: {reason}") from exc
    text = decode_body(raw, encoding)
    return status, text


def fixture_path(name: str):
    if not FIXTURE_RE.fullmatch(name):
        raise InputError("fixture name is not allowed")
    from pathlib import Path

    root = (Path(__file__).resolve().parent.parent / "tests" / "fixtures").resolve()
    path = (root / f"{name}.json").resolve()
    if path.parent != root or not path.is_file():
        raise InputError("fixture is not available")
    return path


def load_fixture_steps(name: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(fixture_path(name).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError("fixture JSON is malformed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list) or not payload["steps"]:
        raise InputError("fixture is not a response fixture")
    steps: list[dict[str, Any]] = []
    for step in payload["steps"]:
        if not isinstance(step, dict):
            raise InputError("fixture is not a response fixture")
        steps.append(step)
    return steps


def step_response(step: dict[str, Any]) -> tuple[int, str]:
    transport = step.get("transport")
    if transport == "off_host_redirect":
        raise UnsafeError("refusing off-host redirect; requests stay on opendata.paris.fr")
    if transport == "timeout":
        raise UpstreamError("network error: source request timed out")
    if transport == "rate_limited":
        retry_after = step.get("retry_after")
        retry_text = retry_after if isinstance(retry_after, str) else None
        raise BlockedError(
            f"network error: rate_limited: retry_after={retry_text}: HTTP 429",
            retry_after=retry_text,
        )
    if transport == "unavailable":
        status = step.get("http_status", 503)
        if isinstance(status, bool) or not isinstance(status, int):
            raise InputError("fixture is not a response fixture")
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    status = step.get("http_status", 200)
    if isinstance(status, bool) or not isinstance(status, int):
        raise InputError("fixture is not a response fixture")
    if "body_raw" in step:
        body = step.get("body_raw")
        if not isinstance(body, str):
            raise InputError("fixture is not a response fixture")
        return status, body
    if "body" in step:
        return status, json.dumps(step["body"])
    raise InputError("fixture is not a response fixture")


class ResponseSource:
    def __init__(self, steps: list[dict[str, Any]] | None):
        self.steps = steps
        self.index = 0

    def get(self, url: str) -> tuple[int, str]:
        assert_allowed_url(url)
        if self.steps is None:
            return live_get(url)
        if self.index >= len(self.steps):
            raise InputError("fixture is missing a response step")
        step = self.steps[self.index]
        self.index += 1
        return step_response(step)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{label} was not a JSON object")
    return value


def optional_text(record: dict[str, Any], field: str) -> str | None:
    if field not in record or record[field] is None:
        return None
    value = record[field]
    if not isinstance(value, str):
        raise SchemaError(f"{field} was not a string")
    return value


def require_text(record: dict[str, Any], field: str) -> str:
    value = optional_text(record, field)
    if value is None or not value.strip():
        raise SchemaError(f"{field} was missing")
    return value


def optional_date(record: dict[str, Any], field: str) -> str | None:
    value = optional_text(record, field)
    if value is None:
        return None
    if DATE_RE.fullmatch(value) is None:
        raise SchemaError(f"{field} was not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in value.split("-"))
    try:
        datetime(year, month, day)
    except ValueError as exc:
        raise SchemaError(f"{field} was not a real date") from exc
    return value


def finite_number_or_null(value: Any, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SchemaError(f"{field} was not a finite number or null")
    return value


def occupancy_band(k: float | int) -> str | None:
    """Published 2019 notice bands. The lower edge belongs to the higher band."""
    if k < 0:
        return None
    if k < 15:
        return "Fluide"
    if k < 30:
        return "Pré-saturé"
    if k < 50:
        return "Saturé"
    return "Bloqué"


def parse_hour_ending(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchemaError("t_1h was not an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchemaError("t_1h had no timezone offset; refusing to label it as UTC or Europe/Paris")
    paris_offset = parsed.astimezone(PARIS).utcoffset()
    if parsed.utcoffset() != paris_offset:
        raise SchemaError("t_1h offset does not match Europe/Paris; refusing to relabel it")
    return parsed


def geometry_from_shape(shape: Any) -> dict[str, Any] | None:
    if shape is None:
        return None
    if not isinstance(shape, dict):
        raise SchemaError("geo_shape was not an object")
    geometry = shape.get("geometry") if shape.get("type") == "Feature" else shape
    if geometry is None:
        return None
    if not isinstance(geometry, dict):
        raise SchemaError("geo_shape geometry was not an object")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind not in {"LineString", "MultiLineString", "Point"}:
        raise SchemaError("geo_shape used an unsupported geometry type")
    positions = list(_positions(kind, coordinates))
    if len(positions) > MAX_GEOMETRY_POSITIONS:
        raise SchemaError("geo_shape exceeds the coordinate cap")
    if kind == "LineString" and len(positions) < 2:
        raise SchemaError("geo_shape LineString had fewer than two positions")
    if kind == "Point" and len(positions) != 1:
        raise SchemaError("geo_shape Point was not one position")
    return {"type": kind, "coordinates": coordinates}


def _positions(kind: str, coordinates: Any):
    if kind == "Point":
        yield from _one_position(coordinates)
        return
    if kind == "LineString":
        if not isinstance(coordinates, list):
            raise SchemaError("geo_shape coordinates were not a list")
        for position in coordinates:
            yield from _one_position(position)
        return
    if not isinstance(coordinates, list):
        raise SchemaError("geo_shape coordinates were not a list")
    for line in coordinates:
        if not isinstance(line, list):
            raise SchemaError("geo_shape coordinates were not a list")
        for position in line:
            yield from _one_position(position)


def _one_position(position: Any):
    if (
        not isinstance(position, list)
        or len(position) < 2
        or isinstance(position[0], bool)
        or isinstance(position[1], bool)
        or not isinstance(position[0], (int, float))
        or not isinstance(position[1], (int, float))
        or not math.isfinite(position[0])
        or not math.isfinite(position[1])
        or not -180 <= position[0] <= 180
        or not -90 <= position[1] <= 90
    ):
        raise SchemaError("geo_shape position was not WGS84 longitude then latitude")
    yield position


def point_geometry(point: Any) -> dict[str, Any] | None:
    if point is None:
        return None
    if not isinstance(point, dict):
        raise SchemaError("geo_point_2d was not an object")
    lon = point.get("lon")
    lat = point.get("lat")
    if isinstance(lon, bool) or isinstance(lat, bool) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise SchemaError("geo_point_2d was not longitude and latitude")
    if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise SchemaError("geo_point_2d was outside WGS84 bounds")
    return {"type": "Point", "coordinates": [lon, lat]}


def normalise_record(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    iu_ac = require_text(raw, "iu_ac")
    stamp = require_text(raw, "t_1h")
    observed = parse_hour_ending(stamp)
    flow = finite_number_or_null(raw.get("q"), "q")
    occupancy = finite_number_or_null(raw.get("k"), "k")
    traffic = require_text(raw, "etat_trafic")
    closure = require_text(raw, "etat_barre")
    amont = optional_text(raw, "libelle_nd_amont")
    aval = optional_text(raw, "libelle_nd_aval")
    date_debut = optional_date(raw, "date_debut")
    date_fin = optional_date(raw, "date_fin")
    point = raw.get("geo_point_2d")
    point_geo = point_geometry(point)
    geometry = geometry_from_shape(raw.get("geo_shape")) or point_geo
    lon = lat = None
    if isinstance(point, dict) and point_geo is not None:
        lon, lat = point_geo["coordinates"]
    notes: list[str] = []
    if traffic in TRAFFIC_STATES and traffic != "Inconnu" and occupancy is not None:
        band = occupancy_band(occupancy)
        if band != traffic:
            notes.append("band")
    if occupancy is not None and (occupancy < 0 or occupancy > 100):
        notes.append("occupancy-range")
    if flow is not None and flow < 0:
        notes.append("negative-flow")
    reference_ended = False
    if date_fin is not None and date_fin < observed.date().isoformat():
        reference_ended = True
    direction = None
    if amont or aval:
        direction = f"{amont or ''} -> {aval or ''}"
    record = {
        "iu_ac": iu_ac,
        "libelle": optional_text(raw, "libelle"),
        "t_1h": stamp,
        "derived_period_start": (observed - timedelta(hours=1)).isoformat(timespec="seconds"),
        "hour_ending_timezone": TIMEZONE_NAME,
        "q_vehicles_per_hour": flow,
        "q_observed": flow is not None,
        "k_occupancy_percent": occupancy,
        "k_observed": occupancy is not None,
        "etat_trafic": traffic,
        "etat_barre": closure,
        "iu_nd_amont": optional_text(raw, "iu_nd_amont"),
        "libelle_nd_amont": amont,
        "iu_nd_aval": optional_text(raw, "iu_nd_aval"),
        "libelle_nd_aval": aval,
        "direction": direction,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "reference_date_fin_before_observation": reference_ended,
        "lon": lon,
        "lat": lat,
    }
    return record, geometry, notes


def interpret_metadata(status: int, text: str) -> dict[str, Any]:
    if status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    payload = require_object(parse_json_document(text), "dataset metadata")
    if payload.get("dataset_id") != DATASET_ID:
        raise SchemaError("dataset_id was not comptages-routiers-permanents")
    metas = require_object(payload.get("metas"), "metas")
    default = require_object(metas.get("default"), "metas.default")
    dcat = metas.get("dcat")
    licence = default.get("license")
    licence_url = default.get("license_url")
    publisher = default.get("publisher")
    timezone_name = default.get("timezone")
    title = default.get("title")
    if not isinstance(licence, str) or not licence.strip():
        raise SchemaError("source licence was not stated")
    if licence != LICENCE_NAME or not isinstance(licence_url, str) or not _odbl_url(licence_url):
        raise UnsafeError(
            "refusing records because the source licence is not confirmed ODbL: "
            f"{licence!r} {licence_url!r}"
        )
    if not isinstance(publisher, str) or not publisher.strip():
        raise SchemaError("source publisher was not stated")
    if timezone_name != TIMEZONE_NAME:
        raise SchemaError(f"source timezone was {timezone_name!r}; refusing to relabel hours as Europe/Paris")
    if not isinstance(title, str) or not title.strip():
        raise SchemaError("source title was not stated")
    latest = default.get("data_processed")
    if not isinstance(latest, str) or not latest.strip():
        latest = default.get("modified")
    if not isinstance(latest, str) or not latest.strip():
        raise SchemaError("source data_processed timestamp was not stated")
    records_count = default.get("records_count")
    if isinstance(records_count, bool) or not isinstance(records_count, int) or records_count < 0:
        raise SchemaError("source records_count was not a non-negative integer")
    granularity = None
    if isinstance(dcat, dict) and isinstance(dcat.get("granularity"), str):
        granularity = dcat["granularity"]
    geometry_types = default.get("geometry_types")
    if geometry_types is not None and (
        not isinstance(geometry_types, list) or not all(isinstance(item, str) for item in geometry_types)
    ):
        raise SchemaError("source geometry_types was not a list of strings")
    return {
        "dataset_id": DATASET_ID,
        "title": title,
        "publisher": publisher,
        "licence": licence,
        "licence_url": licence_url,
        "timezone": timezone_name,
        "temporal_granularity": granularity,
        "records_count": records_count,
        "records_count_meaning": "Catalogue count of arc-hour rows. Not a vehicle total and not the number of rows returned.",
        "geometry_types": geometry_types,
        "data_processed": latest,
        "licence_text": licence_text(licence, licence_url),
    }


def _odbl_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme in {"http", "https"}
        and host in {"opendatacommons.org", "www.opendatacommons.org"}
        and parsed.path.rstrip("/").lower() == "/licenses/odbl"
        and parsed.username is None
        and parsed.password is None
    )


def interpret_records(status: int, text: str, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
    if status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    payload = require_object(parse_json_document(text), "records response")
    rows = payload.get("results")
    total = payload.get("total_count")
    if not isinstance(rows, list):
        raise SchemaError("results was not a list")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise SchemaError("total_count was not a non-negative integer")
    if total == 0 and rows:
        raise SchemaError("total_count was 0 but results were returned")
    if total > 0 and not rows:
        raise SchemaError("total_count was positive but results were empty")
    if len(rows) > limit:
        raise SchemaError("results exceeded the requested limit")
    records: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    notes: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SchemaError("result was not an object")
        record, geometry, row_notes = normalise_record(row)
        records.append(record)
        features.append({"type": "Feature", "geometry": geometry, "properties": record})
        notes.extend(row_notes)
        if record["etat_barre"] != "Ouvert":
            notes.append("closed")
        if record["reference_date_fin_before_observation"]:
            notes.append("reference-date")
    return records, features, notes, total


def count_warnings(total: int, returned: int, notes: list[str]) -> list[str]:
    warnings = [
        WARN_FLOW,
        WARN_OCCUPANCY,
        WARN_NULL,
        WARN_HOUR,
        WARN_ODBL,
        f"Catalogue matched {total} arc-hours; returned {returned}. This is not a vehicle total.",
    ]
    if "band" in notes:
        warnings.append(
            "k is outside the published band for etat_trafic on at least one row. Both values are preserved."
        )
    if "occupancy-range" in notes:
        warnings.append("k is outside 0 to 100 percent on at least one row. The source value is preserved.")
    if "negative-flow" in notes:
        warnings.append("q is negative on at least one row. The source value is preserved and is not coerced to zero.")
    if "closed" in notes:
        warnings.append(
            "At least one arc is not marked Ouvert. Barré, Invalide, Inconnu, or any other closure state is not an open-road count."
        )
    if "reference-date" in notes:
        warnings.append(
            "date_fin is the reference availability date, not the count hour. It is earlier than t_1h on at least one row and was not used to relabel the hour."
        )
    return warnings


def emit_success(
    results: list[dict[str, Any]],
    meta: dict[str, str],
    lines: list[str],
    *,
    as_json: bool,
    as_geojson: bool,
    features: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> int:
    if as_geojson:
        payload = geojson_envelope(features or [], meta)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif as_json:
        payload = result_envelope(results, meta)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)
    return 0


def emit_error(
    code: int,
    message: str,
    meta: dict[str, str],
    *,
    as_json: bool,
    retry_after: str | None = None,
) -> int:
    if as_json:
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"paris-road-counters: {message}", file=sys.stderr)
    return code


def human_dataset(info: dict[str, Any], url: str) -> list[str]:
    lines = [
        info["title"],
        f"Publisher: {info['publisher']}",
        f"Licence: {info['licence_text']}",
        f"Timezone: {info['timezone']}",
        f"Granularity: {info['temporal_granularity'] or 'not stated'}",
        f"Catalogue arc-hours: {info['records_count']} ({info['records_count_meaning']})",
        f"Data processed: {info['data_processed']}",
        "Coverage described by the publisher: rolling 13 months, published the next day (J-1). This command does not download that window.",
        f"Source: {url}",
    ]
    return lines


def human_counts(records: list[dict[str, Any]], warnings: list[str], url: str) -> list[str]:
    lines = [f"Paris permanent counters ({len(records)} arc-hour{'s' if len(records) != 1 else ''})"]
    for warning in warnings:
        lines.append(warning)
    if not records:
        lines.append("No arc-hours matched.")
    for record in records:
        flow = "unobserved (not zero)" if not record["q_observed"] else f"{record['q_vehicles_per_hour']} vehicles in the hour"
        occupancy = "unobserved (not zero)" if not record["k_observed"] else f"{record['k_occupancy_percent']} percent of the hour"
        lines.append(
            f"- arc {record['iu_ac']} {record['libelle'] or ''}".rstrip()
        )
        lines.append(f"  hour ending {record['t_1h']} ({record['hour_ending_timezone']}); starts {record['derived_period_start']}")
        lines.append(f"  direction: {record['direction'] or 'not stated'}")
        lines.append(f"  flow q: {flow}")
        lines.append(f"  occupancy k: {occupancy}")
        lines.append(f"  traffic state: {record['etat_trafic']}; arc state: {record['etat_barre']}")
    lines.append(f"Source: {url}")
    return lines


def dataset_meta(info: dict[str, Any], url: str) -> dict[str, str]:
    return source_meta(
        url,
        licence=info["licence_text"],
        latest_data=info["data_processed"],
        publisher=info["publisher"],
    )


def run_dataset(source: ResponseSource, *, as_json: bool) -> int:
    status, text = source.get(DATASET_URL)
    info = interpret_metadata(status, text)
    meta = dataset_meta(info, DATASET_URL)
    result = {
        key: info[key]
        for key in (
            "dataset_id",
            "title",
            "publisher",
            "licence",
            "licence_url",
            "timezone",
            "temporal_granularity",
            "records_count",
            "records_count_meaning",
            "geometry_types",
            "data_processed",
        )
    }
    warnings = [
        WARN_ODBL,
        "Historical counters and the Lambert-93 referential are different datasets and are not read.",
        "records_count is the catalogue size. This command returns no counter rows.",
    ]
    return emit_success(
        [result],
        meta,
        human_dataset(info, DATASET_URL),
        as_json=as_json,
        as_geojson=False,
        warnings=warnings,
    )


def run_counts(args: argparse.Namespace, source: ResponseSource, *, as_json: bool, as_geojson: bool) -> int:
    check_hour_window(args.from_hour, args.to_hour)
    url = records_query(args)
    meta_status, meta_text = source.get(DATASET_URL)
    info = interpret_metadata(meta_status, meta_text)
    status, text = source.get(url)
    records, features, notes, total = interpret_records(status, text, args.limit)
    warnings = count_warnings(total, len(records), notes)
    meta = dataset_meta(info, url)
    return emit_success(
        records,
        meta,
        human_counts(records, warnings, url),
        as_json=as_json,
        as_geojson=as_geojson,
        features=features,
        warnings=warnings,
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Paris permanent road counters (comptages routiers permanents)")
    sub = parser.add_subparsers(dest="command", required=True)
    dataset = sub.add_parser("dataset", help="read catalogue licence, timezone, and row count for this dataset only")
    dataset.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    dataset.add_argument("--fixture", help="replay a local fixture instead of the network")
    counts = sub.add_parser("counts", help="read at most 20 arc-hours of flow and occupancy")
    counts.add_argument("--limit", type=parse_limit, required=True, help=f"rows to return, from 1 to {MAX_LIMIT}")
    counts.add_argument("--arc", type=parse_arc, help="exact iu_ac")
    counts.add_argument("--from", dest="from_hour", type=parse_hour, help="first Europe/Paris hour-ending stamp, YYYY-MM-DDTHH:00:00")
    counts.add_argument("--to", dest="to_hour", type=parse_hour, help="last Europe/Paris hour-ending stamp, YYYY-MM-DDTHH:00:00")
    counts.add_argument("--flow", choices=("any", "observed", "missing"), default="any", help="filter on whether q was counted")
    counts.add_argument("--traffic-state", choices=TRAFFIC_STATES, help="exact published etat_trafic label")
    counts.add_argument("--arc-state", choices=ARC_STATES, help="exact published etat_barre label")
    counts.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    counts.add_argument("--fixture", help="replay a local fixture instead of the network")
    add_spatial_arguments(counts)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        machine = wants_machine_output(argv, args)
        steps = load_fixture_steps(args.fixture) if args.fixture else None
        source = ResponseSource(steps)
        if args.command == "dataset":
            if getattr(args, "format", None) == "geojson":
                raise InputError("dataset has no geometry output")
            return run_dataset(source, as_json=machine)
        return run_counts(args, source, as_json=machine, as_geojson=args.format == "geojson")
    except InputError as exc:
        return emit_error(2, str(exc), source_meta(LANDING_URL), as_json=wants_machine_output(argv, args))
    except BlockedError as exc:
        return emit_error(
            4,
            str(exc),
            source_meta(LANDING_URL),
            as_json=wants_machine_output(argv, args),
            retry_after=exc.retry_after,
        )
    except UpstreamError as exc:
        return emit_error(5, str(exc), source_meta(LANDING_URL), as_json=wants_machine_output(argv, args))
    except SchemaError as exc:
        return emit_error(6, str(exc), source_meta(LANDING_URL), as_json=wants_machine_output(argv, args))
    except UnsafeError as exc:
        return emit_error(7, str(exc), source_meta(LANDING_URL), as_json=wants_machine_output(argv, args))


if __name__ == "__main__":
    raise SystemExit(main())
