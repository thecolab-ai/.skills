#!/usr/bin/env python3
"""Canonical Python CLI for {{SKILL_NAME}}."""
from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="{{SKILL_TITLE}}")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="show scaffold source and implementation status")
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    payload = {
        "skill": "{{SKILL_NAME}}",
        "source_url": "{{SOURCE_URL}}",
        "status": "untested",
        "next_action": "replace the scaffold status command with the documented data commands",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{{SKILL_NAME}}: untested scaffold for {{SOURCE_URL}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
