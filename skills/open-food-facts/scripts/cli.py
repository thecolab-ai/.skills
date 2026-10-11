#!/usr/bin/env python3
"""Read-only Open Food Facts barcode lookup and bounded taxonomy search."""
from __future__ import annotations

import argparse
import http.client
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

from provenance import error_envelope, provenance, result_envelope  # noqa: E402

HOST = "world.openfoodfacts.org"
ORIGIN = f"https://{HOST}"
ALLOWED_HOSTS = frozenset({HOST})
PUBLISHER = "Open Food Facts"
LICENCE = (
    "Open Database License (ODbL) for the database; "
    "Database Contents License (DbCL) for individual contents. "
    "Product images are CC BY-SA 3.0 and are not retrieved."
)
USER_AGENT = "TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 262144
MAX_JSON_DEPTH = 16
MAX_TAGS = 12
MAX_TEXT = 400
MAX_LIMIT = 10
PRODUCT_FIELDS = (
    "product_name",
    "brands",
    "quantity",
    "categories_tags",
    "countries_tags",
    "ingredients_text",
    "nutriscore_grade",
    "nova_group",
    "allergens_tags",
    "labels_tags",
)
SEARCH_FIELDS = (
    "code",
    "product_name",
    "brands",
    "categories_tags",
    "countries_tags",
)
TAG_FIELDS = {"categories_tags", "countries_tags", "allergens_tags", "labels_tags"}
STRING_FIELDS = {"product_name", "brands", "quantity", "ingredients_text", "nutriscore_grade"}
BARCODE_RE = re.compile(r"[0-9]{8,14}")
FIXTURE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,48}")
TAG_RE = re.compile(r"[a-z]{2}:[a-z0-9]+(?:-[a-z0-9]+)*")


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


def source_meta(url: str, *, latest_data: str | None = None) -> dict[str, str]:
    return provenance(url, PUBLISHER, licence=LICENCE, latest_data=latest_data)


def parse_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 10")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 10")
    return number


def normalise_barcode(value: str) -> str:
    text = value.strip()
    if not BARCODE_RE.fullmatch(text):
        raise InputError(
            "barcode must be 8 to 14 digits, including any leading zeros; "
            "spaces, signs and URLs are not accepted"
        )
    return text


def normalise_tag(value: str, label: str) -> str:
    text = value.strip().lower()
    if ":" not in text:
        text = f"en:{text}"
    if not TAG_RE.fullmatch(text) or len(text) > 80:
        raise InputError(
            f"{label} must be an Open Food Facts taxonomy tag such as en:yogurts"
        )
    return text


def product_url(barcode: str) -> str:
    fields = ",".join(("code", *PRODUCT_FIELDS, "last_modified_t"))
    query = urllib.parse.urlencode({"fields": fields})
    return f"{ORIGIN}/api/v3/product/{barcode}.json?{query}"


def search_url(country: str | None, category: str | None, limit: int) -> str:
    params: dict[str, str] = {
        "page": "1",
        "page_size": str(limit),
        "fields": ",".join(SEARCH_FIELDS),
    }
    if country:
        params["countries_tags"] = country
    if category:
        params["categories_tags"] = category
    return f"{ORIGIN}/api/v2/search?{urllib.parse.urlencode(params)}"


def assert_allowed_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise UnsafeError("refusing a request outside https://world.openfoodfacts.org")


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


def _reject_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant {value}")


def parse_json_document(text: str) -> Any:
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError("upstream JSON exceeds the supported nesting depth") from exc
    except ValueError as exc:
        raise SchemaError("upstream returned malformed JSON") from exc


