#!/usr/bin/env python3
"""Stable machine-readable result and exit-code contract for executable skills."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "1"

EXIT_SUCCESS = 0
EXIT_INVALID_INPUT = 2
EXIT_MISSING_CONFIGURATION = 3
EXIT_BLOCKED = 4
EXIT_UPSTREAM_UNAVAILABLE = 5
EXIT_SCHEMA_FAILURE = 6
EXIT_UNSAFE_OPERATION = 7

VALID_EXIT_CODES = {
    EXIT_SUCCESS,
    EXIT_INVALID_INPUT,
    EXIT_MISSING_CONFIGURATION,
    EXIT_BLOCKED,
    EXIT_UPSTREAM_UNAVAILABLE,
    EXIT_SCHEMA_FAILURE,
    EXIT_UNSAFE_OPERATION,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def result_envelope(
    *,
    ok: bool,
    source_name: str,
    source_url: str,
    query: dict[str, Any],
    data: Any,
    warnings: list[str] | None = None,
    blocked: bool = False,
    retrieved_at: str | None = None,
    freshness: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source: dict[str, Any] = {
        "name": source_name,
        "url": source_url,
        "retrieved_at": retrieved_at or utc_now(),
    }
    if freshness:
        source["freshness"] = freshness
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(ok),
        "source": source,
        "query": query,
        "data": data,
        "warnings": list(warnings or []),
        "blocked": bool(blocked),
    }
    if error is not None:
        envelope["error"] = error
    return envelope


def validate_result_envelope(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["result must be a JSON object"]
    required = {"schema_version", "ok", "source", "query", "data", "warnings", "blocked"}
    missing = sorted(required - payload.keys())
    if missing:
        errors.append(f"missing result fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if not isinstance(payload.get("ok"), bool):
        errors.append("ok must be a boolean")
    if not isinstance(payload.get("blocked"), bool):
        errors.append("blocked must be a boolean")
    if not isinstance(payload.get("query"), dict):
        errors.append("query must be an object")
    if not isinstance(payload.get("warnings"), list):
        errors.append("warnings must be an array")
    elif not all(isinstance(item, str) for item in payload["warnings"]):
        errors.append("warnings must contain only strings")
    source = payload.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        for field in ("name", "url", "retrieved_at"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"source.{field} must be a non-empty string")
        url = source.get("url")
        if isinstance(url, str):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                errors.append("source.url must be an absolute HTTP(S) URL")
            if parsed.username is not None or parsed.password is not None:
                errors.append("source.url must not contain user information")
            try:
                port = parsed.port
            except ValueError:
                errors.append("source.url contains an invalid port")
            else:
                expected_port = 443 if parsed.scheme == "https" else 80
                if port is not None and port != expected_port:
                    errors.append("source.url must use the default port for its scheme")
        retrieved_at = source.get("retrieved_at")
        if isinstance(retrieved_at, str):
            try:
                retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
            except ValueError:
                errors.append("source.retrieved_at must be an ISO timestamp")
            else:
                if retrieved.tzinfo is None or retrieved.utcoffset() is None:
                    errors.append("source.retrieved_at must include a timezone")
    ok = payload.get("ok")
    error = payload.get("error")
    if ok is False:
        if not isinstance(error, dict):
            errors.append("failed results must contain an error object")
        else:
            if error.get("code") not in VALID_EXIT_CODES - {EXIT_SUCCESS}:
                errors.append("error.code must be a stable non-zero exit code")
            if not isinstance(error.get("message"), str) or not error["message"].strip():
                errors.append("error.message must be a non-empty string")
    elif ok is True and error is not None:
        errors.append("successful results must not contain error")
    if payload.get("blocked") is True and ok is not False:
        errors.append("blocked results must not be successful")
    if isinstance(error, dict):
        code = error.get("code")
        if payload.get("blocked") is True and code != EXIT_BLOCKED:
            errors.append("blocked results must use exit code 4")
        if code == EXIT_BLOCKED and payload.get("blocked") is not True:
            errors.append("exit code 4 results must set blocked true")
    return errors


def classify_legacy_error(exit_code: int, text: str) -> int:
    """Map legacy CLI failures onto the stable repository exit-code contract."""
    # Stable codes 3-7 take precedence. Legacy CLIs often use 2 for both
    # argparse errors and upstream states, so code 2 still needs classification.
    if exit_code in VALID_EXIT_CODES - {EXIT_SUCCESS, EXIT_INVALID_INPUT}:
        return exit_code
    lower = text.lower()
    if exit_code == EXIT_INVALID_INPUT and any(
        marker in lower
        for marker in (
            "usage:",
            "unrecognized arguments",
            "invalid choice",
            "the following arguments are required",
        )
    ):
        return EXIT_INVALID_INPUT
    if any(marker in lower for marker in ("captcha", "blocked", "rate limit", "rate_limited", "http 429")):
        return EXIT_BLOCKED
    if any(marker in lower for marker in ("api key", "token is required", "credential", "not set", "missing configuration")) or (
        any(marker in lower for marker in ("missing", "required"))
        and any(marker in lower for marker in ("token", "password", "api_key", "api key", "credential"))
    ):
        return EXIT_MISSING_CONFIGURATION
    if any(
        marker in lower
        for marker in (
            "unsafe",
            "unsupported operation",
            "read-only",
            "can mutate",
            "i-understand-this-can-mutate",
            "only select / with",
        )
    ):
        return EXIT_UNSAFE_OPERATION
    if any(
        marker in lower
        for marker in (
            "source schema",
            "schema changed",
            "parser failure",
            "returned non-json",
            "invalid json from",
            "unexpected response",
        )
    ):
        return EXIT_SCHEMA_FAILURE
    if any(
        marker in lower
        for marker in (
            "upstream_unavailable",
            "upstream unavailable",
            "network error",
            "failed to reach",
            "timed out",
            "timeout",
            "http 5",
        )
    ):
        return EXIT_UPSTREAM_UNAVAILABLE
    if any(marker in lower for marker in ("usage:", "invalid", "unrecognized arguments", "required:")):
        return EXIT_INVALID_INPUT
    if exit_code == EXIT_INVALID_INPUT:
        return EXIT_INVALID_INPUT
    return EXIT_UPSTREAM_UNAVAILABLE
