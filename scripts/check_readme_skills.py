#!/usr/bin/env python3
"""Compatibility entry point for generated catalogue drift checking."""
from __future__ import annotations

import sys

import generate_catalogue


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--check"]
    raise SystemExit(generate_catalogue.main())
