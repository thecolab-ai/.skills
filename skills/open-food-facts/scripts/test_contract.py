#!/usr/bin/env python3
"""Deterministic repository and parser contract for Open Food Facts."""
from __future__ import annotations

import argparse
import io
import json
import urllib.error
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from http.client import HTTPMessage
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
import sys

sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_test import audit_skill  # noqa: E402
from provenance import (  # noqa: E402
    add_spatial_arguments,
    error_envelope,
    geojson_envelope,
    parse_bbox,
    provenance,
    result_envelope,
)

import cli  # noqa: E402

DATA_COMMAND = ("product", "00012345678905", "--fixture", "product-found", "--json")


def invoke(arguments: list[str]) -> tuple[int, dict, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(arguments)
    text = stdout.getvalue()
    payload = json.loads(text) if "--json" in arguments and text else {}
    return code, payload, stderr.getvalue()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_provenance_contract() -> None:
    cases = (
        (DATA_COMMAND, 0),
        (("--thecolab-invalid-option", "--json"), 2),
    )
    for arguments, expected_code in cases:
        code, payload, stderr = invoke(list(arguments))
        require(code == expected_code, f"{arguments} exited {code}")
        require(stderr == "", stderr)
        meta = payload["meta"]
        require(bool(meta["source_url"]) and meta["publisher"] == "Open Food Facts", "provenance missing")
        require(meta["retrieved_at"].endswith("Z"), "retrieved_at was not UTC")
        retrieved = datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00"))
        require(retrieved.utcoffset() == timedelta(0), "retrieved_at was not UTC")
        require(isinstance(payload["results"], list), "results was not a list")
        if expected_code:
            require(payload["results"] == [], "error result was not empty")
            require(payload["error"]["code"] == expected_code, "error code mismatch")
            require(payload["error"]["type"] == "invalid_input", "error type mismatch")
        else:
            require("error" not in payload, "success payload contained error")

    meta = provenance("https://example.invalid/data", "Fixture publisher")
    require("licence" not in meta and "latest_data" not in meta, "unknown licence was invented")
    cached = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        licence="Fixture terms",
        latest_data="2026-09",
        retrieved_at="2026-10-01T01:02:03Z",
    )
    require(cached["licence"] == "Fixture terms" and cached["latest_data"] == "2026-09", "cached facts changed")
    require(cached["retrieved_at"] == "2026-10-01T01:02:03Z", "cached retrieval time changed")
    normalised = provenance(
        "https://example.invalid/data",
        "Fixture publisher",
        retrieved_at="2026-10-01T14:02:03+13:00",
    )
    require(normalised["retrieved_at"] == cached["retrieved_at"], "offset was not normalised to Z")
    try:
        provenance("https://example.invalid/data", "Fixture publisher", retrieved_at="2026-10-01T01:02:03")
    except ValueError:
        pass
    else:
        raise AssertionError("naive retrieval timestamp accepted")
    require(result_envelope([], cached)["results"] == [], "empty envelope dropped results")
    failure = error_envelope(4, "rate-limited", meta, retry_after="60")
    require(failure["error"]["type"] == "blocked" and failure["error"]["retry_after"] == "60", "retry_after dropped")

    require(parse_bbox("174,-37,175,-36") == (174.0, -37.0, 175.0, -36.0), "bbox parser changed")
    invalid_boxes = (
        "174,-37,175", "a,b,c,d", "nan,-37,175,-36", "174,-37,inf,-36",
        "175,-37,174,-36", "174,-36,175,-37", "-181,-37,175,-36",
        "174,-91,175,-36", "174,-37,181,-36", "174,-37,175,91", "174,-37,174,-36",
    )
    for invalid in invalid_boxes:
        try:
            parse_bbox(invalid)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"invalid bbox accepted: {invalid}")
    parser = argparse.ArgumentParser()
    add_spatial_arguments(parser)
    args = parser.parse_args(["--bbox", "174,-37,175,-36", "--format", "geojson"])
    require(args.bbox == (174.0, -37.0, 175.0, -36.0) and args.format == "geojson", "spatial args changed")
    require(parser.parse_args(["--bbox=-180,-90,180,90"]).bbox == (-180.0, -90.0, 180.0, 90.0), "negative bbox split")
    collection = geojson_envelope([], meta)
    require(collection == {"type": "FeatureCollection", "features": [], "meta": meta}, "geojson envelope changed")


