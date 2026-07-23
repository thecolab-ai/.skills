#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402

if __name__ == "__main__":
    # The generic contract runner checks every documented command's --help.
    # Synthetic variables expose the gated account command surface without login.
    os.environ["NEWWORLD_USERNAME"] = "contract-test@example.invalid"
    os.environ["NEWWORLD_PASSWORD"] = "fixture"
    raise SystemExit(run_contract_test(Path(__file__).resolve().parents[1]))
