#!/usr/bin/env python3
"""Run any executable skill through the common JSON result contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from result_contract import (  # noqa: E402
    VALID_EXIT_CODES,
    classify_legacy_error,
    result_envelope,
    validate_result_envelope,
)
from skill_metadata import load_skill  # noqa: E402

SENSITIVE_ENV_NAME = re.compile(
    r"(?:^|_)(?:API_?KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?|USERNAME|LOGIN|FETCH_PROXY|HTTPS_PROXY)$",
    re.IGNORECASE,
)
SENSITIVE_ARGUMENT_NAME = re.compile(
    r"(?:^|[-_])(?:api[-_]?key|token|password|secret|credential|username|login|proxy)(?:$|[-_])",
    re.IGNORECASE,
)
_MISSING = object()


def redact_secrets(text: str) -> str:
    redacted = text
    values = {
        value
        for name, value in os.environ.items()
        if SENSITIVE_ENV_NAME.search(name) and value
    }
    # Replace longer values first so an overlapping username cannot leave part
    # of a token behind. Even very short credential values are safer redacted
    # than emitted; output readability is secondary to the no-secret contract.
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def sensitive_argument_values(arguments: list[str]) -> set[str]:
    values: set[str] = set()
    capture_next = False
    for argument in arguments:
        if capture_next:
            if argument:
                values.add(argument)
            capture_next = False
            continue
        if argument.startswith("--") and "=" in argument:
            name, value = argument.split("=", 1)
            if SENSITIVE_ARGUMENT_NAME.search(name) and value:
                values.add(value)
        elif argument.startswith("-") and SENSITIVE_ARGUMENT_NAME.search(argument):
            capture_next = True
    return values


def redact_arguments(arguments: list[str]) -> list[str]:
    """Redact credential-like option values while preserving command shape."""
    redacted: list[str] = []
    redact_next = False
    for argument in arguments:
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        if argument.startswith("--") and "=" in argument:
            name, _value = argument.split("=", 1)
            if SENSITIVE_ARGUMENT_NAME.search(name):
                redacted.append(f"{name}=[REDACTED]")
                continue
        redacted.append(argument)
        if argument.startswith("-") and SENSITIVE_ARGUMENT_NAME.search(argument):
            redact_next = True
    return redacted


def redact_command_output(text: str, arguments: list[str]) -> str:
    redacted = redact_secrets(text)
    for value in sorted(sensitive_argument_values(arguments), key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def emit_envelope(payload: dict[str, object]) -> None:
    errors = validate_result_envelope(payload)
    if errors:
        raise RuntimeError("invalid common result envelope: " + "; ".join(errors))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def json_objects(text: str) -> list[dict[str, object]]:
    """Parse a stream made only of one or more whitespace-separated JSON objects."""
    stripped = text.strip()
    if not stripped:
        return []
    decoder = json.JSONDecoder()
    objects: list[dict[str, object]] = []
    offset = 0
    try:
        while offset < len(stripped):
            value, end = decoder.raw_decode(stripped, offset)
            if not isinstance(value, dict):
                return []
            objects.append(value)
            offset = end
            while offset < len(stripped) and stripped[offset].isspace():
                offset += 1
    except (json.JSONDecodeError, TypeError):
        return []
    return objects


def json_like(text: str) -> bool:
    """Return whether a stream begins like JSON or a common JSON-like token."""
    raw = text.strip()
    if not raw:
        return False
    if raw.startswith("\ufeff"):
        return True
    stripped = raw.lstrip()
    if stripped[:1] in {"{", "[", '"', "-", "~"} or stripped[:1].isdigit():
        return True
    token = stripped.casefold()
    reserved_prefixes = (
        "true",
        "false",
        "null",
        "none",
        "nil",
        "undefined",
        "nan",
        "infinity",
        "+infinity",
        "-infinity",
    )
    return token.startswith(reserved_prefixes)


def json_object(text: str) -> dict[str, object] | None:
    """Parse exactly one top-level JSON object from a command stream."""
    objects = json_objects(text)
    return objects[0] if len(objects) == 1 else None


def looks_like_result_envelope(payload: dict[str, object]) -> bool:
    """Distinguish a direct result envelope from legacy JSON command data."""
    envelope_fields = {"schema_version", "ok", "source", "query", "data", "warnings", "blocked"}
    return "schema_version" in payload or len(envelope_fields.intersection(payload)) >= 4


def payload_advertises_failure(payload: dict[str, object]) -> bool:
    """Return whether one JSON object contains failure result markers."""
    status = payload.get("status")
    for marker in ("ok", "blocked", "success"):
        if marker in payload and not isinstance(payload[marker], bool):
            return True
    if payload.get("ok") is False or payload.get("blocked") is True:
        return True
    if payload.get("success") is False:
        return True
    if "status" in payload:
        if not isinstance(status, str):
            return True
        if status.strip().lower() not in {"ok", "success"}:
            return True

    error = payload.get("error")
    if error not in (None, "", {}):
        return True

    # A top-level numeric/status code paired with a message is an incomplete
    # failure envelope, not ordinary command data. Fail closed rather than
    # nesting it under an apparently successful wrapper envelope.
    return "code" in payload and "message" in payload


def advertised_failure(text: str) -> bool:
    """Return whether a JSON command stream advertises failure or contradicts success.

    This check deliberately runs before direct-envelope forwarding. Otherwise a
    valid success envelope on stdout could hide a structured failure on stderr,
    or a partial ``{"ok": false, ...}`` result could be nested as successful
    legacy data. Complete JSON arrays and scalar values are valid legacy data;
    failure markers only have meaning on top-level objects.
    """
    stripped = text.strip()
    if not stripped:
        return False
    try:
        value = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        if json_like(text):
            return True
        for line in text.splitlines()[1:]:
            try:
                line_value = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                # Plain diagnostics may contain JSON-like fragments (for
                # example argparse metavars). Only complete JSON values on a
                # later line are eligible for structured-failure inspection.
                if len(json_objects(line)) > 1:
                    return True
                continue
            if isinstance(line_value, dict) and payload_advertises_failure(line_value):
                return True
        return False
    if type(value) is float and stripped.casefold() in {"nan", "infinity", "+infinity", "-infinity"}:
        # Python's decoder accepts these non-standard constants, but they are
        # not valid JSON scalar outputs and historically failed closed here.
        return True
    return isinstance(value, dict) and payload_advertises_failure(value)


def direct_result_envelope(
    *,
    stdout: str,
    stderr: str,
    returncode: int,
) -> tuple[dict[str, object] | None, list[str]]:
    """Find and validate an envelope emitted directly by a skill CLI.

    Successful CLIs conventionally emit JSON on stdout; failed CLIs may emit a
    structured result on either stream. A payload that advertises itself as an
    envelope is never silently treated as legacy data when it is malformed.
    """
    streams = (stdout, stderr) if returncode == 0 else (stderr, stdout)
    candidates: list[tuple[int, dict[str, object], list[str]]] = []
    for stream_index, stream in enumerate(streams):
        payload = json_object(stream)
        if payload is None or not looks_like_result_envelope(payload):
            continue
        errors = validate_result_envelope(payload)
        if not errors:
            if returncode == 0 and payload.get("ok") is not True:
                errors.append("zero exit status must emit a successful result")
            elif returncode != 0:
                error = payload.get("error")
                error_code = error.get("code") if isinstance(error, dict) else None
                if payload.get("ok") is not False:
                    errors.append("non-zero exit status must emit a failed result")
                if error_code != returncode:
                    errors.append("result error.code must match the command exit status")
        candidates.append((stream_index, payload, errors))

    if not candidates:
        return None, []

    combined_errors = [error for _index, _payload, errors in candidates for error in errors]
    if len(candidates) > 1:
        combined_errors.append("multiple result envelopes emitted across stdout and stderr")
    else:
        selected_index = candidates[0][0]
        opposing_stream = streams[1 - selected_index].strip()
        if opposing_stream and (json_objects(opposing_stream) or json_like(opposing_stream)):
            combined_errors.append(
                "direct result envelope accompanied by structured or malformed JSON on the opposing stream"
            )
    if combined_errors:
        return candidates[0][1], combined_errors
    return candidates[0][1], []


def structured_legacy_error(text: str) -> dict[str, object] | None:
    """Extract useful fields from a pre-envelope JSON failure payload."""
    payload = json_object(text)
    if payload is None or looks_like_result_envelope(payload):
        return None
    raw_error = payload.get("error")
    message = payload.get("message")
    code = payload.get("code", _MISSING)
    if isinstance(raw_error, dict):
        message = message or raw_error.get("message")
        error_type = raw_error.get("type")
        if "code" in raw_error:
            code = raw_error["code"]
    else:
        error_type = raw_error
    if not isinstance(message, str) or not message.strip():
        return None
    extracted: dict[str, object] = {"message": message}
    if code is not _MISSING:
        extracted["code"] = code
    if isinstance(error_type, str) and error_type.strip():
        extracted["type"] = error_type
    details = {
        key: value
        for key, value in payload.items()
        if key not in {"code", "error", "message"}
    }
    if details:
        extracted["details"] = details
    return extracted


def command_for(skill_dir: Path, args: list[str]) -> list[str]:
    python_cli = skill_dir / "scripts" / "cli.py"
    node_cli = skill_dir / "scripts" / "cli.mjs"
    if python_cli.is_file():
        return [sys.executable, str(python_cli), *args]
    if node_cli.is_file():
        return ["node", str(node_cli), *args]
    raise FileNotFoundError("skill has no scripts/cli.py or declared legacy scripts/cli.mjs")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run-skill",
        description="Run a skill and emit the stable TheColab JSON result envelope",
    )
    parser.add_argument("skill", help="skill folder name")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="arguments passed to the skill CLI")
    args = parser.parse_args()

    skills_root = (REPO_ROOT / "skills").resolve()
    skill_dir = skills_root / args.skill
    valid_name = bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.skill))
    try:
        inside_catalogue = skill_dir.resolve().parent == skills_root
    except OSError:
        inside_catalogue = False
    if not valid_name or not inside_catalogue or not skill_dir.is_dir():
        payload = result_envelope(
            ok=False,
            source_name=args.skill,
            source_url="https://github.com/thecolab-ai/.skills",
            query={"argv": redact_arguments(list(args.arguments))},
            data=None,
            warnings=[],
            error={"code": 2, "message": f"unknown skill: {args.skill}"},
        )
        emit_envelope(payload)
        return 2
    document = load_skill(skill_dir)
    metadata = document.metadata
    cli_args = list(args.arguments)
    if cli_args and cli_args[0] == "--":
        cli_args.pop(0)
    if "--json" not in cli_args and "--help" not in cli_args and "-h" not in cli_args:
        cli_args.append("--json")
    query_args = redact_arguments(cli_args)

    try:
        completed = subprocess.run(
            command_for(skill_dir, cli_args),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        payload = result_envelope(
            ok=False,
            source_name=metadata.get("thecolab.source_owner", args.skill),
            source_url=metadata.get("thecolab.source_url", "about:blank"),
            query={"argv": query_args},
            data=None,
            warnings=[],
            error={"code": 5, "message": str(exc)},
        )
        emit_envelope(payload)
        return 5
    except subprocess.TimeoutExpired:
        payload = result_envelope(
            ok=False,
            source_name=metadata.get("thecolab.source_owner", args.skill),
            source_url=metadata.get("thecolab.source_url", "about:blank"),
            query={"argv": query_args},
            data=None,
            warnings=[],
            error={"code": 5, "message": "skill command exceeded the bounded 60-second runtime"},
        )
        emit_envelope(payload)
        return 5

    stdout = redact_command_output(completed.stdout.strip(), cli_args)
    stderr = redact_command_output(completed.stderr.strip(), cli_args)

    if completed.returncode == 0 and any(advertised_failure(stream) for stream in (stdout, stderr)):
        payload = result_envelope(
            ok=False,
            source_name=metadata["thecolab.source_owner"],
            source_url=metadata["thecolab.source_url"],
            query={"argv": query_args},
            data=None,
            warnings=[],
            error={
                "code": 6,
                "message": "CLI emitted a structured or contradictory failure with zero exit status",
            },
        )
        emit_envelope(payload)
        return 6

    direct_payload, direct_errors = direct_result_envelope(
        stdout=stdout,
        stderr=stderr,
        returncode=completed.returncode,
    )
    if direct_payload is not None:
        if direct_errors:
            payload = result_envelope(
                ok=False,
                source_name=metadata["thecolab.source_owner"],
                source_url=metadata["thecolab.source_url"],
                query={"argv": query_args},
                data=None,
                warnings=[],
                error={
                    "code": 6,
                    "message": "CLI emitted an invalid result envelope: " + "; ".join(direct_errors),
                },
            )
            emit_envelope(payload)
            return 6
        emit_envelope(direct_payload)
        return completed.returncode

    if completed.returncode == 0:
        if "--help" in cli_args or "-h" in cli_args:
            data = {"help": stdout}
        else:
            try:
                data = json.loads(stdout) if stdout else None
            except json.JSONDecodeError as exc:
                payload = result_envelope(
                    ok=False,
                    source_name=metadata["thecolab.source_owner"],
                    source_url=metadata["thecolab.source_url"],
                    query={"argv": query_args},
                    data=None,
                    warnings=[stderr] if stderr else [],
                    error={"code": 6, "message": f"CLI did not emit valid JSON: {exc.msg}"},
                )
                emit_envelope(payload)
                return 6
        payload = result_envelope(
            ok=True,
            source_name=metadata["thecolab.source_owner"],
            source_url=metadata["thecolab.source_url"],
            query={"argv": query_args},
            data=data,
            warnings=[stderr] if stderr else [],
        )
        emit_envelope(payload)
        return 0

    combined = "\n".join(part for part in (stderr, stdout) if part)
    structured_error = structured_legacy_error(stderr) or structured_legacy_error(stdout)
    structured_code = structured_error.get("code") if structured_error is not None else None
    structured_code_present = structured_error is not None and "code" in structured_error
    invalid_structured_code = structured_code_present and (
        type(structured_code) is not int
        or structured_code not in VALID_EXIT_CODES - {0}
        or structured_code != completed.returncode
    )
    if invalid_structured_code:
        exit_code = 6
    elif type(structured_code) is int:
        exit_code = structured_code
    else:
        exit_code = classify_legacy_error(completed.returncode, combined)
    blocked = exit_code == 4
    error: dict[str, object] = {
        "code": exit_code,
        "message": (
            f"CLI emitted an invalid legacy error code {structured_code!r}; "
            f"expected a stable non-zero code matching exit status {completed.returncode}"
            if invalid_structured_code
            else str(structured_error["message"])
            if structured_error is not None
            else combined or "skill command failed"
        ),
    }
    if structured_error is not None:
        error.update({key: value for key, value in structured_error.items() if key not in {"code", "message"}})
    payload = result_envelope(
        ok=False,
        source_name=metadata["thecolab.source_owner"],
        source_url=metadata["thecolab.source_url"],
        query={"argv": query_args},
        data=None,
        warnings=[],
        blocked=blocked,
        error=error,
    )
    emit_envelope(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