def check_parser_contracts() -> None:
    url = cli.product_url("00012345678905")
    require(url.startswith("https://world.openfoodfacts.org/api/v3/product/00012345678905.json?"), "leading zero was stripped")
    require("fields=all" not in url and "image" not in url and "knowledge_panels" not in url, "field allowlist widened")
    search = cli.search_url("en:new-zealand", "en:yogurts", 1)
    require(search.startswith("https://world.openfoodfacts.org/api/v2/search?"), "search host drifted")
    require("page_size=1" in search and "page=1" in search, "search was not single-page")
    require("search_terms" not in search and "/cgi/" not in search, "full-text search was added")

    code, payload, stderr = invoke(list(DATA_COMMAND))
    require(code == 0 and stderr == "", "found fixture failed")
    record = payload["results"][0]
    require(record["code"] == "00012345678905" and record["requested_code"] == "00012345678905", "leading zeros dropped")
    require(record["product_name"] == "Fixture cocoa spread", "fixture name changed")
    require("nova_group" not in record and "nova_group" in record["missing_fields"], "missing field was invented")
    require(payload["meta"]["latest_data"] == "2024-03-09T16:00:00Z", "latest_data was not the source timestamp")
    require(payload["meta"]["licence"].startswith("Open Database License"), "data licence missing")
    require("fixture: product-found" in payload["warnings"][0], "fixture was presented as live")
    require("Traceback" not in json.dumps(payload), "fixture success traced")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "product-normalised", "--json"])
    require(code == 0 and payload["results"][0]["code"] == "00012345678905", "normalised code replaced the request")
    require(payload["results"][0]["source_code"] == "12345678905", "source code was hidden")

    code, payload, _stderr = invoke(["product", "12345670", "--fixture", "product-not-found", "--json"])
    require(code == 0 and payload["results"] == [], "not-found was not an empty success")
    require(any("product_not_found" in item for item in payload["warnings"]), "not-found warning missing")
    require("error" not in payload, "not-found was reported as an error")

    code, payload, _stderr = invoke(["product", "12345670", "--fixture", "product-http-200-not-found", "--json"])
    require(code == 0 and payload["results"] == [], "HTTP 200 failure was treated as a product")

    code, payload, _stderr = invoke(["product", "8710447445990", "--fixture", "product-other-type", "--json"])
    require(code == 7 and "different_product_type" in payload["error"]["message"], "other product type was parsed as food")
    require(payload["error"]["type"] == "unsupported_operation", "other product type was not refused")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "product-v2-status", "--json"])
    require(code == 6 and payload["error"]["type"] == "schema_failure", "v2 integer status was accepted")
    require("Traceback" not in json.dumps(payload), "schema failure traced")

    code, payload, stderr = invoke(["product", "00012345678905", "--fixture", "transport-malformed", "--json"])
    require(code == 6 and stderr == "" and payload["error"]["type"] == "schema_failure", "malformed JSON was not typed")
    require("Traceback" not in payload["error"]["message"], "malformed JSON traced")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-deep", "--json"])
    require(code == 6 and "nesting depth" in payload["error"]["message"], "deep JSON was not typed")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-nan", "--json"])
    require(code == 6 and payload["error"]["type"] == "schema_failure", "NaN JSON was accepted")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-rate-limit", "--json"])
    require(code == 4 and payload["error"]["retry_after"] == "17", "Retry-After was dropped")
    require(payload["error"]["type"] == "blocked" and payload["results"] == [], "rate limit looked empty")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-unavailable", "--json"])
    require(code == 5 and "503" in payload["error"]["message"], "503 was not unavailable")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-timeout", "--json"])
    require(code == 5 and "timed out" in payload["error"]["message"], "timeout was not unavailable")

    code, payload, _stderr = invoke(["product", "00012345678905", "--fixture", "transport-off-host", "--json"])
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host redirect was followed")

    code, payload, _stderr = invoke(["search", "--country", "new-zealand", "--fixture", "search-empty", "--json"])
    require(code == 0 and payload["results"] == [], "empty search was an error")
    require(any(item == "source count: 0" for item in payload["warnings"]), "zero count was hidden")

    code, payload, _stderr = invoke(
        ["search", "--country", "en:new-zealand", "--category", "yogurts", "--limit", "1", "--fixture", "search-found", "--json"]
    )
    require(code == 0 and payload["results"][0]["code"] == "09415522002738", "search stripped a leading zero")
    parsed_search = urllib.parse.parse_qs(urllib.parse.urlsplit(search).query)
    require(parsed_search["countries_tags"] == ["en:new-zealand"], "country tag was not encoded")
    require(parsed_search["page_size"] == ["1"] and parsed_search["page"] == ["1"], "search page was not bounded")

    for arguments in (
        ["product", "ABC", "--json"],
        ["product", "123", "--json"],
        ["product", "123456789012345", "--json"],
        ["product", "3017624010701.json", "--json"],
        ["product", "http://example.invalid/1", "--json"],
        ["search", "--limit", "0", "--country", "new-zealand", "--json"],
        ["search", "--limit", "-1", "--country", "new-zealand", "--json"],
        ["search", "--limit", "nan", "--country", "new-zealand", "--json"],
        ["search", "--limit", "999999", "--country", "new-zealand", "--json"],
        ["search", "--limit", "inf", "--country", "new-zealand", "--json"],
        ["search", "--json"],
        ["search", "--country", "../secret", "--json"],
        ["product", "00012345678905", "--fixture", "../cli", "--json"],
    ):
        code, payload, stderr = invoke(arguments)
        require(code == 2 and payload["error"]["type"] == "invalid_input", f"accepted {arguments}")
        require("Traceback" not in stderr and "Traceback" not in payload["error"]["message"], f"traced {arguments}")

    human_out, human_err = io.StringIO(), io.StringIO()
    with redirect_stdout(human_out), redirect_stderr(human_err):
        human_code = cli.main(["product", "12345670", "--fixture", "product-not-found"])
    require(human_code == 0 and "No Open Food Facts product" in human_out.getvalue(), "human not-found was unclear")
    require(human_err.getvalue() == "", "human not-found wrote stderr")