def latest_from_timestamp(value: Any) -> str | None:
    """`last_modified_t` is the product record's unix update time, not retrieval time."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= 4102444800:
        return None
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _message_ids(payload: dict[str, Any], key: str) -> list[str]:
    items = payload.get(key, [])
    if items is None:
        return []
    if not isinstance(items, list):
        raise SchemaError(f"{key} was not a list")
    found: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise SchemaError(f"{key} entry was not an object")
        message = item.get("message")
        if isinstance(message, dict) and isinstance(message.get("id"), str) and message["id"]:
            found.append(message["id"])
    return found


def _result_id(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise SchemaError("result was not an object")
    ident = result.get("id")
    if not isinstance(ident, str) or not ident:
        raise SchemaError("result.id was missing")
    return ident


def shape_record(product: dict[str, Any], fields: tuple[str, ...], *, requested_code: str | None) -> dict[str, Any]:
    record: dict[str, Any] = {}
    missing: list[str] = []
    if requested_code is not None:
        record["requested_code"] = requested_code
    for field in fields:
        if field not in product or product[field] in (None, ""):
            missing.append(field)
            continue
        value = product[field]
        if field == "code":
            if isinstance(value, bool) or not isinstance(value, str):
                raise SchemaError("code was not a string")
            record["code"] = value
            continue
        if field in TAG_FIELDS:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise SchemaError(f"{field} was not a list of strings")
            record[field] = value[:MAX_TAGS]
            if len(value) > MAX_TAGS:
                record[f"{field}_truncated"] = True
            continue
        if field == "ingredients_text":
            if not isinstance(value, str):
                raise SchemaError("ingredients_text was not a string")
            record[field] = value[:MAX_TEXT]
            if len(value) > MAX_TEXT:
                record["ingredients_text_truncated"] = True
            continue
        if field == "nova_group":
            if isinstance(value, bool) or not isinstance(value, int):
                raise SchemaError("nova_group was not an integer")
            record[field] = value
            continue
        if field in STRING_FIELDS:
            if not isinstance(value, str):
                raise SchemaError(f"{field} was not a string")
            record[field] = value
            continue
        raise SchemaError(f"unexpected field {field}")
    if requested_code is not None and record.get("code") not in {None, requested_code}:
        record["source_code"] = record["code"]
        record["code"] = requested_code
    if missing:
        record["missing_fields"] = missing
    return record


def interpret_product(http_status: int, payload: Any, barcode: str) -> tuple[list[dict[str, Any]], list[str], str | None]:
    if http_status >= 500:
        raise UpstreamError(f"upstream unavailable (HTTP {http_status})")
    if http_status not in {200, 404}:
        raise UpstreamError(f"upstream unavailable (HTTP {http_status})")
    if not isinstance(payload, dict):
        raise SchemaError("product response was not a JSON object")
    status = payload.get("status")
    if not isinstance(status, str):
        raise SchemaError("product status was not a string; HTTP success is not a product result")
    ident = _result_id(payload)
    if status == "failure" and ident == "product_found_with_a_different_product_type":
        raise UnsafeError(
            "source result product_found_with_a_different_product_type; "
            "this skill stays on world.openfoodfacts.org and does not follow other product hosts"
        )
    warnings = [f"source message: {item}" for item in _message_ids(payload, "warnings")]
    errors = [f"source message: {item}" for item in _message_ids(payload, "errors")]
    if status == "failure" and ident == "product_not_found":
        notice = [f"source result: {ident}", *errors, *warnings]
        returned = payload.get("code")
        if isinstance(returned, str) and returned != barcode:
            notice.append(f"source normalised the barcode to {returned}")
        return [], notice, None
    if http_status != 200 or status not in {"success", "success_with_warnings"} or ident != "product_found":
        raise SchemaError(
            f"unexpected product result HTTP {http_status} status {status} result {ident}"
        )
    product = payload.get("product")
    if not isinstance(product, dict):
        raise SchemaError("product object was missing")
    record = shape_record(product, ("code", *PRODUCT_FIELDS), requested_code=barcode)
    return [record], [*errors, *warnings], latest_from_timestamp(product.get("last_modified_t"))


def interpret_search(http_status: int, payload: Any, limit: int) -> tuple[list[dict[str, Any]], list[str], str | None]:
    if http_status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {http_status})")
    if not isinstance(payload, dict):
        raise SchemaError("search response was not a JSON object")
    products = payload.get("products")
    count = payload.get("count")
    if not isinstance(products, list):
        raise SchemaError("search products was not a list")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise SchemaError("search count was not a non-negative integer")
    if count == 0 and products:
        raise SchemaError("search count was 0 but products were returned")
    if isinstance(count, int) and count > 0 and not products:
        raise SchemaError("search count was positive but products were empty")
    records: list[dict[str, Any]] = []
    for product in products[:limit]:
        if not isinstance(product, dict):
            raise SchemaError("search product was not an object")
        records.append(shape_record(product, SEARCH_FIELDS, requested_code=None))
    warnings: list[str] = []
    if isinstance(count, int):
        warnings.append(f"source count: {count}")
    if len(products) > limit:
        warnings.append("response truncated to the requested limit")
    return records, warnings, None


def _read_http_error(exc: urllib.error.HTTPError) -> tuple[int, str]:
    """Read an HTTP error body. urllib leaves Content-Encoding compressed."""
    try:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, http.client.HTTPException):
        raw = b""
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpstreamError("upstream response exceeds the safety cap")
    encoding = exc.headers.get("Content-Encoding") if exc.headers is not None else None
    if not encoding and raw.startswith(b"\x1f\x8b"):
        encoding = "gzip"
    try:
        decoded = nzfetch._decompress(raw, encoding, MAX_RESPONSE_BYTES)
    except (nzfetch.FetchError, OSError, ValueError) as err:
        raise SchemaError("upstream returned an unreadable response body") from err
    return exc.code, decoded.decode("utf-8", "replace")


def classify_fetch_error(exc: nzfetch.FetchError) -> tuple[int, str] | None:
    cause = exc.__cause__
    if isinstance(cause, urllib.error.HTTPError) and cause.code in {404, 500, 502, 503, 504}:
        return _read_http_error(cause)
    return None


def retrieve(url: str) -> tuple[int, str]:
    assert_allowed_url(url)
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            accept="application/json",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            browser_headers=False,
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_RESPONSE_BYTES,
            expect_json=True,
        )
    except nzfetch.RateLimited as exc:
        raise BlockedError(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            retry_after=exc.retry_after,
        ) from exc
    except nzfetch.Blocked as exc:
        raise BlockedError(f"network error: {exc}") from exc
    except nzfetch.FetchError as exc:
        message = str(exc)
        if "allowlist" in message or "downgrade" in message:
            raise UnsafeError(
                "refusing off-host redirect; requests stay on world.openfoodfacts.org"
            ) from exc
        recovered = classify_fetch_error(exc)
        if recovered is not None:
            return recovered
        if "timed out" in message.lower() or isinstance(exc.__cause__, TimeoutError):
            raise UpstreamError("network error: source request timed out") from exc
        raise UpstreamError(f"upstream unavailable: {exc}") from exc
    assert_allowed_url(final_url)
    if len(body) > MAX_RESPONSE_BYTES:
        raise UpstreamError("upstream response exceeds the safety cap")
    return 200, body.decode("utf-8")


def fixture_file(name: str) -> pathlib.Path:
    if not FIXTURE_RE.fullmatch(name):
        raise InputError("fixture name is not allowed")
    root = (pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures").resolve()
    path = (root / f"{name}.json").resolve()
    if path.parent != root or not path.is_file():
        raise InputError("fixture is not available")
    return path


def load_fixture(name: str) -> tuple[int, str]:
    try:
        payload = json.loads(fixture_file(name).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError("fixture JSON is malformed") from exc
    if not isinstance(payload, dict):
        raise InputError("fixture is not a response fixture")
    transport = payload.get("transport")
    if transport == "rate_limited":
        retry_after = payload.get("retry_after")
        retry_text = retry_after if isinstance(retry_after, str) else None
        raise BlockedError(
            f"network error: rate_limited: retry_after={retry_text}: fixture",
            retry_after=retry_text,
        )
    if transport == "unavailable":
        status = payload.get("status")
        code = status if isinstance(status, int) else 503
        raise UpstreamError(f"upstream unavailable (HTTP {code})")
    if transport == "timeout":
        raise UpstreamError("network error: source request timed out")
    if transport == "off_host_redirect":
        raise UnsafeError("refusing off-host redirect; requests stay on world.openfoodfacts.org")
    if "body_raw" in payload:
        body = payload.get("body_raw")
        status = payload.get("http_status", 200)
        if not isinstance(body, str) or isinstance(status, bool) or not isinstance(status, int):
            raise InputError("fixture is not a response fixture")
        return status, body
    if "body" in payload:
        status = payload.get("http_status", 200)
        if isinstance(status, bool) or not isinstance(status, int):
            raise InputError("fixture is not a response fixture")
        return status, json.dumps(payload["body"])
    raise InputError("fixture is not a response fixture")


def response_for(url: str, fixture: str | None) -> tuple[int, str]:
    if fixture:
        return load_fixture(fixture)
    return retrieve(url)


def emit_success(
    results: list[dict[str, Any]],
    meta: dict[str, str],
    lines: list[str],
    as_json: bool,
    warnings: list[str] | None = None,
) -> int:
    if as_json:
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
    as_json: bool,
    *,
    retry_after: str | None = None,
) -> int:
    if as_json:
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"open-food-facts: {message}", file=sys.stderr)
    return code


def human_product(record: dict[str, Any], url: str) -> list[str]:
    lines = [f"Open Food Facts barcode {record.get('requested_code') or record.get('code')}"]
    labels = (
        ("product_name", "Name"),
        ("brands", "Brands"),
        ("quantity", "Quantity"),
        ("nutriscore_grade", "Published Nutri-Score grade"),
        ("nova_group", "Published NOVA group"),
    )
    for key, label in labels:
        if key in record:
            lines.append(f"{label}: {record[key]}")
    for key, label in (("categories_tags", "Categories"), ("countries_tags", "Countries"), ("allergens_tags", "Allergens"), ("labels_tags", "Labels")):
        if key in record:
            lines.append(f"{label}: {', '.join(record[key])}")
    if "ingredients_text" in record:
        lines.append(f"Ingredients: {record['ingredients_text']}")
    if record.get("source_code"):
        lines.append(f"Source barcode after normalisation: {record['source_code']}")
    missing = record.get("missing_fields") or []
    if missing:
        lines.append("Missing optional fields: " + ", ".join(missing))
    lines.append(f"Source: {url}")
    lines.append(f"Licence: {LICENCE}")
    return lines


def human_search(records: list[dict[str, Any]], url: str, warnings: list[str]) -> list[str]:
    lines = [f"Open Food Facts search ({len(records)} shown, first page only)"]
    for warning in warnings:
        lines.append(warning.capitalize() if warning.startswith("source") else warning)
    if not records:
        lines.append("No products matched.")
    for record in records:
        name = record.get("product_name") or "(name missing)"
        brands = f" ({record['brands']})" if record.get("brands") else ""
        lines.append(f"- {record.get('code', '(code missing)')} {name}{brands}")
    lines.append(f"Source: {url}")
    lines.append("This command does not page further and does not run full-text search.")
    return lines


def guarded_payload(status: int, body: str) -> Any:
    """HTTP 5xx is an outage even when the body is not JSON."""
    if status == 429:
        raise BlockedError(f"network error: rate_limited: retry_after=None: HTTP {status}")
    if status >= 500 or status in {401, 403}:
        raise UpstreamError(f"upstream unavailable (HTTP {status})") if status >= 500 else BlockedError(
            f"network error: upstream access blocked (HTTP {status})"
        )
    return parse_json_document(body)


def run_product(args: argparse.Namespace) -> int:
    barcode = normalise_barcode(args.barcode)
    url = product_url(barcode)
    meta = source_meta(url)
    try:
        status, body = response_for(url, args.fixture)
        payload = guarded_payload(status, body)
        results, warnings, latest = interpret_product(status, payload, barcode)
    except (BlockedError, UpstreamError, SchemaError, UnsafeError) as exc:
        exc.attempt_url = url  # type: ignore[attr-defined]
        raise
    if latest:
        meta = source_meta(url, latest_data=latest)
    if args.fixture:
        warnings = [f"fixture: {args.fixture}; not a live Open Food Facts response", *warnings]
    if not results:
        lines = [f"No Open Food Facts product for barcode {barcode}.", *warnings, f"Source: {url}"]
        return emit_success([], meta, lines, args.json, warnings)
    lines = human_product(results[0], url)
    if warnings:
        lines[1:1] = warnings
    return emit_success(results, meta, lines, args.json, warnings or None)


def run_search(args: argparse.Namespace) -> int:
    if not args.country and not args.category:
        raise InputError("search requires --country, --category, or both")
    country = normalise_tag(args.country, "--country") if args.country else None
    category = normalise_tag(args.category, "--category") if args.category else None
    url = search_url(country, category, args.limit)
    meta = source_meta(url)
    try:
        status, body = response_for(url, args.fixture)
        payload = guarded_payload(status, body)
        results, warnings, _latest = interpret_search(status, payload, args.limit)
    except (BlockedError, UpstreamError, SchemaError, UnsafeError) as exc:
        exc.attempt_url = url  # type: ignore[attr-defined]
        raise
    if args.fixture:
        warnings = [f"fixture: {args.fixture}; not a live Open Food Facts response", *warnings]
    return emit_success(results, meta, human_search(results, url, warnings), args.json, warnings or None)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Read-only Open Food Facts product lookup")
    sub = parser.add_subparsers(dest="command", required=True)
    product = sub.add_parser("product", help="look up one food product by barcode")
    product.add_argument("barcode", help="8 to 14 digits; leading zeros are preserved")
    product.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    product.add_argument("--fixture", help="named synthetic fixture under tests/fixtures; not a live lookup")
    search = sub.add_parser("search", help="one page of v2 country or category search")
    search.add_argument("--country", help="taxonomy tag, for example new-zealand or en:new-zealand")
    search.add_argument("--category", help="taxonomy tag, for example yogurts or en:yogurts")
    search.add_argument("--limit", type=parse_limit, default=5, help="page size from 1 to 10 (default 5)")
    search.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    search.add_argument("--fixture", help="named synthetic fixture under tests/fixtures; not a live lookup")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "product":
            return run_product(args)
        if args.command == "search":
            return run_search(args)
        raise InputError(f"unsupported command: {args.command}")
    except InputError as exc:
        return emit_error(2, str(exc), source_meta(getattr(exc, "attempt_url", ORIGIN)), "--json" in argv)
    except BlockedError as exc:
        return emit_error(
            4, str(exc), source_meta(getattr(exc, "attempt_url", ORIGIN)), "--json" in argv, retry_after=exc.retry_after
        )
    except UpstreamError as exc:
        return emit_error(5, str(exc), source_meta(getattr(exc, "attempt_url", ORIGIN)), "--json" in argv)
    except SchemaError as exc:
        return emit_error(6, str(exc), source_meta(getattr(exc, "attempt_url", ORIGIN)), "--json" in argv)
    except UnsafeError as exc:
        return emit_error(7, str(exc), source_meta(getattr(exc, "attempt_url", ORIGIN)), "--json" in argv)


if __name__ == "__main__":
    raise SystemExit(main())
