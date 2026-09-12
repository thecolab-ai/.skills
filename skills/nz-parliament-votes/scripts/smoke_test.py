#!/usr/bin/env python3
"""Deterministic fixture checks and a bounded live Journal API probe."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from parliament_votes import parse_journal  # noqa: E402

fixture = json.loads((SKILL / "tests/fixtures/journal.json").read_text(encoding="utf-8"))
parsed = parse_journal(fixture, "https://journals.parliament.nz/api/data/Journal/" + fixture["Id"])
assert len(parsed["votes"]) == 2
assert parsed["votes"][0]["totals"] == {"ayes": 4, "noes": 1, "abstentions": 1}
assert any(row["entity_kind"] == "unknown" and row["source_label"] == "Example-Surname" for row in parsed["votes"][0]["participants"])
assert all(row["attribution_basis"] in {"explicit_party_count", "unresolved_singleton_label"} for vote in parsed["votes"] for row in vote["participants"])
print("[PASS] fixture conservative Journal division parsing and tally reconciliation")

completed = subprocess.run(
    [sys.executable, str(SKILL / "scripts/cli.py"), "search", "--limit", "1", "--json"],
    capture_output=True, text=True, timeout=20, check=False,
)
if completed.returncode == 0:
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == "1" and payload["source"]["url"].startswith("https://journals.parliament.nz/")
    assert payload["data"]["page_size"] <= 1
    assert all(row["detail_url"].startswith("https://journals.parliament.nz/api/data/Journal/") for row in payload["data"]["results"])
    print("[PASS] live official weekly Journal search")
elif completed.returncode in {4, 5}:
    detail = completed.stdout.strip() or completed.stderr.strip()
    print(f"[SKIP] Parliament Journals source unavailable: {detail}")
else:
    print(completed.stdout or completed.stderr, file=sys.stderr)
    raise SystemExit(1)
