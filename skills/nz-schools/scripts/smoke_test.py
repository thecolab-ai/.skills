#!/usr/bin/env python3
"""Fixture assertions plus a bounded live Schools Directory lookup."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))

from schools_directory import nearest, normalize, opened_since  # noqa: E402

raw = json.loads((SKILL / "tests" / "fixtures" / "schools.json").read_text(encoding="utf-8"))
rows = [normalize(row, source_url="https://catalogue.data.govt.nz/test.csv", retrieved_at="2026-07-19T00:00:00Z", last_modified="2026-07-18") for row in raw]
assert rows[0]["school_id"] == "7" and rows[0]["total_roll"] == 266
assert rows[0]["town_city"] == "Okaihau" and rows[0]["address_text"] == "58 Settlers Way, Okaihau"
assert rows[0]["year_levels"] == {"lowest": 7, "highest": 15}
assert rows[0]["year_levels_provenance"]["method"] == "school_type_literal_range"
assert rows[2]["year_levels"] == {"lowest": 1, "highest": 8}
assert rows[2]["year_levels_provenance"] == {"method": "school_type_mapping", "source_field": "Org_Type", "source_value": "Full Primary"}
assert nearest(rows, -35.32, 173.76, 1)[0]["school_id"] == "7"
assert opened_since(rows, date(2026, 1, 1), 10)[0]["change_type"].startswith("opened_or_proposed")
try:
    normalize("bad", source_url="https://catalogue.data.govt.nz/test.csv", retrieved_at="2026-07-19T00:00:00Z", last_modified=None)
    raise AssertionError("non-object Schools Directory record was accepted")
except ValueError as exc:
    assert "must be an object" in str(exc)
print("[PASS] fixture school fields, year-level provenance, distance ordering and opening-date changes")

for invalid in (
    ("near", "--lat", "91", "--lon", "174"),
    ("near", "--lat", "-36", "--lon", "181"),
    ("changes", "--since", "not-a-date"),
):
    completed = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "cli.py"), *invalid, "--json"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert completed.returncode == 2
print("[PASS] school coordinates and dates fail before source retrieval")

spec = importlib.util.spec_from_file_location("nz_schools_cli", SKILL / "scripts" / "cli.py")
cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
responses = iter(({"result": {"url": "https://catalogue.data.govt.nz/test.csv", "last_modified": "2026-07-18"}}, {"result": {"records": ["bad"]}}))
cli.nzfetch.fetch_json = lambda *args, **kwargs: next(responses)
old_argv = sys.argv
try:
    sys.argv = [str(SKILL / "scripts" / "cli.py"), "search", "school", "--json"]
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        assert cli.main() == 6
finally:
    sys.argv = old_argv
assert "source_schema_failure" in errors.getvalue() and "Traceback" not in errors.getvalue()
print("[PASS] malformed source records fail closed with a clean structured error")

completed = subprocess.run(
    [sys.executable, str(SKILL / "scripts" / "cli.py"), "school", "7", "--limit", "1", "--json"],
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)
if completed.returncode == 0:
    payload = json.loads(completed.stdout)
    assert payload["data"][0]["school_id"] == "7"
    assert payload["data"][0]["latitude"] is not None and payload["source"]["freshness"].startswith("nightly")
    print("[PASS] live official nightly Schools Directory API")
elif completed.returncode in {4, 5}:
    print(f"[SKIP] Schools Directory unavailable: {completed.stderr.strip()}")
else:
    print(completed.stderr, file=sys.stderr)
    raise SystemExit(1)
