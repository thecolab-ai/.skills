#!/usr/bin/env python3
"""Fixture assertions plus a bounded live Hinekōrako query."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))

from hinekorako_register import (  # noqa: E402
    document_result,
    exact_supply_match,
    parse_grid_response,
    parse_supply_detail,
    supplier_relationships,
)

rows = parse_grid_response((SKILL / "tests" / "fixtures" / "grid.json").read_text(encoding="utf-8"))
assert rows[0]["id"] == "AKA001" and rows[0]["supply_type"] == "Networked supply"
for malformed in (
    '{"Records": null}',
    '{"Records": {}}',
    '{"Records": [null]}',
    '{"Records": [{"Attributes": null}]}',
    '{"Records": [{"Attributes": {}}]}',
    '{"Records": [{"Attributes": [null]}]}',
    '{"Records": [{"Attributes": [{}]}]}',
):
    try:
        parse_grid_response(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError("non-list Hinekōrako Records must fail closed")

cli_path = SKILL / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("hinekorako_cli", cli_path)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
stderr = io.StringIO()
with mock.patch.object(cli, "fetch_supplies", side_effect=ValueError("Hinekōrako grid response Records field is not a list")):
    with mock.patch.object(sys, "argv", [str(cli_path), "documents", "AKA001", "--json"]):
        with contextlib.redirect_stderr(stderr):
            assert cli.main() == 6
assert "source_schema_failure" in stderr.getvalue() and "Traceback" not in stderr.getvalue()
detail = parse_supply_detail(
    (SKILL / "tests" / "fixtures" / "supply-detail.html").read_text(encoding="utf-8"),
    rows[0]["source_url"],
    "2026-07-19T00:00:00Z",
)
assert detail["registration_status"] == "Registered" and detail["region"] == "Canterbury"
assert detail["population"] == "820" and detail["exemptions_granted"] is False
assert detail["documents"][0]["url"].endswith("aka001-assurance.pdf")
assert "current potability" in detail["what_this_does_not_prove"]
relationships = supplier_relationships(detail)
assert {row["relationship"] for row in relationships} == {"registered_supplier", "supply_operator"}
assert exact_supply_match(rows, "AKA001") == rows[0]
assert exact_supply_match(rows, "akaroa") == rows[0]
assert exact_supply_match(rows, "Aka") is None
documents = document_result(detail)
assert set(documents) == {
    "supply_id", "supply_name", "documents", "information_withheld",
    "what_this_does_not_prove", "source_url", "retrieved_at",
}
assert documents["supply_id"] == "AKA001" and documents["documents"][0]["title"] == "Public assurance document"
assert "supply" not in documents and "registration_status" not in documents
print("[PASS] fixture grid/detail fields, documents and safety caveats")
print("[PASS] exact ID/name document resolution rejects fuzzy-only matches and preserves document shape")
print("[PASS] non-list grid Records fail closed through CLI exit 6 with a clean structured error")

completed = subprocess.run(
    [sys.executable, str(SKILL / "scripts" / "cli.py"), "supply", "AKA001", "--limit", "2", "--json"],
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)
if completed.returncode == 0:
    payload = json.loads(completed.stdout)
    assert payload["data"] and payload["data"][0]["supply_id"] == "AKA001"
    assert payload["data"][0]["source_url"].startswith("https://hinekorako.taumataarowai.govt.nz/")
    print("[PASS] live official Hinekōrako supply and detail")
    document_check = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "cli.py"), "documents", "AKA001", "--limit", "2", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert document_check.returncode == 0, document_check.stderr
    document_payload = json.loads(document_check.stdout)
    assert document_payload["data"] and document_payload["data"][0]["supply_id"] == "AKA001"
    assert set(document_payload["data"][0]) == {
        "supply_id", "supply_name", "documents", "information_withheld",
        "what_this_does_not_prove", "source_url", "retrieved_at",
    }
    print("[PASS] live documents command has exact document-only result shape")
elif completed.returncode in {4, 5}:
    print(f"[SKIP] Hinekōrako source unavailable: {completed.stderr.strip()}")
else:
    print(completed.stderr, file=sys.stderr)
    raise SystemExit(1)
