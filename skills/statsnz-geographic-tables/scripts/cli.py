#!/usr/bin/env python3
"""Read Stats NZ Datafinder geographic-table metadata and published samples.

Only tables 122777 and 123518 are supported. The keyed query API, bulk
exports, and the created_by user profile are refused.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from provenance import error_envelope, provenance, result_envelope

HOST = "datafinder.stats.govt.nz"
ORIGIN = f"https://{HOST}"
PUBLISHER = "Stats NZ"
CANONICAL_PAGE = f"{ORIGIN}/table/122777-current-geographic-boundaries-table/"
TABLE_IDS = ("122777", "123518")
TIMEOUT_SECONDS = 15
MAX_BYTES = 262144
MAX_SAMPLE_ROWS = 200
USER_AGENT = "thecolab-statsnz-geographic-tables/1.0 (+https://github.com/thecolab-ai/.skills)"
FIXTURE_ENV = "STATSNZ_GEOGRAPHIC_TABLES_FIXTURE"
OPEN_LICENCE_TYPE = "cc-by"
OPEN_LICENCE_TITLE = "Creative Commons Attribution"

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
Transport = Callable[[str], tuple[int, dict[str, str], bytes, bool, str]]

TABLE_PATHS = {table_id: f"/services/api/v1/tables/{table_id}/" for table_id in TABLE_IDS}
LEAK_MARKER = "SHOULD_NOT_APPEAR"


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class SourceError(Exception):
    """A typed failure with a stable exit code."""

    def __init__(self, code: int, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


class AllowlistRedirectHandler(HTTPRedirectHandler):
    """Follow only HTTPS redirects that stay on a table or sample path."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        parse_allowlisted(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = build_opener(AllowlistRedirectHandler())


def table_api_url(table_id: str) -> str:
    return f"{ORIGIN}{TABLE_PATHS[table_id]}"


def parse_table_id(value: str) -> str:
    if value not in TABLE_IDS:
        raise argparse.ArgumentTypeError("table must be 122777 or 123518")
    return value


