#!/usr/bin/env python3
import io
import json
import subprocess
import sys
from pathlib import Path

import openpyxl

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "lib"))

from treasury_workbooks import (  # noqa: E402
    ComparisonError,
    compare_key_indicators,
    filter_key_indicators,
    parse_key_indicators,
    parse_publications,
    parse_resources,
    primary_forecast_publications,
    resolve_publication,
    search_appropriations,
    select_charts_workbook,
)

STAMP = "2026-07-19T00:00:00Z"
BEFU_PAGE = "https://www.treasury.govt.nz/publications/efu/budget-economic-and-fiscal-update-2026"
CATALOGUE = "https://www.treasury.govt.nz/publications/budgets/forecasts"


def summary_workbook(debt_label: str, debt_values: list[float]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Table 1"
    sheet.append([None, "Table 1.1 Key economic and fiscal indicators"])
    sheet.append([None, "Sources: Stats NZ, the Treasury"])
    sheet.append([])
    sheet.append([None, None, 2025, 2026, 2027])
    sheet.append([None, "Year ending 30 June ", "Actual", "Forecast", "Forecast"])
    sheet.append([None, "OBEGALx ($billions)", -9.306, -13.852, -10.362])
    sheet.append([None, debt_label, *debt_values])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def expenditure_workbook() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Raw Data"
    sheet.append(
        [
            "Department",
            "Vote",
            "App ID",
            "Parent ID",
            "Appropriation Name",
            "Category Name",
            "Group Type",
            "Appropriation or Category Type",
            "Restriction Type",
            "Functional Classification",
            "Amount $000",
            "Year",
            "Amount Type",
            "Periodicity",
            "Current Scope",
            "M Number",
            "Portfolio Name",
        ]
    )
    sheet.append(
        [
            "Ministry of Health",
            "Health",
            123,
            123,
            "Health services",
            "Health services",
            "Single",
            "Departmental Output Expenses",
            None,
            "Health",
            33031368,
            2027,
            "Main Estimates",
            "A",
            "Funding health services.",
            1,
            "Minister of Health",
        ]
    )
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


resources = parse_resources((SKILL / "tests/fixtures/publication.html").read_text(), BEFU_PAGE, STAMP)
assert select_charts_workbook(resources)["url"].endswith("befu26-charts-data.xlsx")
assert all("#" not in resource["url"] for resource in resources)
assert all(resource["url"].rstrip("/") != BEFU_PAGE.rstrip("/") for resource in resources)

catalogue_rows = parse_publications(
    (SKILL / "tests/fixtures/catalog.html").read_text(), CATALOGUE, STAMP
)
primary = primary_forecast_publications(catalogue_rows)
assert [row["publication_kind"] for row in primary] == ["HYEFU", "BEFU"]
assert all(not row["title"].startswith("Skip") for row in primary)
hyefu = resolve_publication(catalogue_rows, "HYEFU 2025")
befu = resolve_publication(catalogue_rows, "BEFU 2026")
assert hyefu and hyefu["slug"] == "half-year-economic-and-fiscal-update-2025"
assert befu and befu["slug"] == "budget-economic-and-fiscal-update-2026"
assert resolve_publication(catalogue_rows, "made up vintage") is None

before_body = summary_workbook("Net core Crown debt ($billions)", [182.171, 196.987, 220.568])
after_body = summary_workbook("Net core Crown debt ($billions)", [182.171, 191.761, 216.481])
before = parse_key_indicators(before_body, hyefu, "https://www.treasury.govt.nz/hyefu.xlsx", STAMP)
after = parse_key_indicators(after_body, befu, "https://www.treasury.govt.nz/befu.xlsx", STAMP)
comparison = compare_key_indicators(before, after)
debt_2026 = next(row for row in comparison if row["measure"] == "Net core Crown debt" and row["period_label"] == "2026")
assert debt_2026["delta"] == -5.226 and debt_2026["unit"] == "NZD billion"
assert debt_2026["from"]["provenance"] == "Table 1!D7"
assert debt_2026["to"]["cell"] == "D7"
assert debt_2026["alignment"].startswith("exact definition")
forecast_values = filter_key_indicators(after, "net core crown debt")
assert forecast_values and forecast_values[0]["period"] == "2025-06-30"
assert forecast_values[1]["forecast_status"] == "forecast"
assert forecast_values[1]["cell"] == "D7"

mismatched = parse_key_indicators(
    summary_workbook("Net core Crown debt (% of GDP)", [41.8, 43.3, 46.0]),
    befu,
    "https://www.treasury.govt.nz/mismatch.xlsx",
    STAMP,
)
try:
    compare_key_indicators(before, mismatched)
except ComparisonError as exc:
    assert "Refusing to align changed definition" in str(exc)
else:
    raise AssertionError("changed fiscal definitions must fail closed")

appropriation_publication = {
    "title": "Budget 2026 Data: Estimates and Appropriations 2026/27",
    "url": "https://www.treasury.govt.nz/publications/data/budget-2026-data-estimates-appropriations-2026-27",
}
for vote_query in ("Health", "Vote Health"):
    matches = search_appropriations(
        expenditure_workbook(),
        vote_query,
        appropriation_publication,
        "https://www.treasury.govt.nz/expenditure.xlsx",
        STAMP,
        vote_only=True,
    )
    assert len(matches) == 1 and matches[0]["vote"] == "Health"
    assert matches[0]["value"] == 33031368
    assert matches[0]["unit"] == "NZD thousand"
    assert matches[0]["period"] == "2027-06-30"
    assert matches[0]["forecast_status"] == "main estimates"
    assert matches[0]["cell"] == "K2" and matches[0]["provenance"] == "Raw Data!K2"
print("[PASS] fixture Treasury resolver, exact forecast alignment, delta and cell provenance")
print("[PASS] invalid vintages and changed definitions fail closed")
print("[PASS] catalogue navigation filtering, structured forecast values and Vote normalisation")

run = subprocess.run(
    [
        sys.executable,
        str(SKILL / "scripts/cli.py"),
        "compare",
        "--from",
        "HYEFU 2025",
        "--to",
        "BEFU 2026",
        "--limit",
        "3",
        "--json",
    ],
    capture_output=True,
    text=True,
    timeout=120,
)
if run.returncode == 0:
    payload = json.loads(run.stdout)
    assert payload["data"] and all(row["from"]["workbook_url"] for row in payload["data"])
    assert all(row["alignment"].startswith("exact definition") for row in payload["data"])
    print("[PASS] live official HYEFU 2025 to BEFU 2026 exact forecast comparison")

    checks = [
        (["latest", "--limit", "3", "--json"], "latest"),
        (["forecast", "net core crown debt", "--limit", "2", "--json"], "forecast"),
        (["vote", "Vote Health", "--limit", "2", "--json"], "vote"),
    ]
    for arguments, label in checks:
        check = subprocess.run(
            [sys.executable, str(SKILL / "scripts/cli.py"), *arguments],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert check.returncode == 0, check.stderr
        check_payload = json.loads(check.stdout)
        assert check_payload["data"], f"live {label} returned no records"
        if label == "latest":
            assert all(not row["title"].startswith("Skip") for row in check_payload["data"])
            assert all(row["publication_kind"] in {"BEFU", "HYEFU", "PREFU"} for row in check_payload["data"])
        else:
            assert all(row["period"] and row["cell"] for row in check_payload["data"])
    print("[PASS] live latest, structured forecast and Vote Health regressions")
elif run.returncode in {4, 5}:
    print(f"[SKIP] Treasury blocked/unavailable: {run.stderr.strip()}")
else:
    print(run.stderr, file=sys.stderr)
    raise SystemExit(1)
