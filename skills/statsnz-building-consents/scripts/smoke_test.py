#!/usr/bin/env python3
"""Deterministic release/workbook fixtures plus a bounded live Stats NZ probe."""

import io
import json
import subprocess
import sys
import importlib.util
from pathlib import Path

import openpyxl

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))

from building_consents import graph_records, parse_annual_workbook, parse_release  # noqa: E402

stamp = "2026-07-19T00:00:00Z"
url = "https://www.stats.govt.nz/information-releases/building-consents-issued-test/"
release = parse_release((SKILL / "tests/fixtures/release.html").read_text(), url, stamp)
regions = graph_records(release, "by region")
assert release["publication_date"] == "2026-07-02 10:45:00"
assert release["documents"][0]["url"].endswith("building-consents-issued-test.xlsx")
assert [row["value"] for row in regions if row["category"] == "Auckland"] == [13864, 16862]
for malformed in ('<div id="pageViewData" data-value="[]"></div>', '<div id="pageViewData" data-value="{&quot;DateTaxonomyTerm&quot;: []}"></div>'):
    try:
        parse_release(malformed, url, stamp)
        raise AssertionError("non-object release metadata must fail closed")
    except ValueError:
        pass

workbook = openpyxl.Workbook()
sheet = workbook.active
sheet.title = "Table 1"
for row in [
    ["Table 1", None, None, None, None, None],
    [None] * 6,
    ["Building consents issued", None, None, None, None, None],
    [None] * 6,
    [None, None, None, "Residential buildings", None, None],
    [None, None, None, "New dwellings", None, None],
    [None, None, None, "All dwellings", None, "Floor area"],
    [None] * 6,
    [None] * 6,
    ["Series ref: BLDM.SFTZ", None, None, "Number", None, "m2(000)"],
    [None, None, None, "1100A1A", None, "1100A3A"],
    [None] * 6,
    ["Year ended May", None, None, None, None, None],
    [2025, None, None, 37500, None, 5900],
    [2026, None, None, 39737, None, 6200],
    ["Month", None, None, None, None, None],
]:
    sheet.append(row)
buffer = io.BytesIO()
workbook.save(buffer)
annual = parse_annual_workbook(buffer.getvalue(), "https://www.stats.govt.nz/test.xlsx", stamp)
assert len(annual) == 4
assert annual[-1]["measure"] == "floor_area" and annual[-1]["provenance"] == "Table 1!F15"
print("[PASS] fixture Stats NZ release JSON, regional graph CSV and annual workbook provenance")
spec=importlib.util.spec_from_file_location("building_cli",SKILL/"scripts/cli.py");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.parse_date("2026-05",end=True).isoformat()=="2026-06-01"
assert module.parse_date("2026-05-31",end=True).isoformat()=="2026-06-01"
invalid=subprocess.run([sys.executable,str(SKILL/"scripts/cli.py"),"timeseries","--from","2026-06","--to","2026-05","--json"],capture_output=True,text=True);assert invalid.returncode==2 and "--from must not be after --to" in invalid.stderr

run = subprocess.run(
    [sys.executable, str(SKILL / "scripts/cli.py"), "region", "Auckland", "--limit", "2", "--json"],
    capture_output=True,
    text=True,
    timeout=75,
    check=False,
)
if run.returncode == 0:
    payload = json.loads(run.stdout)
    assert payload["data"] and all(row["category"] == "Auckland" for row in payload["data"])
    assert all(row["source_url"] and row["retrieved_at"] for row in payload["data"])
    print("[PASS] live official Stats NZ regional building-consent series")
elif run.returncode in {4, 5}:
    print(f"[SKIP] Stats NZ blocked/unavailable: {run.stderr.strip()}")
else:
    print(run.stderr, file=sys.stderr)
    raise SystemExit(1)
