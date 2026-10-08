#!/usr/bin/env python3
"""Deterministic repository and source-parser contract checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
from contract_test import run_contract_test  # noqa: E402
from parser_tests import run  # noqa: E402

if __name__ == '__main__':
    result = run_contract_test(Path(__file__).resolve().parents[1])
    if result == 0:
        run()
    raise SystemExit(result)
