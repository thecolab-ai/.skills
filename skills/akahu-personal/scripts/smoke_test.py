#!/usr/bin/env python3
"""Offline safety checks for the authenticated Akahu connector."""
import importlib.util
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
spec = importlib.util.spec_from_file_location("akahu_personal_cli", CLI)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)

sample = {
    "formatted_account": "12-3456-1234567-00",
    "nested": [{"other_account": "98-7654-7654321-01"}],
}
redacted = cli.redact_obj(sample)
assert redacted["formatted_account"] == "xx-xxxx-xxxxxxx-00"
assert redacted["nested"][0]["other_account"] == "xx-xxxx-xxxxxxx-01"
assert cli.parse_params(["start=2026-01-01", "type=DEBIT"]) == [
    ("start", "2026-01-01"),
    ("type", "DEBIT"),
]
print("[PASS] fixture personal-data redaction and query parsing")
print("[SKIP] live Akahu check requires operator-supplied personal credentials")