def check_transport_guards() -> None:
    original = cli.nzfetch.fetch_bytes

    def off_host(url: str, **kwargs) -> tuple[bytes, str, str]:
        require(kwargs.get("timeout") == 10, "redirect probe had no timeout")
        require(kwargs.get("allowed_hosts") == cli.ALLOWED_HOSTS, "redirect probe dropped the host allowlist")
        require(kwargs.get("headers", {}).get("User-Agent") == cli.USER_AGENT, "User-Agent was not app-specific")
        require(url.startswith("https://world.openfoodfacts.org/api/v3/product/3017624010701.json"), url)
        raise cli.nzfetch.FetchError(
            "outbound URL host is not in the declared allowlist: world.openproductsfacts.org"
        )

    cli.nzfetch.fetch_bytes = off_host
    try:
        code, payload, stderr = invoke(["product", "3017624010701", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "cross-host redirect was followed")
    require(stderr == "" and payload["results"] == [], "redirect error was noisy")

    body = json.dumps(
        {
            "status": "failure",
            "result": {"id": "product_not_found", "name": "Product not found"},
            "errors": [{"message": {"id": "product_not_found"}}],
            "warnings": [],
        }
    ).encode()

    def not_found(url: str, **_kwargs) -> tuple[bytes, str, str]:
        raise cli.nzfetch.FetchError(f"HTTP 404 from {url}") from urllib.error.HTTPError(
            url, 404, "Not Found", HTTPMessage(), io.BytesIO(body)
        )

    cli.nzfetch.fetch_bytes = not_found
    try:
        code, payload, _stderr = invoke(["product", "12345670", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 0 and payload["results"] == [], "HTTP 404 body was not an empty success")

    import gzip

    compressed = gzip.compress(body)
    gzip_headers = HTTPMessage()
    gzip_headers["Content-Encoding"] = "gzip"

    def gzip_not_found(url: str, **_kwargs) -> tuple[bytes, str, str]:
        raise cli.nzfetch.FetchError(f"HTTP 404 from {url}") from urllib.error.HTTPError(
            url, 404, "Not Found", gzip_headers, io.BytesIO(compressed)
        )

    cli.nzfetch.fetch_bytes = gzip_not_found
    try:
        code, payload, stderr = invoke(["product", "12345670", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 0 and payload["results"] == [] and stderr == "", "gzip HTTP 404 was not decompressed")
    require("malformed" not in json.dumps(payload), "gzip HTTP 404 was treated as malformed JSON")

    def unavailable(url: str, **_kwargs) -> tuple[bytes, str, str]:
        raise cli.nzfetch.FetchError(f"HTTP 503 from {url}") from urllib.error.HTTPError(
            url, 503, "Unavailable", HTTPMessage(), io.BytesIO(b"<html>busy</html>")
        )

    cli.nzfetch.fetch_bytes = unavailable
    try:
        code, payload, stderr = invoke(["product", "12345670", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 5 and "503" in payload["error"]["message"], "HTTP 503 HTML became a schema or success")
    require("Traceback" not in stderr and "<html>" not in json.dumps(payload), "503 body leaked")

    def timed_out(url: str, **_kwargs) -> tuple[bytes, str, str]:
        raise cli.nzfetch.FetchError(f"{url} unavailable after 1 attempt(s) (network error: timed out)")

    cli.nzfetch.fetch_bytes = timed_out
    try:
        code, payload, _stderr = invoke(["search", "--category", "yogurts", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 5 and "timed out" in payload["error"]["message"], "timeout was not typed")

    def limited(url: str, **_kwargs) -> tuple[bytes, str, str]:
        raise cli.nzfetch.RateLimited(f"{url} rate-limited after 1 attempt(s); retry later.", retry_after="17")

    cli.nzfetch.fetch_bytes = limited
    try:
        code, payload, _stderr = invoke(["product", "3017624010701", "--json"])
    finally:
        cli.nzfetch.fetch_bytes = original
    require(code == 4 and payload["error"]["retry_after"] == "17", "live rate-limit mapping dropped Retry-After")


def main() -> int:
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        check_provenance_contract()
        check_parser_contracts()
        check_transport_guards()
        result["checks"].extend(("provenance", "json_errors", "cached_metadata", "spatial_contract", "parser_fixtures"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
