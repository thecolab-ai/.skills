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

from result_contract import classify_legacy_error, result_envelope, validate_result_envelope  # noqa: E402
from skill_metadata import load_skill  # noqa: E402


SENSITIVE_ENV_NAME = re.compile(
    r"(?:^|_)(?:API_?KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?|USERNAME|LOGIN|FETCH_PROXY|HTTPS_PROXY)$",
    re.I,
)
SENSITIVE_ARGUMENT_NAME = re.compile(
    r"(?:^|[-_])(?:api[-_]?key|token|password|secret|credential|username|login|proxy)(?:$|[-_])",
    re.I,
)


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


def json_object(text: str) -> dict[str, object] | None:
    """Return a JSON object from a command stream, or ``None`` for raw output."""
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def looks_like_result_envelope(payload: dict[str, object]) -> bool:
    """Distinguish a direct result envelope from legacy JSON command data."""
    envelope_fields = {"schema_version", "ok", "source", "query", "data", "warnings", "blocked"}
    return "schema_version" in payload or len(envelope_fields.intersection(payload)) >= 4


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
    for stream in streams:
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
        return payload, errors
    return None, []


def structured_legacy_error(text: str) -> dict[str, object] | None:
    """Extract useful fields from a pre-envelope JSON failure payload."""
    payload = json_object(text)
    if payload is None or looks_like_result_envelope(payload):
        return None
    raw_error = payload.get("error")
    message = payload.get("message")
    if isinstance(raw_error, dict):
        message = message or raw_error.get("message")
        error_type = raw_error.get("type")
    else:
        error_type = raw_error
    if not isinstance(message, str) or not message.strip():
        return None
    extracted: dict[str, object] = {"message": message}
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
    exit_code = classify_legacy_error(completed.returncode, combined)
    blocked = exit_code == 4
    structured_error = structured_legacy_error(stderr) or structured_legacy_error(stdout)
    error: dict[str, object] = {
        "code": exit_code,
        "message": (
            str(structured_error["message"])
            if structured_error is not None
            else combined or "skill command failed"
        ),
    }
    if structured_error is not None:
        error.update({key: value for key, value in structured_error.items() if key != "message"})
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
