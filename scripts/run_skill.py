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
    payload = result_envelope(
        ok=False,
        source_name=metadata["thecolab.source_owner"],
        source_url=metadata["thecolab.source_url"],
        query={"argv": query_args},
        data=None,
        warnings=[],
        blocked=blocked,
        error={"code": exit_code, "message": combined or "skill command failed"},
    )
    emit_envelope(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