def parse_allowlisted(url: str) -> tuple[str, str]:
    """Return (kind, table_id) for a table or published-sample URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != HOST:
        raise SourceError(7, "refusing a URL whose host is outside datafinder.stats.govt.nz")
    if parsed.username is not None or parsed.password is not None:
        raise SourceError(7, "refusing a URL that contains user information")
    if parsed.query or parsed.fragment:
        raise SourceError(7, "refusing a URL with a query string; the keyed query API is not supported")
    try:
        if parsed.port not in (None, 443):
            raise SourceError(7, "refusing a URL that does not use the default HTTPS port")
    except ValueError as exc:
        raise SourceError(7, "refusing a URL with an invalid port") from exc
    path = parsed.path
    for table_id, table_path in TABLE_PATHS.items():
        if path == table_path:
            return "table", table_id
        prefix = f"/services/api/v1/tables/{table_id}/versions/"
        suffix = "/data/sample/"
        if path.startswith(prefix) and path.endswith(suffix):
            version = path[len(prefix) : -len(suffix)]
            if version.isdigit() and "/" not in version:
                return "sample", table_id
    raise SourceError(7, "refusing a URL that is not a published table or sample endpoint")


def header_value(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == name.lower() and value is not None:
                return str(value)
        return None
    value = headers.get(name)
    return None if value is None else str(value)


def fixture_bytes(name: str) -> bytes:
    path = (FIXTURE_ROOT / name).resolve()
    if path.parent != FIXTURE_ROOT.resolve():
        raise SourceError(2, "invalid fixture")
    return path.read_bytes()


def routes_for(mode: str) -> dict[str, tuple[int, dict[str, str], bytes, bool]]:
    """Map an exact request URL to a canned response. Missing keys are leaks."""
    if mode == "positive":
        table = fixture_bytes("table-positive.json")
        sample_url = json.loads(table)["data"]["sample"]
        return {
            table_api_url("122777"): (200, {}, table, False),
            sample_url: (200, {}, fixture_bytes("sample-positive.json"), False),
        }
    if mode == "empty":
        table = fixture_bytes("table-empty.json")
        sample_url = json.loads(table)["data"]["sample"]
        return {
            table_api_url("122777"): (200, {}, table, False),
            sample_url: (200, {}, fixture_bytes("sample-empty.json"), False),
        }
    if mode == "wide":
        table = fixture_bytes("table-wide.json")
        sample_url = json.loads(table)["data"]["sample"]
        return {
            table_api_url("123518"): (200, {}, table, False),
            sample_url: (200, {}, fixture_bytes("sample-wide.json"), False),
        }
    if mode == "malformed":
        return {table_api_url("122777"): (200, {"Content-Type": "application/json"}, b"{", False)}
    if mode == "schema":
        return {table_api_url("122777"): (200, {"Content-Type": "application/json"}, b"{}", False)}
    if mode == "truncated":
        return {table_api_url("122777"): (200, {}, b'{"id": 122777', True)}
    if mode == "http-429":
        return {table_api_url("122777"): (429, {"Retry-After": "17"}, b"", False)}
    if mode == "http-503":
        return {table_api_url("122777"): (503, {}, b"unavailable", False)}
    if mode == "redirect":
        return {
            table_api_url("122777"): (302, {"Location": "https://example.com/stolen"}, b"", False)
        }
    if mode == "bad-licence":
        return {table_api_url("122777"): (200, {}, fixture_bytes("table-bad-licence.json"), False)}
    if mode == "query-url":
        return {table_api_url("122777"): (200, {}, fixture_bytes("table-query-url.json"), False)}
    if mode == "off-host":
        return {table_api_url("122777"): (200, {}, fixture_bytes("table-off-host.json"), False)}
    raise SourceError(2, f"unknown fixture mode {mode!r}")


def build_transport(mode: str) -> Transport:
    if mode == "timeout":
        def timeout_transport(url: str) -> tuple[int, dict[str, str], bytes, bool, str]:
            parse_allowlisted(url)
            raise TimeoutError("timed out")

        return timeout_transport

    routes = routes_for(mode)

    def transport(url: str) -> tuple[int, dict[str, str], bytes, bool, str]:
        spec = routes.get(url)
        if spec is None:
            body = json.dumps({"sample": [["__row__", "leak"], [[1, LEAK_MARKER]]]}).encode()
            return 200, {}, body, False, url
        status, headers, body, truncated = spec
        return status, headers, body, truncated, url

    return transport


def transport_from_env() -> Transport | None:
    mode = os.environ.get(FIXTURE_ENV)
    if not mode:
        return None
    return build_transport(mode)


def decode_document(url: str, status: int, headers: Any, body: bytes, truncated: bool, final_url: str) -> Any:
    if status in {301, 302, 303, 307, 308}:
        location = header_value(headers, "Location") or ""
        try:
            parse_allowlisted(location)
        except SourceError:
            raise SourceError(7, "redirect host or path is outside the published table and sample endpoints") from None
        raise SourceError(7, "redirect did not stay on the requested table or sample URL")
    if status == 429:
        raise SourceError(
            4,
            "network error: rate_limited (HTTP 429)",
            retry_after=header_value(headers, "Retry-After"),
        )
    if status in {401, 403}:
        raise SourceError(4, f"network error: blocked (HTTP {status})")
    if status != 200:
        raise SourceError(5, f"network error: upstream unavailable (HTTP {status})")
    if truncated:
        raise SourceError(6, "source schema failure: response exceeded the byte cap and was truncated")
    requested_kind, requested_id = parse_allowlisted(url)
    final_kind, final_id = parse_allowlisted(final_url)
    if (final_kind, final_id) != (requested_kind, requested_id) or urlparse(final_url).path != urlparse(url).path:
        raise SourceError(7, "redirect changed the requested table or sample path")
    content_type = header_value(headers, "Content-Type")
    if content_type and "json" not in content_type.lower():
        raise SourceError(6, "source schema failure: response was not JSON")
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceError(6, "source schema failure: response was not JSON") from exc
    if not isinstance(document, dict):
        raise SourceError(6, "source schema failure: response JSON was not an object")
    return document


def fetch_json(url: str, transport: Transport | None) -> Any:
    parse_allowlisted(url)
    try:
        if transport is not None:
            try:
                status, headers, body, truncated, final_url = transport(url)
            except TimeoutError as exc:
                raise SourceError(5, "network error: source request timed out") from exc
        else:
            request = Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                method="GET",
            )
            try:
                with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
                    raw = response.read(MAX_BYTES + 1)
                    status, headers, body, truncated, final_url = (
                        response.status,
                        response.headers,
                        raw[:MAX_BYTES],
                        len(raw) > MAX_BYTES,
                        response.geturl(),
                    )
            except SourceError:
                raise
            except HTTPError as exc:
                raw = exc.read(MAX_BYTES + 1)
                status, headers, body, truncated, final_url = (
                    exc.code,
                    exc.headers,
                    raw[:MAX_BYTES],
                    len(raw) > MAX_BYTES,
                    exc.geturl() or url,
                )
            except TimeoutError as exc:
                raise SourceError(5, "network error: source request timed out") from exc
            except URLError as exc:
                reason = exc.reason
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    raise SourceError(5, "network error: source request timed out") from exc
                raise SourceError(5, "network error: upstream unavailable") from exc
    except SourceError:
        raise
    return decode_document(url, status, headers, body, truncated, final_url)


def require_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceError(6, f"source schema failure: missing {key}")
    return value


def require_count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceError(6, f"source schema failure: {label} is not a non-negative integer")
    return value


def licence_name(document: dict[str, Any]) -> dict[str, str]:
    licence = document.get("license")
    if not isinstance(licence, dict):
        raise SourceError(7, "source licence is missing; refusing to emit records")
    title = licence.get("title")
    licence_type = licence.get("type")
    if licence_type != OPEN_LICENCE_TYPE or not isinstance(title, str) or OPEN_LICENCE_TITLE not in title:
        raise SourceError(7, "source licence is not a confirmed Creative Commons Attribution licence")
    result = {"licence": title, "licence_type": OPEN_LICENCE_TYPE}
    version = licence.get("version")
    if isinstance(version, str) and version.strip():
        result["licence_version"] = version
    licence_url = licence.get("url_html")
    if isinstance(licence_url, str):
        try:
            parse_allowlisted(licence_url)
        except SourceError:
            # Licence pages are on this host but are not table or sample paths.
            parsed = urlparse(licence_url)
            if (
                parsed.scheme == "https"
                and (parsed.hostname or "").lower() == HOST
                and not parsed.query
                and not parsed.fragment
            ):
                result["licence_url"] = licence_url
        else:
            result["licence_url"] = licence_url
    return result


def page_url(document: dict[str, Any]) -> str:
    value = require_text(document, "url_html")
    parsed = urlparse(value)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != HOST or not parsed.path.startswith("/table/"):
        raise SourceError(6, "source schema failure: table page URL is not on datafinder.stats.govt.nz")
    return value


def published_sample(document: dict[str, Any], table_id: str) -> tuple[str, str]:
    data = document.get("data")
    version = document.get("version")
    if not isinstance(data, dict) or not isinstance(version, dict):
        raise SourceError(6, "source schema failure: table document has no data or version object")
    version_id = version.get("id")
    if isinstance(version_id, bool) or not isinstance(version_id, int):
        raise SourceError(6, "source schema failure: published version id is missing")
    sample_url = data.get("sample")
    if not isinstance(sample_url, str):
        raise SourceError(6, "source schema failure: published sample URL is missing")
    kind, sample_table = parse_allowlisted(sample_url)
    if kind != "sample" or sample_table != table_id:
        raise SourceError(7, "refusing a URL that is not the published sample for the requested table")
    path = urlparse(sample_url).path
    prefix = f"/services/api/v1/tables/{table_id}/versions/"
    version_text = path[len(prefix) : -len("/data/sample/")]
    if version_text != str(version_id):
        raise SourceError(6, "source schema failure: sample URL version does not match the published version")
    return sample_url, str(version_id)


def field_list(data: dict[str, Any]) -> list[dict[str, str]]:
    raw_fields = data.get("fields", [])
    if not isinstance(raw_fields, list):
        raise SourceError(6, "source schema failure: fields is not a list")
    fields: list[dict[str, str]] = []
    for item in raw_fields:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise SourceError(6, "source schema failure: field name is missing")
        field = {"name": item["name"]}
        if isinstance(item.get("type"), str) and item["type"].strip():
            field["type"] = item["type"]
        fields.append(field)
    return fields


def normalise_table(document: dict[str, Any], table_id: str) -> dict[str, Any]:
    if document.get("type") != "table":
        raise SourceError(6, "source schema failure: document type is not table")
    if document.get("id") != int(table_id):
        raise SourceError(6, "source schema failure: table id does not match the request")
    data = document.get("data")
    if not isinstance(data, dict):
        raise SourceError(6, "source schema failure: table document has no data object")
    sample_url, version_id = published_sample(document, table_id)
    published_at = document.get("published_at")
    if published_at is not None and not isinstance(published_at, str):
        raise SourceError(6, "source schema failure: published_at is not a string")
    record: dict[str, Any] = {
        "table_id": table_id,
        "title": require_text(document, "title"),
        "page_url": page_url(document),
        "feature_count": require_count(data.get("feature_count"), "feature_count"),
        "published_version_id": version_id,
        "sample_url": sample_url,
        "fields": field_list(data),
    }
    record.update(licence_name(document))
    if isinstance(published_at, str) and published_at.strip():
        record["published_at"] = published_at
    reject_profile(record)
    return record


def cell_value(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceError(6, "source schema failure: sample cell is not a string, number, or null")
    if isinstance(value, float) and value != value or value in {float("inf"), float("-inf")}:
        raise SourceError(6, "source schema failure: sample cell is not finite")
    return value


def parse_sample(document: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    sample = document.get("sample")
    if not isinstance(sample, list) or len(sample) != 2:
        raise SourceError(6, "source schema failure: sample payload is not a header plus rows")
    header, rows = sample
    if not isinstance(header, list) or not header or not all(isinstance(item, str) and item for item in header):
        raise SourceError(6, "source schema failure: sample header is missing")
    if len(set(header)) != len(header):
        raise SourceError(6, "source schema failure: sample header repeats a column")
    if not isinstance(rows, list):
        raise SourceError(6, "source schema failure: sample rows are missing")
    if len(rows) > MAX_SAMPLE_ROWS:
        raise SourceError(7, "published sample exceeds the row bound; refusing a bulk extract")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(header):
            raise SourceError(6, "source schema failure: sample row does not match the header")
        parsed.append(
            {
                key: cell_value(value)
                for key, value in zip(header, row)
                if key != "created_by"
            }
        )
    return [column for column in header if column != "created_by"], parsed


def reject_profile(value: Any) -> None:
    if isinstance(value, dict):
        if "created_by" in value:
            raise SourceError(6, "refusing to emit a created_by user profile")
        for item in value.values():
            reject_profile(item)
    elif isinstance(value, list):
        for item in value:
            reject_profile(item)


def run_command(command: str, table_id: str, transport: Transport | None = None) -> dict[str, Any]:
    if table_id not in TABLE_IDS:
        raise SourceError(2, "table must be 122777 or 123518")
    document = fetch_json(table_api_url(table_id), transport)
    record = normalise_table(document, table_id)
    source_url = table_api_url(table_id)
    if command == "sample":
        sample_document = fetch_json(record["sample_url"], transport)
        columns, rows = parse_sample(sample_document)
        record = {
            **record,
            "columns": columns,
            "sample_row_count": len(rows),
            "rows": rows,
        }
        source_url = record["sample_url"]
        reject_profile(record)
    elif command != "table":
        raise SourceError(2, f"unknown command {command!r}")
    return {
        "source_url": source_url,
        "licence": record["licence"],
        "latest_data": record.get("published_at"),
        "record": record,
    }


def emit_error(code: int, message: str, *, json_mode: bool, retry_after: str | None = None) -> int:
    if json_mode:
        print(json.dumps(
            error_envelope(code, message, provenance(CANONICAL_PAGE, PUBLISHER), retry_after=retry_after),
            indent=2,
            ensure_ascii=False,
        ))
    else:
        print(f"statsnz-geographic-tables: {message}", file=sys_stderr())
    return code


def sys_stderr():
    import sys
    return sys.stderr


def print_table(record: dict[str, Any]) -> None:
    print(f"{record['title']} ({record['table_id']})")
    print(f"Page: {record['page_url']}")
    print(f"Licence: {record['licence']}")
    print(f"Feature count: {record['feature_count']}")
    if record.get("published_at"):
        print(f"Published at: {record['published_at']}")
    print(f"Published version: {record['published_version_id']}")
    names = ", ".join(field["name"] for field in record["fields"])
    print(f"Fields: {names}")


def print_sample(record: dict[str, Any]) -> None:
    print_table(record)
    print(f"Published sample rows: {record['sample_row_count']}")
    columns = record["columns"][:8]
    hidden_columns = len(record["columns"]) - len(columns)
    for index, row in enumerate(record["rows"][:20], start=1):
        shown = "; ".join(f"{column}={row.get(column)}" for column in columns)
        print(f"{index}. {shown}")
    if hidden_columns or len(record["rows"]) > 20:
        print("Human output is abbreviated. --json returns the full bounded sample.")


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = sys.argv[1:] if argv is None else argv
    json_mode = "--json" in argv
    parser = ArgumentParser(description="Stats NZ Datafinder geographic table metadata and published samples")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("table", "show licence, feature count, and publication metadata"),
        ("sample", "read the published version sample only"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("table_id", type=parse_table_id, metavar="122777|123518", help="122777 or 123518")
        command.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    try:
        args = parser.parse_args(argv)
        outcome = run_command(args.command, args.table_id, transport_from_env())
    except InputError as exc:
        return emit_error(2, str(exc), json_mode=json_mode)
    except SourceError as exc:
        return emit_error(exc.code, str(exc), json_mode=json_mode, retry_after=exc.retry_after)
    meta = provenance(
        outcome["source_url"],
        PUBLISHER,
        licence=outcome["licence"],
        latest_data=outcome["latest_data"],
    )
    if args.json:
        print(json.dumps(result_envelope([outcome["record"]], meta), indent=2, ensure_ascii=False))
    elif args.command == "sample":
        print_sample(outcome["record"])
    else:
        print_table(outcome["record"])
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
