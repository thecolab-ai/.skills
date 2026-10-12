#!/usr/bin/env python3
"""Read-only OpenStreetMap notes search for a small bounding box."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from provenance import error_envelope, geojson_envelope, parse_bbox, provenance, result_envelope

PUBLISHER = "OpenStreetMap contributors"
LICENCE = "Open Database License (ODbL) 1.0"
API_ORIGIN = "https://api.openstreetmap.org"
WEB_ORIGIN = "https://www.openstreetmap.org"
NOTES_COLLECTION = API_ORIGIN + "/api/0.6/notes.json"
ALLOWED_HOSTS = {"api.openstreetmap.org", "www.openstreetmap.org"}
USER_AGENT = "thecolab-osm-notes/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"
TIMEOUT_SECONDS = 15
MAX_BYTES = 262144
MAX_LIMIT = 20
MAX_SPAN_DEGREES = 0.05
MAX_CLOSED_DAYS = 7
TEXT_CAP = 2000
SKILL_DIR = Path(__file__).resolve().parents[1]
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$")
STATUSES = {"open", "closed", "hidden"}
ACTIONS = {"opened", "commented", "closed", "reopened", "hidden"}


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class SourceError(Exception):
    """A typed notes-command failure with a stable exit code."""

    def __init__(self, code: int, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class _NotesRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        if parsed.scheme != "https" or host not in ALLOWED_HOSTS or path != "/api/0.6/notes.json":
            raise SourceError(7, "refusing a redirect that is not the read-only notes collection")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def wants_machine_output(argv: list[str]) -> bool:
    if "--json" in argv or "--format=geojson" in argv:
        return True
    if "--format" in argv:
        index = argv.index("--format")
        return index + 1 < len(argv) and argv[index + 1] == "geojson"
    return False


def source_meta(source_url: str = NOTES_COLLECTION, latest_data: str | None = None) -> dict[str, str]:
    return provenance(source_url, PUBLISHER, licence=LICENCE, latest_data=latest_data)


def format_coord(value: float) -> str:
    text = format(value, ".7f").rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def request_url(bbox: tuple[float, float, float, float], limit: int, closed_days: int) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    box = ",".join(format_coord(part) for part in (min_lon, min_lat, max_lon, max_lat))
    return f"{NOTES_COLLECTION}?bbox={box}&limit={limit}&closed={closed_days}"


def check_span(bbox: tuple[float, float, float, float]) -> None:
    min_lon, min_lat, max_lon, max_lat = bbox
    if max_lon - min_lon > MAX_SPAN_DEGREES + 1e-9 or max_lat - min_lat > MAX_SPAN_DEGREES + 1e-9:
        raise SourceError(2, "--bbox span must be at most 0.05 degrees in longitude and in latitude")


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"--limit must be an integer from 1 to {MAX_LIMIT}")
    return number


def parse_closed_days(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(
            f"--closed-days must be an integer from 0 to {MAX_CLOSED_DAYS}"
        )
    number = int(value)
    if not 0 <= number <= MAX_CLOSED_DAYS:
        raise argparse.ArgumentTypeError(
            f"--closed-days must be an integer from 0 to {MAX_CLOSED_DAYS}; "
            "all-history closed=-1 is not available"
        )
    return number


def resolve_fixture(value: str) -> Path:
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, SKILL_DIR / raw]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise SourceError(2, "fixture path must stay inside the skill directory") from exc
        try:
            resolved.relative_to(SKILL_DIR)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    raise SourceError(2, "fixture path must stay inside the skill directory")


def _read_capped(stream: Any) -> bytes:
    body = stream.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise SourceError(5, "network error: notes response exceeded the 262144 byte cap")
    return body


def _header_map(headers: Any) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise SourceError(7, "refusing a notes request that is not on the OpenStreetMap API")
    if parsed.path.rstrip("/") != "/api/0.6/notes.json":
        raise SourceError(7, "refusing a request that is not the read-only notes collection")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NotesRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() not in ALLOWED_HOSTS:
                raise SourceError(7, "refusing a notes response from outside the OpenStreetMap API")
            if final.path.rstrip("/") != "/api/0.6/notes.json":
                raise SourceError(7, "refusing a response that is not the read-only notes collection")
            return response.status, _header_map(response.headers), _read_capped(response)
    except SourceError:
        raise
    except TimeoutError:
        raise SourceError(5, "network error: source request timed out") from None
    except urllib.error.HTTPError as exc:
        try:
            body = _read_capped(exc)
        except SourceError:
            raise
        return exc.code, _header_map(exc.headers), body
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            raise SourceError(5, "network error: source request timed out") from None
        detail = str(reason)
        if len(detail) > 160 or "://" in detail or "@" in detail:
            detail = "notes API request failed"
        raise SourceError(5, f"network error: {detail}") from None


def load_fixture(path: Path) -> tuple[int, dict[str, str], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise SourceError(2, "fixture exceeds the 262144 byte cap")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 200, {"content-type": "application/json"}, raw
    if isinstance(payload, dict) and set(payload) == {"_http"}:
        http = payload["_http"]
        if not isinstance(http, dict):
            raise SourceError(6, "fixture HTTP wrapper must be an object")
        status = http.get("status")
        if isinstance(status, bool) or not isinstance(status, int):
            raise SourceError(6, "fixture HTTP status must be an integer")
        headers = http.get("headers") or {}
        if not isinstance(headers, dict):
            raise SourceError(6, "fixture HTTP headers must be an object")
        body = http.get("body", "")
        if isinstance(body, (dict, list)):
            encoded = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            encoded = body.encode("utf-8")
        else:
            raise SourceError(6, "fixture HTTP body must be text or JSON")
        normalised = {str(key).lower(): str(value) for key, value in headers.items()}
        return status, normalised, encoded
    return 200, {"content-type": "application/json"}, raw


def _fail_status(status: int, headers: dict[str, str]) -> None:
    retry_after = headers.get("retry-after")
    if status in {401, 403, 429, 451, 509}:
        raise SourceError(4, f"network error: HTTP {status}", retry_after=retry_after)
    if status == 400:
        raise SourceError(2, "notes API rejected the bounding box or limit")
    if status in {408, 500, 502, 503, 504} or status >= 500:
        raise SourceError(5, f"network error: HTTP {status}: upstream unavailable", retry_after=retry_after)
    raise SourceError(5, f"network error: HTTP {status}: upstream unavailable")


def _require_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise SourceError(6, f"notes response schema mismatch: {label}")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SourceError(6, f"notes response schema mismatch: {label}")
    return float(value)


def _comment(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SourceError(6, "notes response schema mismatch: comment")
    text = raw.get("text")
    if not isinstance(text, str):
        raise SourceError(6, "notes response schema mismatch: comment text")
    action = raw.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise SourceError(6, "notes response schema mismatch: comment action")
    comment = {
        "date": _require_timestamp(raw.get("date"), "comment date"),
        "action": action,
        "text": text[:TEXT_CAP],
    }
    if len(text) > TEXT_CAP:
        comment["text_truncated"] = True
    return comment


def _inside(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon - 1e-8 <= lon <= max_lon + 1e-8 and min_lat - 1e-8 <= lat <= max_lat + 1e-8


def normalise_notes(
    payload: Any,
    bbox: tuple[float, float, float, float],
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise SourceError(6, "notes response schema mismatch: FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SourceError(6, "notes response schema mismatch: features")
    selected = features[:limit]
    notes: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for feature in selected:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise SourceError(6, "notes response schema mismatch: feature")
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise SourceError(6, "notes response schema mismatch: geometry")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise SourceError(6, "notes response schema mismatch: coordinates")
        longitude = _finite(coordinates[0], "longitude")
        latitude = _finite(coordinates[1], "latitude")
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise SourceError(6, "notes response schema mismatch: coordinate range")
        if not _inside(longitude, latitude, bbox):
            raise SourceError(6, "notes response schema mismatch: note outside the requested bounding box")
        if not isinstance(properties, dict):
            raise SourceError(6, "notes response schema mismatch: properties")
        note_id = properties.get("id")
        if isinstance(note_id, bool) or not isinstance(note_id, int) or note_id < 1:
            raise SourceError(6, "notes response schema mismatch: note id")
        status = properties.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise SourceError(6, "notes response schema mismatch: status")
        created = _require_timestamp(properties.get("date_created"), "date_created")
        timestamps.append(created)
        comments_raw = properties.get("comments")
        if not isinstance(comments_raw, list) or not comments_raw:
            raise SourceError(6, "notes response schema mismatch: comments")
        comments = [_comment(item) for item in comments_raw]
        timestamps.extend(comment["date"] for comment in comments)
        note: dict[str, Any] = {
            "id": note_id,
            "status": status,
            "longitude": longitude,
            "latitude": latitude,
            "date_created": created,
            "comments": comments,
            "note_url": f"{WEB_ORIGIN}/note/{note_id}",
        }
        if "date_closed" in properties and properties.get("date_closed") is not None:
            closed = _require_timestamp(properties.get("date_closed"), "date_closed")
            note["date_closed"] = closed
            timestamps.append(closed)
        notes.append(note)
    latest = max(timestamps) if timestamps else None
    return notes, latest


def decode_notes(
    status: int,
    headers: dict[str, str],
    body: bytes,
    bbox: tuple[float, float, float, float],
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    if status != 200:
        _fail_status(status, headers)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(6, "notes response schema mismatch: JSON") from exc
    return normalise_notes(payload, bbox, limit)


def to_features(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for note in notes:
        properties = {key: value for key, value in note.items() if key not in {"longitude", "latitude"}}
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [note["longitude"], note["latitude"]],
                },
                "properties": properties,
            }
        )
    return features


def render_text(notes: list[dict[str, Any]], bbox: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    lines = [
        f"OpenStreetMap notes — {LICENCE}",
        "© OpenStreetMap contributors",
        (
            "bbox "
            f"{format_coord(min_lon)},{format_coord(min_lat)},"
            f"{format_coord(max_lon)},{format_coord(max_lat)}"
        ),
        f"{len(notes)} note" + ("" if len(notes) == 1 else "s"),
    ]
    for note in notes:
        lines.append(
            f"#{note['id']} {note['status']} "
            f"{format_coord(note['longitude'])},{format_coord(note['latitude'])} "
            f"created {note['date_created']}"
        )
        for comment in note["comments"]:
            text = " ".join(comment["text"].split())
            suffix = " [truncated]" if comment.get("text_truncated") else ""
            lines.append(f"  {comment['action']} {comment['date']}: {text}{suffix}")
    return "\n".join(lines)


def emit_error(code: int, message: str, machine: bool, retry_after: str | None = None) -> int:
    if machine:
        print(
            json.dumps(
                error_envelope(code, message, source_meta(), retry_after=retry_after),
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"osm-notes: {message}", file=sys.stderr)
    return code


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Read OpenStreetMap map notes inside a small bounding box.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)
    notes = sub.add_parser(
        "notes",
        help="read notes.json for one small bounding box",
        description=(
            "GET the public notes collection once. "
            "This command does not create, comment on, close, or reopen notes."
        ),
    )
    notes.add_argument(
        "--bbox",
        required=True,
        type=parse_bbox,
        metavar="minLon,minLat,maxLon,maxLat",
        help="WGS84 box; each side must be at most 0.05 degrees. The notes API filters by point containment.",
    )
    notes.add_argument("--limit", type=parse_limit, default=10, help=f"maximum notes to return, 1 to {MAX_LIMIT}")
    notes.add_argument(
        "--closed-days",
        type=parse_closed_days,
        default=0,
        help="0 returns open notes only; 1 to 7 also includes notes closed within that many days",
    )
    notes.add_argument("--format", choices=("json", "geojson"), default="json", help="geojson is machine-readable")
    notes.add_argument("--json", action="store_true", help="emit the provenance JSON envelope")
    notes.add_argument(
        "--fixture",
        help="replay a notes JSON file inside this skill directory instead of calling the API",
    )
    return parser


def run_notes(args: argparse.Namespace) -> int:
    check_span(args.bbox)
    fixture = resolve_fixture(args.fixture) if args.fixture else None
    url = None if fixture else request_url(args.bbox, args.limit, args.closed_days)
    if fixture:
        status, headers, body = load_fixture(fixture)
    else:
        assert url is not None
        status, headers, body = http_get(url)
    notes, latest = decode_notes(status, headers, body, args.bbox, args.limit)
    meta = source_meta(url or NOTES_COLLECTION, latest)
    machine = args.json or args.format == "geojson"
    if args.format == "geojson":
        print(json.dumps(geojson_envelope(to_features(notes), meta), indent=2, ensure_ascii=False))
    elif machine:
        print(json.dumps(result_envelope(notes, meta), indent=2, ensure_ascii=False))
    else:
        print(render_text(notes, args.bbox))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    machine = wants_machine_output(argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command != "notes":
            raise SourceError(7, "unsupported notes operation")
        return run_notes(args)
    except InputError as exc:
        return emit_error(2, str(exc), machine)
    except SourceError as exc:
        return emit_error(exc.code, str(exc), machine, exc.retry_after)


if __name__ == "__main__":
    raise SystemExit(main())
