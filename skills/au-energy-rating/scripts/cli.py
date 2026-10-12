#!/usr/bin/env python3
"""Read the Australian Energy Rating CKAN package and bounded datastore previews.

The CLI calls only data.gov.au CKAN action endpoints. It does not download the
multi-megabyte CSV resources and it does not accept a caller-supplied URL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode, urlparse

from provenance import error_envelope, provenance, result_envelope

ALLOWED_HOST = "data.gov.au"
PACKAGE_ID = "559708e5-480e-4f94-8429-c49571e82761"
API_ROOT = "https://data.gov.au/data/api/3/action/"
PACKAGE_URL = API_ROOT + "package_show?" + urlencode({"id": PACKAGE_ID})
PUBLISHER = (
    "Australian Government Department of Climate Change, Energy, "
    "the Environment and Water"
)
USER_AGENT = (
    "thecolab-au-energy-rating/1.0 "
    "(public CKAN read; +https://github.com/thecolab-ai/.skills)"
)
TIMEOUT_SECONDS = 15
MAX_LIMIT = 20
MAX_BYTES = 524288
MAX_REDIRECTS = 3
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
Fetch = Callable[[str], dict[str, Any]]


class SkillError(Exception):
    def __init__(self, message: str, code: int, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class InputError(ValueError):
    """Argparse failure emitted as a typed error, before any network call."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow only HTTPS redirects that stay on data.gov.au."""

    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        assert_allowed_url(newurl, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def assert_allowed_url(url: str, *, redirect: bool = False) -> None:
    """Reject any request or redirect that leaves official HTTPS on data.gov.au."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    kind = "redirect host" if redirect else "request URL"
    if (
        parsed.scheme != "https"
        or host != ALLOWED_HOST
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SkillError(
            f"{kind} is outside the data.gov.au https allowlist: {host or 'unknown'}",
            7,
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise SkillError(
            f"{kind} is outside the data.gov.au https allowlist: invalid port",
            7,
        ) from exc
    if port not in (None, 443):
        raise SkillError(
            f"{kind} is outside the data.gov.au https allowlist: non-default port",
            7,
        )


def clean_name(value: str) -> str:
    """Collapse CKAN's space-padded resource titles without dropping tokens."""
    return re.sub(r"[ \t]+", " ", value).strip()


def clean_notes(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def preview_url(resource_id: str, limit: int) -> str:
    return API_ROOT + "datastore_search?" + urlencode(
        {"resource_id": resource_id, "limit": str(limit)}
    )


def resource_id_type(value: str) -> str:
    if "://" in value or "/" in value or value.lower().startswith("http"):
        raise argparse.ArgumentTypeError(
            "resource must be a datastore id from package, not a URL"
        )
    if not UUID_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "resource must be a lowercase UUID from package"
        )
    return value


def limit_type(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(
            f"--limit must be an integer from 1 to {MAX_LIMIT}"
        )
    limit = int(value)
    if limit < 1 or limit > MAX_LIMIT:
        raise argparse.ArgumentTypeError(
            f"--limit must be an integer from 1 to {MAX_LIMIT}"
        )
    return limit


def _opener() -> urllib.request.OpenerDirector:
    # An empty proxy map disables environment proxies. File and FTP handlers
    # cannot run because assert_allowed_url only allows https://data.gov.au.
    return urllib.request.build_opener(
        AllowlistRedirectHandler(),
        urllib.request.ProxyHandler({}),
    )


def decode_response(status: int, headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
    """Turn one bounded HTTP response into a CKAN object, or a typed error.

    Error statuses are decided before the body is parsed, so a 429 or 503 body
    cannot be treated as a successful row set.
    """
    if status == 429:
        retry_after = headers.get("Retry-After") if headers is not None else None
        if not isinstance(retry_after, str) or not retry_after.strip() or len(retry_after) > 200:
            retry_after = None
        else:
            retry_after = retry_after.strip()
        raise SkillError("network error: HTTP 429", 4, retry_after=retry_after)
    if status == 503:
        raise SkillError("network error: HTTP 503", 5)
    if status != 200:
        code = 5 if status >= 500 else 6
        raise SkillError(f"network error: HTTP {status}", code)
    if len(body) > MAX_BYTES:
        raise SkillError(
            "source schema failure: response exceeded the byte cap and was not parsed",
            6,
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillError("source schema failure: non-JSON or truncated JSON", 6) from exc
    if not isinstance(payload, dict):
        raise SkillError("source schema failure: expected a JSON object", 6)
    return payload


def fetch_json(url: str) -> dict[str, Any]:
    assert_allowed_url(url)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            assert_allowed_url(final_url)
            body = response.read(MAX_BYTES + 1)
            status = getattr(response, "status", 200)
            headers = response.headers
    except SkillError:
        raise
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES + 1)
        try:
            return decode_response(exc.code, exc.headers, body)
        finally:
            exc.close()
    except TimeoutError as exc:
        raise SkillError("network error: source request timed out", 5) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, SkillError):
            raise reason
        text = str(reason).lower()
        if isinstance(reason, TimeoutError) or "timed out" in text:
            raise SkillError("network error: source request timed out", 5) from exc
        raise SkillError(f"network error: {reason}", 5) from exc
    return decode_response(status, headers, body)


def require_result(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is not True:
        raise SkillError(
            "source schema failure: CKAN success was not true; no rows were invented",
            6,
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise SkillError("source schema failure: CKAN result was not an object", 6)
    return result


def _required_text(result: Mapping[str, Any], key: str) -> str:
    value = result.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillError(f"source schema failure: package {key} was missing", 6)
    return value


def parse_package(payload: dict[str, Any]) -> dict[str, Any]:
    result = require_result(payload)
    package_id = _required_text(result, "id")
    if package_id != PACKAGE_ID:
        raise SkillError(
            "source schema failure: response was not the energy-rating package",
            6,
        )
    organisation = result.get("organization")
    if not isinstance(organisation, dict):
        raise SkillError("source schema failure: package organisation was missing", 6)
    publisher = organisation.get("title")
    if not isinstance(publisher, str) or not publisher.strip():
        raise SkillError("source schema failure: package organisation title was missing", 6)
    notes = result.get("notes")
    if notes is None:
        notes_text = ""
    elif isinstance(notes, str):
        notes_text = clean_notes(notes)
    else:
        raise SkillError("source schema failure: package notes were not text", 6)
    licence_title = result.get("license_title")
    licence_id = result.get("license_id")
    licence_url = result.get("license_url")
    if licence_title is not None and not isinstance(licence_title, str):
        raise SkillError("source schema failure: licence title was not text", 6)
    if licence_id is not None and not isinstance(licence_id, str):
        raise SkillError("source schema failure: licence id was not text", 6)
    if licence_url is not None and not isinstance(licence_url, str):
        raise SkillError("source schema failure: licence URL was not text", 6)
    modified = result.get("metadata_modified")
    if modified is not None and not isinstance(modified, str):
        raise SkillError("source schema failure: metadata_modified was not text", 6)
    raw_resources = result.get("resources")
    if not isinstance(raw_resources, list):
        raise SkillError("source schema failure: package resources were not a list", 6)
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_resources:
        resources.append(_parse_resource(item, seen))
    return {
        "package_id": package_id,
        "name": _required_text(result, "name"),
        "title": _required_text(result, "title"),
        "organisation": publisher.strip(),
        "licence_id": licence_id,
        "licence_title": licence_title.strip() if isinstance(licence_title, str) and licence_title.strip() else None,
        "licence_url": licence_url,
        "metadata_modified": modified,
        "notes": notes_text,
        "resources": resources,
    }


def _parse_resource(item: Any, seen: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SkillError("source schema failure: a package resource was not an object", 6)
    resource_id = item.get("id")
    if not isinstance(resource_id, str) or not UUID_RE.fullmatch(resource_id):
        raise SkillError("source schema failure: a resource id was not a lowercase UUID", 6)
    if resource_id in seen:
        raise SkillError("source schema failure: duplicate resource id", 6)
    seen.add(resource_id)
    name = item.get("name")
    if not isinstance(name, str) or not clean_name(name):
        raise SkillError("source schema failure: a resource name was empty", 6)
    active = item.get("datastore_active")
    if not isinstance(active, bool):
        raise SkillError("source schema failure: datastore_active was not a boolean", 6)
    fmt = item.get("format")
    if fmt is not None and not isinstance(fmt, str):
        raise SkillError("source schema failure: resource format was not text", 6)
    size = item.get("size")
    if size is not None and (type(size) is not int or size < 0):
        raise SkillError("source schema failure: resource size was not a positive integer or null", 6)
    modified = item.get("last_modified")
    if modified is not None and not isinstance(modified, str):
        raise SkillError("source schema failure: resource last_modified was not text", 6)
    return {
        "id": resource_id,
        "name": clean_name(name),
        "format": fmt,
        "datastore_active": active,
        "size": size,
        "last_modified": modified,
    }


def parse_preview(payload: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], int]:
    result = require_result(payload)
    total = result.get("total")
    records = result.get("records")
    if type(total) is not int or total < 0:
        raise SkillError("source schema failure: datastore total was not a non-negative integer", 6)
    if not isinstance(records, list):
        raise SkillError("source schema failure: datastore records were not a list", 6)
    if len(records) > limit:
        raise SkillError(
            "source schema failure: datastore returned more rows than the requested limit",
            6,
        )
    if total == 0 and records:
        raise SkillError(
            "source schema failure: datastore reported no rows but returned records",
            6,
        )
    if total > 0 and limit >= 1 and not records:
        raise SkillError(
            "source schema failure: datastore reported rows but returned none",
            6,
        )
    parsed: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise SkillError("source schema failure: a datastore record was not an object", 6)
        parsed.append(record)
    return parsed, total


def source_meta(
    source_url: str,
    *,
    publisher: str = PUBLISHER,
    licence: str | None = None,
    latest_data: str | None = None,
) -> dict[str, Any]:
    return provenance(
        source_url,
        publisher,
        licence=licence,
        latest_data=latest_data,
    )


def emit_json(payload: dict[str, Any]) -> None:
    try:
        text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        raise SkillError("source schema failure: result was not finite JSON", 6) from exc
    print(text)


def emit_error(exc: SkillError, as_json: bool, meta: dict[str, Any]) -> int:
    if as_json:
        emit_json(error_envelope(exc.code, str(exc), meta, retry_after=exc.retry_after))
    else:
        print(f"au-energy-rating: {exc}", file=sys.stderr)
    return exc.code


def load_package(fetch: Fetch) -> dict[str, Any]:
    return parse_package(fetch(PACKAGE_URL))


def select_resource(package: dict[str, Any], resource_id: str) -> dict[str, Any]:
    matches = [item for item in package["resources"] if item["id"] == resource_id]
    if not matches:
        raise SkillError(
            "resource is not in the energy-rating package; run package to list ids",
            2,
        )
    resource = matches[0]
    if resource["datastore_active"] is not True:
        raise SkillError(
            "resource is not datastore-active; CSV and dictionary downloads are not supported",
            2,
        )
    return resource


def command_package(as_json: bool, fetch: Fetch) -> int:
    package = load_package(fetch)
    meta = source_meta(
        PACKAGE_URL,
        publisher=package["organisation"],
        licence=package["licence_title"],
        latest_data=package["metadata_modified"],
    )
    payload = result_envelope([package], meta)
    if as_json:
        emit_json(payload)
        return 0
    print(package["title"])
    print(f"name: {package['name']}")
    print(f"organisation: {package['organisation']}")
    licence = package["licence_title"] or "not stated"
    if package["licence_id"]:
        licence = f"{licence} ({package['licence_id']})"
    print(f"licence: {licence}")
    if package["licence_url"]:
        print(f"licence url: {package['licence_url']}")
    print(f"metadata modified: {package['metadata_modified'] or '-'}")
    if package["notes"]:
        print(package["notes"])
    print(f"resources: {len(package['resources'])}")
    for resource in package["resources"]:
        mode = "datastore" if resource["datastore_active"] else "not previewable"
        print(
            f"- {resource['name']} [{resource['format'] or '-'}] {mode} id={resource['id']}"
        )
    return 0


def command_preview(resource_id: str, limit: int, as_json: bool, fetch: Fetch) -> int:
    package = load_package(fetch)
    resource = select_resource(package, resource_id)
    url = preview_url(resource_id, limit)
    records, total = parse_preview(fetch(url), limit)
    meta = source_meta(
        url,
        publisher=package["organisation"],
        licence=package["licence_title"],
        latest_data=resource["last_modified"],
    )
    meta["resource_id"] = resource["id"]
    meta["resource_name"] = resource["name"]
    meta["limit"] = limit
    meta["total"] = total
    if package["licence_url"]:
        meta["licence_url"] = package["licence_url"]
    payload = result_envelope(records, meta)
    if as_json:
        emit_json(payload)
        return 0
    print(f"{resource['name']} ({resource['id']})")
    print(f"showing {len(records)} of {total}")
    for record in records:
        bits = []
        for key in ("Brand", "Model_No", "c_star_mixed"):
            if key in record:
                bits.append(f"{key}={record[key]!s}")
        if not bits:
            for key, value in list(record.items())[:3]:
                bits.append(f"{key}={value!s}")
        print("- " + " | ".join(bits))
    return 0


def main(argv: list[str] | None = None, fetch: Fetch | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = ArgumentParser(description="Read the Australian Energy Rating CKAN package")
    sub = parser.add_subparsers(dest="command", required=True)
    package = sub.add_parser("package", help="show the energy-rating package, resources and licence")
    package.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    preview = sub.add_parser(
        "preview",
        help="preview one datastore-active resource without downloading its CSV",
    )
    preview.add_argument("resource_id", type=resource_id_type, help="lowercase resource UUID from package")
    preview.add_argument("--limit", type=limit_type, default=5, help=f"rows to return, from 1 to {MAX_LIMIT}")
    preview.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        meta = source_meta(PACKAGE_URL)
        if "--json" in argv:
            emit_json(error_envelope(2, str(exc), meta))
        else:
            parser.print_usage(sys.stderr)
            print(f"au-energy-rating: {exc}", file=sys.stderr)
        return 2

    fetcher = fetch_json if fetch is None else fetch
    as_json = bool(args.json)
    try:
        if args.command == "package":
            return command_package(as_json, fetcher)
        return command_preview(args.resource_id, args.limit, as_json, fetcher)
    except SkillError as exc:
        return emit_error(exc, as_json, source_meta(PACKAGE_URL))


if __name__ == "__main__":
    raise SystemExit(main())
