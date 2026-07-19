#!/usr/bin/env python3
"""Canonical Python entry point for the legacy Jetstar Node implementation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    legacy = Path(__file__).with_name("cli.mjs")
    try:
        return subprocess.run(["node", str(legacy), *sys.argv[1:]], check=False).returncode
    except FileNotFoundError:
        print("missing configuration: Node.js is required by the declared legacy Jetstar exception", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
