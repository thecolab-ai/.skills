#!/usr/bin/env python3
"""Read-only Ministry for the Environment Koordinates catalogue client.

Search and layer metadata only. Feature query and export endpoints are refused.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any, Callable

from provenance import error_envelope, provenance, result_envelope

REPO_LIB = pathlib.Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(REPO_LIB))
import nzfetch  # noqa: E402

PUBLISHER = "Ministry for the Environment"
HOST = "data.mfe.govt.nz"
API_ROOT = f"https://{HOST}/services/api/v1/"
SOURCE_URL = API_ROOT + "data/"
ALLOWED_HOSTS = frozenset({HOST})
TIMEOUT = 15
MAX_BYTES = 512 * 1024
MAX_LIMIT = 20
MAX_QUERY_LENGTH = 200
MAX_LINK_HEADER = 8192
MAX_LINK_VALUES = 32
MAX_LINK_URL = 2048
NEXT_RELS = frozenset({"next", "page-next"})
LAST_RELS = frozenset({"last", "page-last"})
_LINK_SPACE = " \t\r\n"
OPEN_ATTRIBUTION_TYPE = "cc-by"
OPEN_ATTRIBUTION_VERSIONS = frozenset({"1.0", "2.0", "2.5", "3.0", "4.0"})
CLOSED_TITLE_MARKERS = (
    "non-commercial",
    "noncommercial",
    "no derivatives",
    "noderivatives",
    "share-alike",
    "sharealike",
    "public domain",
    "cc0",
)

class CatalogueDocument:
    """Catalogue JSON plus the response Link header from the same GET."""

    def __init__(self, body: Any, link_header: str | None = None):
        self.body = body
        self.link_header = link_header if isinstance(link_header, str) else None


Transport = Callable[[str], Any]


class InputError(ValueError):
    """Argparse failure emitted as a JSON error envelope when requested."""


class SkillFailure(Exception):
    """A typed catalogue failure with a stable exit code."""

    def __init__(self, code: int, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def limit_value(raw: str) -> int:
    message = f"--limit must be an integer from 1 to {MAX_LIMIT}"
    if not raw.isdecimal():
        raise argparse.ArgumentTypeError(message)
    value = int(raw)
    if not 1 <= value <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(message)
    return value


def layer_id_value(raw: str) -> str:
    if not raw.isdecimal() or raw.startswith("0") or len(raw) > 12:
        raise argparse.ArgumentTypeError("layer id must be a positive integer of at most 12 digits")
    return raw


def search_query_value(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise argparse.ArgumentTypeError("search query must not be empty")
    if len(text) > MAX_QUERY_LENGTH:
        raise argparse.ArgumentTypeError(f"search query must be at most {MAX_QUERY_LENGTH} characters")
    if "://" in text or text.lower().startswith(("http:", "https:")):
        raise argparse.ArgumentTypeError("search accepts catalogue text, not a URL")
    if any(ord(char) < 32 for char in text):
        raise argparse.ArgumentTypeError("search query must not contain control characters")
    return text


def catalogue_url(path: str, params: dict[str, str] | None = None) -> str:
    """Build one official catalogue URL. Query and export paths cannot be formed."""
    if path != "data/" and re.fullmatch(r"layers/[1-9][0-9]{0,11}/", path) is None:
        raise SkillFailure(7, "refusing an unsupported catalogue path")
    if params is not None and any(key not in {"q", "page_size"} for key in params):
        raise SkillFailure(7, "refusing an unsupported catalogue parameter")
    url = API_ROOT + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or "/query" in parsed.path:
        raise SkillFailure(7, "refusing an unsupported catalogue request")
    return url


def outcome_for_exception(exc: BaseException) -> tuple[int, str, str | None]:
    """Map a transport failure to an exit code, message and optional Retry-After."""
    if isinstance(exc, nzfetch.RateLimited):
        return 4, "catalogue request was rate limited", exc.retry_after
    if isinstance(exc, nzfetch.Blocked):
        return 4, "catalogue request was blocked", None
    if isinstance(exc, nzfetch.ResponseTooLarge):
        return 6, "catalogue metadata exceeded the byte cap", None
    if isinstance(exc, nzfetch.InvalidCompressedBody):
        return 6, "catalogue response was truncated or not valid compressed data", None
    if isinstance(exc, TimeoutError):
        return 5, "catalogue request timed out", None
    if isinstance(exc, nzfetch.FetchError):
        message = str(exc)
        if "not in the declared allowlist" in message or "invalid outbound URL" in message:
            return 7, "catalogue redirect or host is outside data.mfe.govt.nz", None
        if "invalid JSON" in message:
            return 6, "catalogue response was not valid JSON", None
        status = _http_status(message)
        if status == 404:
            return 7, "catalogue record was not found", None
        if status in {403, 406, 429, 451}:
            retry_after = None
            return 4, f"catalogue request was blocked (HTTP {status})", retry_after
        if status is not None and 500 <= status <= 599:
            return 5, f"catalogue upstream unavailable (HTTP {status})", None
        if "timed out" in message:
            return 5, "catalogue request timed out", None
        if "network error" in message or "unavailable" in message:
            return 5, "catalogue request failed before a complete JSON document", None
        return 5, "catalogue request failed", None
    return 5, "catalogue request failed", None


def _http_status(message: str) -> int | None:
    marker = "HTTP "
    start = message.find(marker)
    if start < 0:
        return None
    digits = []
    for char in message[start + len(marker):]:
        if char.isdecimal():
            digits.append(char)
        else:
            break
    if len(digits) != 3:
        return None
    return int("".join(digits))


def _read_link_param_value(text: str, index: int) -> tuple[str, int]:
    if index >= len(text):
        return "", index
    if text[index] != '"':
        start = index
        while index < len(text) and text[index] not in _LINK_SPACE + ";,":
            index += 1
            if index - start > MAX_LINK_URL:
                break
        return text[start:index], index
    index += 1
    chars: list[str] = []
    while index < len(text) and len(chars) <= MAX_LINK_URL:
        char = text[index]
        if char == "\\":
            index += 1
            if index >= len(text):
                break
            chars.append(text[index])
            index += 1
            continue
        if char == '"':
            return "".join(chars), index + 1
        chars.append(char)
        index += 1
    return "".join(chars), index


def _skip_link_separator(text: str, index: int) -> int:
    quote = False
    while index < len(text):
        char = text[index]
        if char == "\\" and quote:
            index = min(len(text), index + 2)
            continue
        if char == '"':
            quote = not quote
            index += 1
            continue
        if char == "," and not quote:
            return index + 1
        index += 1
    return index


def _same_host_catalogue_url(url: str) -> str | None:
    """Return a catalogue page URL only when it is https on the official host."""
    if not isinstance(url, str) or not url or len(url) > MAX_LINK_URL or "\\" in url:
        return None
    if any(ord(char) < 32 or char.isspace() for char in url):
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or hostname != HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
        or "/query" in parsed.path
        or parsed.path.rstrip("/") != "/services/api/v1/data"
    ):
        return None
    return url


def parse_link_header(header: str | None) -> tuple[str | None, str | None, bool]:
    """Parse one Link header into same-host next and last catalogue URLs.

    The scan stops at a fixed character and link count. ``has_next`` is true when
    a parsed ``next`` or ``page-next`` relation is present, including when its
    target is omitted because it is not an official catalogue URL.
    """
    if not isinstance(header, str) or not header.strip():
        return None, None, False
    text = header[:MAX_LINK_HEADER]
    next_url: str | None = None
    last_url: str | None = None
    has_next = False
    index = 0
    produced = 0
    length = len(text)
    while index < length and produced < MAX_LINK_VALUES:
        start = index
        while index < length and text[index] in _LINK_SPACE + ",":
            index += 1
        if index >= length:
            break
        if text[index] != "<":
            index = _skip_link_separator(text, index)
            if index <= start:
                index = start + 1
            continue
        url_end = text.find(">", index + 1, index + 2 + MAX_LINK_URL)
        if url_end < 0:
            break
        url = text[index + 1:url_end]
        index = url_end + 1
        rels: list[str] = []
        while index < length and text[index] != ",":
            if text[index] in _LINK_SPACE:
                index += 1
                continue
            if text[index] != ";":
                index += 1
                continue
            index += 1
            while index < length and text[index] in _LINK_SPACE:
                index += 1
            name_start = index
            while index < length and text[index] not in _LINK_SPACE + "=;,":
                index += 1
            name = text[name_start:index].casefold()
            while index < length and text[index] in _LINK_SPACE:
                index += 1
            value = ""
            if index < length and text[index] == "=":
                index += 1
                while index < length and text[index] in _LINK_SPACE:
                    index += 1
                value, index = _read_link_param_value(text, index)
            if name == "rel":
                rels.extend(part.casefold() for part in value.split() if part)
        produced += 1
        folded = frozenset(rels)
        if folded & NEXT_RELS:
            has_next = True
            if next_url is None:
                safe = _same_host_catalogue_url(url)
                if safe:
                    next_url = safe
        if folded & LAST_RELS and last_url is None:
            safe = _same_host_catalogue_url(url)
            if safe:
                last_url = safe
        if index <= start:
            index = start + 1
    return next_url, last_url, has_next


def _link_header_from_response(response: Any) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    values: list[str] = []
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        raw_values = get_all("Link") or []
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        for item in raw_values:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
    if not values:
        getter = getattr(headers, "get", None)
        if callable(getter):
            raw = getter("Link")
            if isinstance(raw, str) and raw.strip():
                values.append(raw.strip())
    if not values:
        return None
    joined = ", ".join(values)
    if len(joined) > MAX_LINK_HEADER:
        return joined[: MAX_LINK_HEADER + 1]
    return joined


def fetch_catalogue_json(url: str) -> tuple[Any, str | None]:
    """GET one catalogue document and keep the Link header fetch_json drops."""
    captured: dict[str, str | None] = {"link": None}
    original = nzfetch._read_response_limited

    def capture(response: Any, max_bytes: int | None = None) -> bytes:
        captured["link"] = _link_header_from_response(response)
        return original(response, max_bytes)

    nzfetch._read_response_limited = capture
    try:
        payload = nzfetch.fetch_json(
            url,
            timeout=TIMEOUT,
            max_bytes=MAX_BYTES,
            allowed_hosts=ALLOWED_HOSTS,
        )
    finally:
        nzfetch._read_response_limited = original
    return payload, captured["link"]


def default_transport(url: str) -> CatalogueDocument:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or "/query" in parsed.path:
        raise SkillFailure(7, "refusing an unsupported catalogue request")
    layer_path = re.fullmatch(r"/services/api/v1/layers/[1-9][0-9]{0,11}/", parsed.path)
    if parsed.path != "/services/api/v1/data/" and layer_path is None:
        raise SkillFailure(7, "refusing an unsupported catalogue path")
    query_keys = set(urllib.parse.parse_qs(parsed.query, keep_blank_values=True))
    if not query_keys <= {"q", "page_size"}:
        raise SkillFailure(7, "refusing an unsupported catalogue parameter")
    body, link_header = fetch_catalogue_json(url)
    return CatalogueDocument(body, link_header=link_header)


def load_fixture(path: str) -> Any:
    if "://" in path or path.lower().startswith(("http:", "https:")):
        raise InputError("--fixture must be a local file, not a URL")
    file_path = pathlib.Path(path)
    try:
        if not file_path.is_file():
            raise InputError("--fixture must be an existing local file")
        raw = file_path.read_bytes()
    except OSError as exc:
        raise SkillFailure(2, "could not read the local fixture") from exc
    if len(raw) > MAX_BYTES:
        raise SkillFailure(6, "fixture exceeded the metadata byte cap")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillFailure(6, "fixture was not UTF-8 JSON") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillFailure(6, "fixture was not valid JSON") from exc


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillFailure(6, f"catalogue {label} is missing")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillFailure(6, f"catalogue {label} is not a string")
    text = value.strip()
    return text or None


def _official_url(value: Any, label: str) -> str | None:
    if value is None:
        return None
    text = _non_empty_string(value, label)
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        raise SkillFailure(6, f"catalogue {label} is not on {HOST}")
    return text


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SkillFailure(6, f"catalogue {label} must be a non-negative integer")
    return value


def parse_search_document(
    payload: Any,
    *,
    limit: int,
    link_header: str | None = None,
) -> tuple[list[dict[str, Any]], bool, str | None, dict[str, str]]:
    next_page = False
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        rows = payload["results"]
        next_page = bool(payload.get("next"))
    else:
        raise SkillFailure(6, "catalogue search was not a JSON list")
    next_url, last_url, has_next = parse_link_header(link_header)
    truncated = next_page or has_next or len(rows) > limit
    selected = rows[:limit]
    results = []
    published_values: list[str] = []
    for row in selected:
        if not isinstance(row, dict):
            raise SkillFailure(6, "catalogue search item was not an object")
        record: dict[str, Any] = {
            "id": _count(row.get("id"), "id"),
            "type": _non_empty_string(row.get("type"), "type"),
            "title": _non_empty_string(row.get("title"), "title"),
        }
        if record["id"] == 0:
            raise SkillFailure(6, "catalogue id must be a positive integer")
        published = _optional_string(row.get("published_at"), "published_at")
        if published:
            record["published_at"] = published
            published_values.append(published)
        first_published = _optional_string(row.get("first_published_at"), "first_published_at")
        if first_published:
            record["first_published_at"] = first_published
        official = _official_url(row.get("url"), "url") if row.get("url") is not None else None
        if official:
            record["url"] = official
        results.append(record)
    latest = published_values[0] if published_values and all(value == published_values[0] for value in published_values) else None
    page: dict[str, str] = {}
    if next_url:
        page["next"] = next_url
    if last_url:
        page["last"] = last_url
    return results, truncated, latest, page


def _licence_record(document: dict[str, Any]) -> dict[str, str]:
    licence = document.get("license")
    if not isinstance(licence, dict):
        raise SkillFailure(7, "layer licence is missing; refusing rather than assuming reuse terms")
    raw_type = licence.get("type")
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise SkillFailure(7, "layer license.type is missing; refusing rather than assuming an open licence")
    licence_type = raw_type.strip().casefold()
    title = licence.get("title")
    title_text = title.strip() if isinstance(title, str) else ""
    folded_title = title_text.casefold()
    if any(marker in folded_title for marker in CLOSED_TITLE_MARKERS):
        raise SkillFailure(7, f"layer licence is not an open attribution licence ({title_text or licence_type})")
    if licence_type != OPEN_ATTRIBUTION_TYPE:
        raise SkillFailure(7, f"layer licence is not an open attribution licence ({licence_type})")
    version = licence.get("version")
    version_text = ""
    if version is not None:
        if not isinstance(version, str):
            raise SkillFailure(6, "layer license.version is not a string")
        version_text = version.strip()
        if version_text and version_text not in OPEN_ATTRIBUTION_VERSIONS:
            raise SkillFailure(7, f"layer licence version is not a known Creative Commons Attribution version ({version_text})")
    record = {"license_type": licence_type}
    if version_text:
        record["license_version"] = version_text
    if title_text:
        record["license_title"] = title_text
    return record


def _field_names(data: dict[str, Any]) -> tuple[list[str], str]:
    if "fields" not in data:
        raise SkillFailure(6, "layer field list is missing")
    fields = data.get("fields")
    if fields is None:
        return [], "absent"
    if not isinstance(fields, list):
        raise SkillFailure(6, "layer field list is not a list")
    names: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            raise SkillFailure(6, "layer field entry is not an object")
        name = field.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SkillFailure(6, "layer field name is missing")
        names.append(name)
    return names, "present" if names else "empty"


def parse_layer_document(payload: Any, *, layer_id: str) -> tuple[dict[str, Any], str, str | None]:
    if not isinstance(payload, dict):
        raise SkillFailure(6, "layer document was not a JSON object")
    document_id = payload.get("id")
    if type(document_id) is not int or str(document_id) != layer_id:
        raise SkillFailure(6, "layer document id did not match the requested id")
    document_type = _non_empty_string(payload.get("type"), "type")
    if document_type != "layer":
        raise SkillFailure(7, f"catalogue document type is {document_type}, not a layer")
    licence = _licence_record(payload)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SkillFailure(6, "layer data object is missing")
    if "feature_count" not in data:
        raise SkillFailure(6, "layer feature_count is missing")
    names, fields_state = _field_names(data)
    record: dict[str, Any] = {
        "id": document_id,
        "type": document_type,
        "title": _non_empty_string(payload.get("title"), "title"),
        "feature_count": _count(data.get("feature_count"), "feature_count"),
        "field_names": names,
        "fields_state": fields_state,
        **licence,
    }
    for source_key, output_key in (
        ("kind", "kind"),
        ("public_access", "public_access"),
        ("geometry_type", "geometry_type"),
        ("crs", "crs"),
    ):
        text = _optional_string(data.get(source_key) if source_key in {"geometry_type", "crs"} else payload.get(source_key), source_key)
        if text:
            record[output_key] = text
    published = _optional_string(payload.get("published_at"), "published_at")
    if published:
        record["published_at"] = published
    official = _official_url(payload.get("url"), "url") if payload.get("url") is not None else None
    if official:
        record["url"] = official
    group = payload.get("group")
    if isinstance(group, dict):
        group_name = _optional_string(group.get("name"), "group name")
        if group_name:
            record["catalogue_group"] = group_name
    licence_text = record.get("license_title") or "cc-by"
    if record.get("license_version") and "license_title" not in record:
        licence_text = f"cc-by {record['license_version']}"
    return record, licence_text, published


def _meta(source_url: str, *, licence: str | None = None, latest_data: str | None = None) -> dict[str, str]:
    return provenance(source_url, PUBLISHER, licence=licence, latest_data=latest_data)


def emit_error(code: int, message: str, source_url: str, *, as_json: bool, retry_after: str | None = None) -> int:
    if as_json:
        print(json.dumps(
            error_envelope(code, message, _meta(source_url), retry_after=retry_after),
            indent=2,
            ensure_ascii=False,
        ))
    else:
        print(f"mfe-data-service: {message}", file=sys.stderr)
    return code


def emit_success(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    kind = payload["query"]["command"]
    if kind == "search":
        query = payload["query"]["text"]
        print(f"MfE catalogue for {query!r}: {len(payload['results'])} shown")
        for row in payload["results"]:
            published = str(row.get("published_at") or "")[:10]
            print(f"- {row['id']} {row['type']} {row['title']} | published: {published or 'unknown'}")
        if payload.get("truncated"):
            print("More catalogue rows exist; this command does not page further.")
        page = payload.get("page")
        if isinstance(page, dict):
            next_page = page.get("next")
            last_page = page.get("last")
            if isinstance(next_page, str):
                print(f"next page: {next_page}")
            if isinstance(last_page, str):
                print(f"last page: {last_page}")
        return 0
    row = payload["results"][0]
    print(f"{row['id']} {row['title']}")
    print(f"licence: {payload['meta'].get('licence', row.get('license_type'))} ({row.get('license_type')})")
    print(f"feature_count: {row['feature_count']}")
    print(f"fields: {', '.join(row['field_names']) if row['field_names'] else '(none declared)'}")
    return 0


def load_document(url: str, fixture: str | None, transport: Transport) -> CatalogueDocument:
    if fixture is not None:
        return CatalogueDocument(load_fixture(fixture))
    try:
        result = transport(url)
    except SkillFailure:
        raise
    except (nzfetch.FetchError, nzfetch.Blocked, TimeoutError, OSError) as exc:
        code, message, retry_after = outcome_for_exception(exc)
        raise SkillFailure(code, message, retry_after=retry_after) from exc
    if isinstance(result, CatalogueDocument):
        return result
    return CatalogueDocument(result)


def run_search(query: str, limit: int, fixture: str | None, transport: Transport) -> dict[str, Any]:
    source_url = catalogue_url("data/", {"q": query, "page_size": str(limit)})
    document = load_document(source_url, fixture, transport)
    results, truncated, latest, page = parse_search_document(
        document.body,
        limit=limit,
        link_header=document.link_header,
    )
    envelope = result_envelope(results, _meta(source_url, latest_data=latest))
    envelope["query"] = {"command": "search", "text": query, "limit": limit}
    envelope["truncated"] = truncated
    if page:
        envelope["page"] = page
    return envelope


def run_layer(layer_id: str, fixture: str | None, transport: Transport) -> dict[str, Any]:
    source_url = catalogue_url(f"layers/{layer_id}/")
    document = load_document(source_url, fixture, transport)
    record, licence, latest = parse_layer_document(document.body, layer_id=layer_id)
    envelope = result_envelope([record], _meta(source_url, licence=licence, latest_data=latest))
    envelope["query"] = {"command": "layer", "id": layer_id}
    return envelope


def main(argv: list[str] | None = None, *, transport: Transport | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = ArgumentParser(description="Search and inspect public MfE Koordinates catalogue layers")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="search the public MfE catalogue")
    search.add_argument("query", type=search_query_value)
    search.add_argument("--limit", type=limit_value, default=10, help=f"maximum rows, 1-{MAX_LIMIT}")
    search.add_argument("--fixture", help="replay a local JSON catalogue document instead of the network")
    search.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    layer = sub.add_parser("layer", help="read one layer's metadata, fields, feature count and licence")
    layer.add_argument("id", type=layer_id_value)
    layer.add_argument("--fixture", help="replay a local JSON layer document instead of the network")
    layer.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        return emit_error(2, str(exc), SOURCE_URL, as_json="--json" in argv)
    active_transport = transport or default_transport
    try:
        if args.command == "search":
            payload = run_search(args.query, args.limit, args.fixture, active_transport)
        else:
            payload = run_layer(args.id, args.fixture, active_transport)
    except InputError as exc:
        return emit_error(2, str(exc), SOURCE_URL, as_json=args.json)
    except SkillFailure as exc:
        try:
            if args.command == "search":
                source_url = catalogue_url("data/", {"q": args.query, "page_size": str(args.limit)})
            else:
                source_url = catalogue_url(f"layers/{args.id}/")
        except SkillFailure:
            source_url = SOURCE_URL
        return emit_error(exc.code, str(exc), source_url, as_json=args.json, retry_after=exc.retry_after)
    return emit_success(payload, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
