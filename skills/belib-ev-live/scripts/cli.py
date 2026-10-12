#!/usr/bin/env python3
"""Live Belib electric-vehicle charge-point availability in Paris.

The feed is the Ville de Paris OpenDataSoft dataset, not a New Zealand source.
Every live command re-reads the dataset licence and refuses records unless it is
still the Open Database License (ODbL).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from provenance import (
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    provenance,
    result_envelope,
)

ALLOWED_HOST = "parisdata.opendatasoft.com"
DATASET_ID = "belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel"
DATASET_URL = (
    "https://parisdata.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    + DATASET_ID
)
RECORDS_URL = DATASET_URL + "/records"
SOURCE_URL = RECORDS_URL
EXPECTED_LICENCE = "Open Database License (ODbL)"
OFFLINE_PUBLISHER = "Direction de la Voirie et des Déplacements - Ville de Paris"
USER_AGENT = "thecolab-belib-ev-live/1.0 (+https://github.com/thecolab-ai/.skills)"
SELECT_FIELDS = (
    "id_pdc,statut_pdc,url_description_pdc,last_updated,arrondissement,"
    "adresse_station,coordonneesxy,code_insee_commune"
)
PARIS_INSEE = "75056"
TIMEOUT_SECONDS = 15
MAX_BYTES = 262144
MAX_LIMIT = 20
CURRENT_MAX_AGE_SECONDS = 3 * 60 * 60
FUTURE_SKEW_SECONDS = 15 * 60
POINT_ID_PATTERN = re.compile(r"^[A-Za-z0-9*]{4,80}$")
RECORD_KEYS = {
    "id_pdc",
    "statut_pdc",
    "url_description_pdc",
    "last_updated",
    "arrondissement",
    "adresse_station",
    "coordonneesxy",
    "code_insee_commune",
}
SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillError(Exception):
    """A typed CLI failure with a stable exit code."""

    def __init__(self, message: str, code: int, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class InputError(ValueError):
    """An argparse failure emitted as a JSON error envelope when requested."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow only HTTPS redirects that stay on the official host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        enforce_https_allowlist(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def enforce_https_allowlist(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != ALLOWED_HOST:
        raise SkillError("redirect to a host outside the allowlist is rejected", 7)


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 20")
    number = int(value)
    if number > MAX_LIMIT:
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 20")
    return number


def parse_point_id(value: str) -> str:
    if not POINT_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("--id must be a Belib charge-point id, not a URL")
    return value


def wants_machine(argv: list[str]) -> bool:
    if "--json" in argv:
        return True
    for index, item in enumerate(argv):
        if item == "--format=geojson":
            return True
        if item == "--format" and index + 1 < len(argv) and argv[index + 1] == "geojson":
            return True
    return False


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_source_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SkillError("availability record last_updated is missing", 6)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SkillError("availability record last_updated is not a timestamp", 6) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SkillError("availability record last_updated must include a timezone", 6)
    return parsed.astimezone(timezone.utc)


def attribution(publisher: str, licence: str) -> str:
    return (
        f"Contains Belib' live charge-point availability from {publisher}, "
        f"licensed under the {licence}."
    )


