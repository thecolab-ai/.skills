#!/usr/bin/env python3
"""Canonical Python CLI for {{SKILL_NAME}}."""
from __future__ import annotations

import argparse
import json
import sys

from provenance import error_envelope, provenance, result_envelope

SOURCE_URL = {{PY_SOURCE_URL}}
PUBLISHER = {{PY_SOURCE_OWNER}}
LICENCE = {{PY_SOURCE_LICENCE}}


class InputError(ValueError):
    """An argparse failure that can be emitted as a JSON error envelope."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def source_meta() -> dict[str, str]:
    # Pass latest_data only when stated by the source; retain cached retrieval times.
    return provenance(SOURCE_URL, PUBLISHER, licence=LICENCE)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = ArgumentParser(description="{{SKILL_TITLE}}")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="show scaffold source and implementation status")
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    try:
        args = parser.parse_args(argv)
    except InputError as exc:
        if "--json" in argv:
            print(json.dumps(error_envelope(2, str(exc), source_meta()), indent=2, ensure_ascii=False))
        else:
            parser.print_usage(sys.stderr)
            print(f"{{SKILL_NAME}}: {exc}", file=sys.stderr)
        return 2
    record = {
        "skill": "{{SKILL_NAME}}",
        "status": "untested",
        "next_action": "replace the scaffold status command with the documented data commands",
    }
    if args.json:
        print(json.dumps(result_envelope([record], source_meta()), indent=2, ensure_ascii=False))
    else:
        print(f"{{SKILL_NAME}}: untested scaffold for {SOURCE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
