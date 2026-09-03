#!/usr/bin/env python3
"""Bounded, read-only client for official NZTA highway information feeds."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import re
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ROOT = "https://trafficnz.info/service/traffic/rest/4/"
SITE_ROOT = "https://trafficnz.info/"
CATALOGUE_URL = "https://catalogue.data.govt.nz/dataset/nzta-highway-information1"
WADL_URL = API_ROOT.rstrip("/") + "?_wadl"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 4_000_000
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
USER_AGENT = "thecolab-nzta-highway-info/1.0"
ALLOWED_HOSTS = {"trafficnz.info"}

ENDPOINTS = {
    "events": ("events/all/10", "roadevent"),
    "travel-times": ("signs/tim/all", "tim"),
    "cameras": ("cameras/all", "camera"),
    "vms": ("signs/vms/all", "vms"),
    "regions": ("regions/all/10", "region"),
}

ERROR_CATEGORIES = {
    2: "invalid_input",
    4: "blocked",
    5: "upstream_unavailable",
    6: "source_schema",
}


class CliError(Exception):
    """Expected CLI failure with a stable repository exit code."""

    exit_code = 5


class InputError(CliError):
    exit_code = 2


class BlockedError(CliError):
    exit_code = 4


class UpstreamError(CliError):
    exit_code = 5


class SchemaError(CliError):
    exit_code = 6


class CliArgumentParser(argparse.ArgumentParser):
    """Route expected argument errors through the stable CLI error envelope."""

    def error(self, message: str) -> NoReturn:
        raise InputError(message)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def scalar(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise SchemaError("upstream response contained a non-finite number")
    return (
        value if isinstance(value, (str, int, float, bool)) or value is None else None
    )


def validate_json_value(value: Any) -> None:
    """Reject values that cannot occur in standards-compliant JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        raise SchemaError("upstream response contained a non-finite number")
    if isinstance(value, list):
        for item in value:
            validate_json_value(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SchemaError("upstream response contained a non-string object key")
            validate_json_value(item)


def required_identifier(item: dict[str, Any], item_name: str) -> str | int:
    value = item.get("id")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SchemaError(f"{item_name} item has an invalid id")
    if isinstance(value, str) and not value.strip():
        raise SchemaError(f"{item_name} item has an invalid id")
    return value


def required_bool(item: dict[str, Any], field: str, item_name: str) -> bool:
    if field not in item:
        raise SchemaError(f"{item_name} item is missing {field}")
    value = item[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "1"}:
            return True
        if normalised in {"false", "0"}:
            return False
    raise SchemaError(f"{item_name} item has invalid {field}")


def reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    return str(name).strip() if name not in (None, "") else None


def normalise_highway(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().upper().replace("STATE HIGHWAY", "SH")
    if text.startswith("SH"):
        suffix = text[2:].strip()
        return f"SH{suffix}" if suffix else text
    if text.isdigit():
        return f"SH{int(text)}"
    return text


def absolute_site_url(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    resolved = urljoin(SITE_ROOT, text)
    if not resolved.startswith(("https://trafficnz.info/", "http://trafficnz.info/")):
        raise SchemaError("camera response contained an unexpected image host")
    return resolved.replace("http://", "https://", 1)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalise_event(item: dict[str, Any]) -> dict[str, Any]:
    item_id = required_identifier(item, "road-event")
    way = nested_name(item.get("way")) or nested_name(item.get("journey"))
    return {
        "id": item_id,
        "type": scalar(item.get("eventType")),
        "description": scalar(item.get("eventDescription")),
        "comments": scalar(item.get("eventComments")),
        "location": scalar(item.get("locationArea")),
        "impact": scalar(item.get("impact")),
        "status": scalar(item.get("status")),
        "planned": bool_value(item.get("planned")),
        "start_at": scalar(item.get("startDate")),
        "end_at": scalar(item.get("endDate")),
        "expected_resolution": scalar(item.get("expectedResolution")),
        "last_updated_at": scalar(item.get("eventModified")),
        "alternative_route": scalar(item.get("alternativeRoute")),
        "region": nested_name(item.get("region")),
        "highway": normalise_highway(way),
        "geometry_wkt": scalar(item.get("geometry")),
    }


def normalise_camera(item: dict[str, Any]) -> dict[str, Any]:
    item_id = required_identifier(item, "camera")
    offline = required_bool(item, "offline", "camera")
    maintenance = required_bool(item, "underMaintenance", "camera")
    status = "offline" if offline else "maintenance" if maintenance else "online"
    highway = (
        item.get("highway")
        or nested_name(item.get("way"))
        or nested_name(item.get("journey"))
    )
    return {
        "id": item_id,
        "name": scalar(item.get("name")),
        "description": scalar(item.get("description")),
        "direction": scalar(item.get("direction")),
        "region": nested_name(item.get("region")),
        "highway": normalise_highway(highway),
        "latitude": scalar(item.get("latitude")),
        "longitude": scalar(item.get("longitude")),
        "status": status,
        "offline": offline,
        "under_maintenance": maintenance,
        "image_url": absolute_site_url(item.get("imageUrl")),
        "thumbnail_url": absolute_site_url(item.get("thumbUrl")),
        "view_url": absolute_site_url(item.get("viewUrl")),
        "last_updated_at": None,
    }


def message_lines(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    return [
        part.strip()
        for part in re.split(r"\[(?:nl|np)\]", str(value), flags=re.IGNORECASE)
        if part.strip()
    ]


def normalise_vms(item: dict[str, Any]) -> dict[str, Any]:
    item_id = required_identifier(item, "VMS")
    lines = message_lines(item.get("currentMessage"))
    highway = nested_name(item.get("way")) or nested_name(item.get("journey"))
    return {
        "id": item_id,
        "name": scalar(item.get("name")),
        "description": scalar(item.get("description")),
        "direction": scalar(item.get("direction")),
        "region": nested_name(item.get("region")),
        "highway": normalise_highway(highway),
        "latitude": scalar(item.get("latitude")),
        "longitude": scalar(item.get("longitude")),
        "message": "\n".join(lines) if lines else None,
        "message_lines": lines,
        "last_message_update": scalar(item.get("lastMessageUpdate")),
        "last_updated_at": scalar(item.get("lastUpdate")),
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_tim_pages(
    value: Any,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    pages: list[list[dict[str, Any]]] = []
    destinations: list[dict[str, Any]] = []
    for page in as_list(value):
        if not isinstance(page, dict):
            raise SchemaError("travel-time sign page is not an object")
        parsed_lines: list[dict[str, Any]] = []
        for line in as_list(page.get("line")):
            if not isinstance(line, dict):
                raise SchemaError("travel-time sign line is not an object")
            cleaned = {
                str(key): scalar(val)
                for key, val in line.items()
                if scalar(val) is not None
            }
            parsed_lines.append(cleaned)
            left = cleaned.get("left")
            right = cleaned.get("right")
            if (
                left not in (None, "")
                and isinstance(right, (int, float))
                and not isinstance(right, bool)
            ):
                destinations.append({"name": str(left), "minutes": right})
        pages.append(parsed_lines)
    return pages, destinations


def normalise_tim(item: dict[str, Any]) -> dict[str, Any]:
    item_id = required_identifier(item, "travel-time sign")
    enabled = required_bool(item, "enabled", "travel-time sign")
    pages, destinations = parse_tim_pages(item.get("page"))
    return {
        "id": item_id,
        "name": scalar(item.get("name")),
        "region": nested_name(item.get("region")),
        "highway": normalise_highway(nested_name(item.get("way"))),
        "latitude": scalar(item.get("latitude")),
        "longitude": scalar(item.get("longitude")),
        "enabled": enabled,
        "mode": scalar(item.get("mode")),
        "virtual": bool_value(item.get("virtual")),
        "pages": pages,
        "destinations": destinations,
        "congestion_status": None,
        "source_provides_baseline": False,
        "last_updated_at": scalar(item.get("timeStamp")),
    }


def normalise_region(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("id") in (None, "") or item.get("name") in (None, ""):
        raise SchemaError("region item is missing id or name")
    return {"id": scalar(item.get("id")), "name": scalar(item.get("name"))}


NORMALISERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "events": normalise_event,
    "travel-times": normalise_tim,
    "cameras": normalise_camera,
    "vms": normalise_vms,
    "regions": normalise_region,
}


def parse_response(
    payload: Any, item_key: str, parser: Callable[[dict[str, Any]], dict[str, Any]]
) -> list[dict[str, Any]]:
    validate_json_value(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
        raise SchemaError("upstream response is missing response object")
    response = payload["response"]
    if item_key not in response:
        raise SchemaError(f"upstream response is missing {item_key} list")
    raw_items = response[item_key]
    if raw_items is None:
        raise SchemaError(f"upstream {item_key} value is null")
    if not isinstance(raw_items, list):
        raise SchemaError(f"upstream {item_key} value is not a list")
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise SchemaError(f"upstream {item_key}[{index}] is not an object")
        parsed.append(parser(item))
    return parsed


def validate_source_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise SchemaError("upstream redirect URL is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise SchemaError("upstream redirected outside the declared NZTA host")


class NZTARedirectHandler(HTTPRedirectHandler):
    """Validate each redirect before urllib issues the follow-up request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_json(url: str) -> Any:
    validate_source_url(url)
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        opener = build_opener(NZTARedirectHandler())
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            length = response.headers.get("Content-Length")
            if length:
                try:
                    declared_length = int(length)
                except ValueError as exc:
                    raise SchemaError(
                        "upstream returned an invalid Content-Length header"
                    ) from exc
                if declared_length < 0:
                    raise SchemaError(
                        "upstream returned an invalid Content-Length header"
                    )
                if declared_length > MAX_RESPONSE_BYTES:
                    raise UpstreamError("upstream response exceeds the 4 MB safety cap")
            try:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, http.client.HTTPException) as exc:
                raise UpstreamError(f"upstream response interrupted: {exc}") from exc
            if len(body) > MAX_RESPONSE_BYTES:
                raise UpstreamError("upstream response exceeds the 4 MB safety cap")
    except HTTPError as exc:
        if exc.code in {401, 403, 429}:
            raise BlockedError(
                f"upstream access blocked or rate-limited (HTTP {exc.code})"
            ) from exc
        raise UpstreamError(f"upstream unavailable (HTTP {exc.code})") from exc
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpstreamError(f"upstream unavailable or timed out: {reason}") from exc
    try:
        return json.loads(body.decode("utf-8"), parse_constant=reject_json_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SchemaError("upstream returned invalid JSON") from exc


def filter_items(
    items: list[dict[str, Any]],
    *,
    region: str | None,
    query: str | None,
    limit: int,
    event_type: str | None = None,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_LIMIT:
        raise InputError(f"--limit must be between 1 and {MAX_LIMIT}")
    region_cf = region.casefold() if region else None
    query_cf = query.casefold() if query else None
    type_cf = event_type.casefold() if event_type else None
    matched: list[dict[str, Any]] = []
    for item in items:
        if region_cf and region_cf not in str(item.get("region") or "").casefold():
            continue
        if type_cf and type_cf not in str(item.get("type") or "").casefold():
            continue
        if active_only and not item.get("message_lines"):
            continue
        if query_cf:
            searchable = json.dumps(item, ensure_ascii=False, sort_keys=True).casefold()
            if query_cf not in searchable:
                continue
        matched.append(item)
        if len(matched) >= limit:
            break
    return matched


def latest_update(items: list[dict[str, Any]]) -> str | None:
    values = [
        str(value)
        for item in items
        for value in (item.get("last_updated_at"), item.get("last_message_update"))
        if isinstance(value, str) and value
    ]
    return max(values) if values else None


def warning_for(command: str) -> list[str]:
    warnings = [
        (
            "NZTA says operational conditions can change rapidly; verify critical "
            "travel decisions on the official Journey Planner and follow road signs "
            "and emergency directions."
        ),
        (
            "This public feed is a current snapshot, not a guarantee of completeness, "
            "road safety, or route availability."
        ),
    ]
    if command in {"cameras", "travel-times"}:
        warnings.append(
            "The source may omit per-item update timestamps for this feed; "
            "retrieved_at only proves when this client fetched it."
        )
    if command == "travel-times":
        warnings.append(
            "Travel-time sign minutes are displayed values without a free-flow "
            "baseline; no congestion classification is inferred."
        )
    return warnings


def execute(command: str, args: argparse.Namespace) -> dict[str, Any]:
    path, item_key = ENDPOINTS[command]
    endpoint = urljoin(API_ROOT, path)
    retrieved_at = utc_now()
    raw = fetch_json(endpoint)
    all_items = parse_response(raw, item_key, NORMALISERS[command])
    if command == "regions":
        items = filter_items(all_items, region=None, query=args.query, limit=args.limit)
    else:
        items = filter_items(
            all_items,
            region=args.region,
            query=args.query,
            limit=args.limit,
            event_type=getattr(args, "event_type", None),
            active_only=getattr(args, "active_only", False),
        )
    return {
        "schema_version": "1",
        "ok": True,
        "kind": command,
        "source": {
            "name": "NZ Transport Agency Waka Kotahi Traffic and Travel API",
            "url": endpoint,
            "catalogue_url": CATALOGUE_URL,
            "contract_url": WADL_URL,
            "retrieved_at": retrieved_at,
            "latest_item_update_at": latest_update(all_items),
        },
        "query": {
            "region": getattr(args, "region", None),
            "text": args.query,
            "event_type": getattr(args, "event_type", None),
            "active_only": getattr(args, "active_only", False),
            "limit": args.limit,
        },
        "data": items,
        "returned": len(items),
        "source_count": len(all_items),
        "truncated": len(items) < len(all_items),
        "complete": False,
        "warnings": warning_for(command),
        "blocked": False,
    }


def add_common(parser: argparse.ArgumentParser, *, region: bool = True) -> None:
    if region:
        parser.add_argument("--region", help="case-insensitive region-name substring")
    parser.add_argument(
        "--query", help="case-insensitive text search across returned fields"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"maximum results (1-{MAX_LIMIT}; default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = CliArgumentParser(
        description="Bounded, read-only NZTA highway information lookups"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    events = sub.add_parser("events", help="current state-highway events and incidents")
    add_common(events)
    events.add_argument("--event-type", help="case-insensitive event-type substring")

    travel = sub.add_parser(
        "travel-times",
        help="current travel-time sign displays; does not infer congestion",
    )
    add_common(travel)

    cameras = sub.add_parser(
        "cameras", help="traffic-camera metadata and current image URLs"
    )
    add_common(cameras)

    vms = sub.add_parser("vms", help="variable-message sign messages and metadata")
    add_common(vms)
    vms.add_argument(
        "--active-only",
        action="store_true",
        help="only signs with a non-empty current message",
    )

    regions = sub.add_parser("regions", help="official Traffic and Travel API regions")
    add_common(regions, region=False)
    return parser


def human_value(item: dict[str, Any], command: str) -> str:
    if command == "events":
        title = item.get("type") or item.get("description") or "Road event"
        return (
            f"{item.get('id')}: {title} — "
            f"{item.get('location') or 'location not supplied'} "
            f"[{item.get('region') or 'region not supplied'}]"
        )
    if command == "cameras":
        return (
            f"{item.get('id')}: "
            f"{item.get('name') or item.get('description') or 'Camera'} "
            f"[{item.get('status')}] "
            f"{item.get('image_url') or 'no image URL'}"
        )
    if command == "vms":
        message = " / ".join(item.get("message_lines") or []) or "no current message"
        return f"{item.get('id')}: {item.get('name') or 'VMS'} — {message}"
    if command == "travel-times":
        values = (
            ", ".join(
                f"{entry['name']} {entry['minutes']} min"
                for entry in item.get("destinations") or []
            )
            or "no numeric destination times"
        )
        return f"{item.get('id')}: {item.get('name') or 'travel-time sign'} — {values}"
    return f"{item.get('id')}: {item.get('name')}"


def emit(payload: dict[str, Any], json_mode: bool) -> None:
    if json_mode:
        try:
            validate_json_value(payload)
            serialised = json.dumps(
                payload, indent=2, ensure_ascii=False, allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise SchemaError(
                "normalised result is not standards-compliant JSON"
            ) from exc
        print(serialised)
        return
    source = payload["source"]
    print(
        f"NZTA {payload['kind']} — {payload['returned']} result(s) "
        f"(fetched {source['retrieved_at']})"
    )
    for item in payload["data"]:
        print(human_value(item, payload["kind"]))
    for warning in payload["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)


def wants_json(argv: list[str]) -> bool:
    return "--json" in argv


def main(argv: list[str] | None = None) -> int:
    actual = list(sys.argv[1:] if argv is None else argv)
    args: argparse.Namespace | None = None
    requested_command = actual[0] if actual and actual[0] in ENDPOINTS else None
    json_mode = wants_json(actual)
    try:
        args = build_parser().parse_args(actual)
        json_mode = bool(getattr(args, "json", False)) or json_mode
        if not 1 <= args.limit <= MAX_LIMIT:
            raise InputError(f"--limit must be between 1 and {MAX_LIMIT}")
        payload = execute(args.command, args)
        emit(payload, json_mode)
        return 0
    except CliError as exc:
        if json_mode or wants_json(actual):
            command = getattr(args, "command", requested_command)
            endpoint = (
                urljoin(API_ROOT, ENDPOINTS[command][0])
                if command in ENDPOINTS
                else API_ROOT
            )
            query = {
                "region": getattr(args, "region", None),
                "text": getattr(args, "query", None),
                "event_type": getattr(args, "event_type", None),
                "active_only": getattr(args, "active_only", False),
                "limit": getattr(args, "limit", None),
            }
            print(
                json.dumps(
                    {
                        "schema_version": "1",
                        "ok": False,
                        "kind": command,
                        "source": {
                            "name": (
                                "NZ Transport Agency Waka Kotahi Traffic and Travel "
                                "API"
                            ),
                            "url": endpoint,
                            "catalogue_url": CATALOGUE_URL,
                            "contract_url": WADL_URL,
                            "retrieved_at": utc_now(),
                            "latest_item_update_at": None,
                        },
                        "query": query,
                        "error": {
                            "code": exc.exit_code,
                            "category": ERROR_CATEGORIES[exc.exit_code],
                            "message": str(exc),
                        },
                        "data": None,
                        "warnings": [],
                        "blocked": exc.exit_code == 4,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