def source_meta(
    publisher: str,
    retrieved_at: str,
    licence: str | None = None,
    latest_data: str | None = None,
    total_count: int | None = None,
    current: bool | None = None,
    licence_url: str | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = provenance(
        SOURCE_URL,
        publisher,
        licence=licence,
        latest_data=latest_data,
        retrieved_at=retrieved_at,
    )
    if licence:
        meta["attribution"] = attribution(publisher, licence)
    if licence_url:
        meta["licence_url"] = licence_url
    if total_count is not None:
        meta["total_count"] = total_count
    if current is not None:
        meta["current"] = current
    return meta


def emit_error(
    code: int,
    message: str,
    machine: bool,
    retrieved_at: str,
    publisher: str = OFFLINE_PUBLISHER,
    licence: str | None = None,
    retry_after: str | None = None,
) -> None:
    if machine:
        print(json.dumps(
            error_envelope(
                code,
                message,
                source_meta(publisher, retrieved_at, licence=licence),
                retry_after=retry_after,
            ),
            indent=2,
            ensure_ascii=False,
        ))
        return
    print(f"belib-ev-live: {message}", file=sys.stderr)


def http_status_error(status: int, retry_after: str | None, body: bytes) -> SkillError | None:
    if status == 200:
        return None
    if status == 429:
        return SkillError("HTTP 429", 4, retry_after=retry_after)
    if status == 503 or status >= 500:
        return SkillError(f"HTTP {status}", 5)
    if status == 400:
        return SkillError("HTTP 400", 6)
    return SkillError(f"HTTP {status}", 5)


def read_bounded(response: Any) -> bytes:
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > MAX_BYTES:
        raise SkillError("response exceeded the 262144 byte cap", 6)
    body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise SkillError("response exceeded the 262144 byte cap", 6)
    encoding = (response.headers.get("Content-Encoding") or "").lower()
    if not encoding or encoding == "identity":
        return body
    if encoding != "gzip":
        raise SkillError("unsupported content encoding", 6)
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as handle:
        decoded = handle.read(MAX_BYTES + 1)
    if len(decoded) > MAX_BYTES:
        raise SkillError("response exceeded the 262144 byte cap", 6)
    return decoded


def decode_json_object(body: bytes) -> dict[str, Any]:
    if not body:
        raise SkillError("non-JSON or truncated JSON", 6)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillError("non-JSON or truncated JSON", 6) from exc
    if not isinstance(payload, dict):
        raise SkillError("non-JSON or truncated JSON", 6)
    return payload


def fetch_json(url: str) -> dict[str, Any]:
    enforce_https_allowlist(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        AllowlistRedirectHandler(),
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            enforce_https_allowlist(response.geturl())
            status = getattr(response, "status", 200)
            retry_after = response.headers.get("Retry-After")
            body = read_bounded(response)
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        try:
            body = exc.read(MAX_BYTES + 1)
        except Exception:
            body = b""
        failure = http_status_error(exc.code, retry_after, body)
        raise failure if failure else SkillError(f"HTTP {exc.code}", 5) from None
    except (TimeoutError, socket.timeout) as exc:
        raise SkillError("network error: source request timed out", 5) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise SkillError("network error: source request timed out", 5) from exc
        raise SkillError(f"network error: {exc.reason}", 5) from exc
    failure = http_status_error(status, retry_after, body)
    if failure:
        raise failure
    return decode_json_object(body)


def parse_licence(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    if payload.get("dataset_id") != DATASET_ID:
        raise SkillError("dataset metadata does not identify the Belib availability dataset", 6)
    metas = payload.get("metas")
    default = metas.get("default") if isinstance(metas, dict) else None
    if not isinstance(default, dict):
        raise SkillError("dataset metadata has no licence record", 6)
    licence = default.get("license")
    publisher = default.get("publisher")
    licence_url = default.get("license_url")
    if not isinstance(licence, str) or licence.strip() != EXPECTED_LICENCE:
        raise SkillError(
            "source licence is not Open Database License (ODbL); refusing to return records",
            7,
        )
    if not isinstance(publisher, str) or not publisher.strip():
        raise SkillError("dataset metadata has no publisher", 6)
    if licence_url is not None and (not isinstance(licence_url, str) or not licence_url.strip() or len(licence_url) > 200):
        raise SkillError("dataset metadata licence URL is not usable", 6)
    url = licence_url.strip() if isinstance(licence_url, str) else None
    return licence.strip(), publisher.strip(), url


def optional_text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SkillError(f"availability record {key} is not text", 6)
    return value


def parse_coordinates(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict) or set(value) != {"lon", "lat"}:
        raise SkillError("availability record coordonneesxy must contain lon and lat", 6)
    lon = value.get("lon")
    lat = value.get("lat")
    if isinstance(lon, bool) or isinstance(lat, bool) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise SkillError("availability record coordinates are not finite numbers", 6)
    if not (-180 <= float(lon) <= 180 and -90 <= float(lat) <= 90):
        raise SkillError("availability record coordinates are outside WGS84", 6)
    return float(lon), float(lat)


def parse_static_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != ALLOWED_HOST:
        raise SkillError("availability record description URL is outside the official host", 6)
    return value


def parse_record(record: Any, retrieved: datetime) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise SkillError("availability result is not an object", 6)
    unexpected = sorted(set(record) - RECORD_KEYS)
    if unexpected:
        raise SkillError("availability record has unsupported fields: " + ", ".join(unexpected), 6)
    point_id = record.get("id_pdc")
    status = record.get("statut_pdc")
    if not isinstance(point_id, str) or not POINT_ID_PATTERN.fullmatch(point_id):
        raise SkillError("availability record id_pdc is missing", 6)
    if not isinstance(status, str) or not status.strip():
        raise SkillError("availability record statut_pdc is missing", 6)
    updated = parse_source_time(record.get("last_updated"))
    longitude, latitude = parse_coordinates(record.get("coordonneesxy"))
    insee = record.get("code_insee_commune")
    if insee is not None and insee != PARIS_INSEE:
        raise SkillError("availability record code_insee_commune is not Paris 75056 or null", 6)
    age_seconds = (retrieved - updated).total_seconds()
    return {
        "id_pdc": point_id,
        "statut_pdc": status,
        "last_updated": record["last_updated"],
        "update_age_seconds": int(age_seconds),
        "arrondissement": optional_text(record, "arrondissement"),
        "adresse_station": optional_text(record, "adresse_station"),
        "code_insee_commune": insee,
        "longitude": longitude,
        "latitude": latitude,
        "static_description_url": parse_static_url(optional_text(record, "url_description_pdc")),
        "_updated": updated,
        "_age_seconds": age_seconds,
    }


def parse_records_payload(payload: dict[str, Any], limit: int, retrieved: datetime) -> tuple[list[dict[str, Any]], int | None]:
    unexpected = sorted(set(payload) - {"total_count", "results"})
    if unexpected:
        raise SkillError("availability payload has unsupported fields: " + ", ".join(unexpected), 6)
    results = payload.get("results")
    if not isinstance(results, list):
        raise SkillError("availability results is not an array", 6)
    if len(results) > limit:
        raise SkillError("response exceeded the requested row cap", 6)
    total_count = payload.get("total_count")
    if total_count is not None and (isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < len(results)):
        raise SkillError("availability total_count is inconsistent", 6)
    parsed = [parse_record(item, retrieved) for item in results]
    parsed.sort(key=lambda item: item["_updated"], reverse=True)
    return parsed[:limit], total_count


def is_current(records: list[dict[str, Any]]) -> bool:
    if not records:
        return False
    age = records[0]["_age_seconds"]
    return -FUTURE_SKEW_SECONDS <= age <= CURRENT_MAX_AGE_SECONDS


def require_current(records: list[dict[str, Any]]) -> None:
    if not records:
        raise SkillError("no availability records to assess freshness", 6)
    if not is_current(records):
        newest = records[0]
        raise SkillError(
            "availability is not current: newest last_updated "
            f"{newest['last_updated']} is {int(newest['_age_seconds'])} seconds from retrieval",
            7,
        )


def local_filter(records: list[dict[str, Any]], point_id: str | None, bbox: tuple[float, float, float, float] | None) -> list[dict[str, Any]]:
    selected = records
    if point_id:
        selected = [record for record in selected if record["id_pdc"] == point_id]
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        selected = [
            record for record in selected
            if record["longitude"] is not None
            and record["latitude"] is not None
            and min_lon <= record["longitude"] <= max_lon
            and min_lat <= record["latitude"] <= max_lat
        ]
    return selected


def build_records_url(limit: int, point_id: str | None, bbox: tuple[float, float, float, float] | None) -> str:
    filters: list[str] = []
    if point_id:
        filters.append(f'id_pdc="{point_id}"')
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        filters.append(
            "in_bbox(coordonneesxy, "
            f"{min_lat:.6f}, {min_lon:.6f}, {max_lat:.6f}, {max_lon:.6f})"
        )
    params = {
        "limit": str(limit),
        "order_by": "last_updated desc",
        "select": SELECT_FIELDS,
    }
    if filters:
        params["where"] = " and ".join(filters)
    return RECORDS_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def resolve_fixture(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = SKILL_DIR / path
    resolved = path.resolve()
    if not resolved.is_relative_to(SKILL_DIR):
        raise SkillError("fixture path must stay inside the skill directory", 2)
    if not resolved.is_file():
        raise SkillError("fixture not found", 2)
    return resolved


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError(f"fixture could not be read: {exc.strerror or 'read failed'}", 2) from exc
    return decode_json_object(text.encode("utf-8"))


def public_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hidden = {"_updated", "_age_seconds"}
    return [{key: value for key, value in record.items() if key not in hidden} for record in records]


def features_for(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for record in public_records(records):
        longitude = record["longitude"]
        latitude = record["latitude"]
        if longitude is None or latitude is None:
            geometry = None
        else:
            geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": record,
        })
    return features


def human_text(records: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = [
        "Belib' live charge-point availability in Paris",
        str(meta.get("attribution") or ""),
        f"Retrieved: {meta['retrieved_at']}",
    ]
    if meta.get("latest_data"):
        current = "current" if meta.get("current") else "not current"
        lines.append(f"Newest update: {meta['latest_data']} ({current})")
    if "total_count" in meta:
        lines.append(f"Matched: {meta['total_count']}")
    if not records:
        lines.append("No charge points matched.")
        return "\n".join(lines)
    for index, record in enumerate(records, start=1):
        has_location = record["latitude"] is not None and record["longitude"] is not None
        place = record.get("adresse_station") or record.get("arrondissement")
        if place is None:
            place = "Paris" if has_location else "location not published"
        coords = f" | {record['latitude']}, {record['longitude']}" if has_location else ""
        lines.append(
            f"{index}. {record['id_pdc']} | {record['statut_pdc']} | "
            f"updated {record['last_updated']} | age {record['update_age_seconds']}s | "
            f"{place}{coords}"
        )
    return "\n".join(lines)


def run_command(args: argparse.Namespace, retrieved_at: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    if args.fixture:
        payload = load_fixture(resolve_fixture(args.fixture))
        licence, publisher, licence_url = EXPECTED_LICENCE, OFFLINE_PUBLISHER, None
    else:
        licence, publisher, licence_url = parse_licence(fetch_json(DATASET_URL))
        payload = fetch_json(build_records_url(args.limit, args.id, args.bbox))
    records, total_count = parse_records_payload(payload, args.limit, retrieved)
    if args.fixture:
        records = local_filter(records, args.id, args.bbox)[: args.limit]
        if total_count is not None and (args.id or args.bbox):
            total_count = len(records)
    if args.require_current:
        require_current(records)
    current = is_current(records) if records else None
    latest = records[0]["last_updated"] if records else None
    meta = source_meta(
        publisher,
        retrieved_at,
        licence=licence,
        latest_data=latest,
        total_count=total_count,
        current=current,
        licence_url=licence_url,
    )
    return records, meta


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="belib-ev-live", description="Paris Belib live charge-point availability")
    sub = parser.add_subparsers(dest="command", required=True)
    availability = sub.add_parser("availability", help="read the newest Belib charge-point availability records")
    availability.add_argument("--limit", required=True, type=parse_limit, help="page size from 1 to 20, newest updates first")
    availability.add_argument("--id", type=parse_point_id, help="exact Belib charge-point id")
    availability.add_argument("--require-current", action="store_true", help="fail unless the newest returned update is within 3 hours")
    availability.add_argument("--fixture", help="offline records JSON inside this skill; skips the network")
    availability.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    add_spatial_arguments(availability)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = wants_machine(argv)
    retrieved_at = utc_now_text()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        emit_error(2, str(exc), machine, retrieved_at)
        return 2
    machine = machine or args.format == "geojson"
    try:
        records, meta = run_command(args, retrieved_at)
    except SkillError as exc:
        emit_error(
            exc.code,
            str(exc),
            machine,
            retrieved_at,
            retry_after=exc.retry_after,
        )
        return exc.code
    visible = public_records(records)
    if args.format == "geojson":
        print(json.dumps(geojson_envelope(features_for(records), meta), indent=2, ensure_ascii=False))
    elif args.json:
        print(json.dumps(result_envelope(visible, meta), indent=2, ensure_ascii=False))
    else:
        print(human_text(visible, meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
