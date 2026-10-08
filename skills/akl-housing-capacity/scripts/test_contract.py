#!/usr/bin/env python3
"""Deterministic CLI, provenance and real-format synthetic parser checks."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
from contract_test import audit_skill  # noqa: E402
import cli  # noqa: E402
from housing import council_records, capacity_records, hud_records, matches, select_periods, typology_records  # noqa: E402
from workbook import NS, SchemaError, Workbook  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def changed_cells(body, sheet_path, changes):
    """Edit synthetic worksheet cells without changing the rest of the archive."""
    edited = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as archive, zipfile.ZipFile(edited, "w") as output:
        for info in archive.infolist():
            data = archive.read(info)
            if info.filename == sheet_path:
                root = ET.fromstring(data)
                sheet_data = root.find(f"{{{NS}}}sheetData")
                for row in list(sheet_data):
                    for cell in list(row):
                        reference = cell.attrib["r"]
                        if reference not in changes:
                            continue
                        value = changes[reference]
                        if value is None:
                            row.remove(cell)
                            continue
                        cell.clear()
                        cell.set("r", reference)
                        if isinstance(value, str):
                            cell.set("t", "inlineStr")
                            inline = ET.SubElement(cell, f"{{{NS}}}is")
                            ET.SubElement(inline, f"{{{NS}}}t").text = value
                        else:
                            ET.SubElement(cell, f"{{{NS}}}v").text = str(value)
                    if not len(row):
                        sheet_data.remove(row)
                data = ET.tostring(root)
            output.writestr(info, data)
    return edited.getvalue()


def fixture_checks(report=False):
    count = 0

    def check(condition, label):
        nonlocal count
        assert condition, label
        count += 1
        if report:
            print(f"[PASS] fixture {label}")

    council = council_records((FIXTURES / "housing.xlsx").read_bytes())
    latest = select_periods(council)
    check(len(latest) == 5, "Council latest observations retain distinct sheets and boards")
    regional = next(r for r in latest if r["sheet"] == "Dwellings Consented")
    check(regional["period"] == "2026-07" and regional["measures"]["all_dwellings"] == 13,
          "Council numeric date and total")
    check(regional["measures"]["houses"] == 0 and regional["measures"]["apartments"] is None,
          "zero and unpublished dash remain distinct")
    check(next(r for r in latest if r["unit"] == "parcels")["period"] == "2026-08",
          "parcels keep their own latest month and unit")
    selected = [r for r in select_periods(council, "2026-06") if matches(r["area"], "Hénderson-Massey")]
    check(len(selected) == 1 and selected[0]["measures"]["all_dwellings"] == 5,
          "area matching and historical observation filter")
    check(select_periods(council, "1900-01") == [], "absent observation month is a valid empty result")
    capacity = capacity_records((FIXTURES / "capacity.xlsx").read_bytes())
    check(capacity[0]["plan_enabled_capacity"] == 321 and capacity[0]["feasible_capacity"] == 123,
          "paired capacity totals use matching local-board columns")
    check(capacity[1]["area_type"] == "region" and capacity[1]["feasible_capacity"] == 234,
          "regional capacity aggregate is identified")
    capacity_body = (FIXTURES / "capacity.xlsx").read_bytes()
    titles = dict(Workbook(capacity_body).rows("Plan-enabled Feasible x LBA"))
    for changes, label in (
        ({"D4": titles[5]["Y"], "Y5": titles[4]["D"]}, "reordered capacity blocks"),
        ({"D4": "Changed title"}, "changed plan-enabled block title"),
        ({"Y5": "Changed title"}, "changed feasible block title"),
        ({"D4": None}, "missing plan-enabled block title row"),
        ({"Y5": None}, "missing feasible block title row"),
    ):
        try:
            capacity_records(changed_cells(capacity_body, "xl/worksheets/sheet1.xml", changes))
        except SchemaError:
            check(True, label + " fail with a schema error")
        else:
            raise AssertionError(label + " accepted")
    typologies = typology_records((FIXTURES / "feasibility.xlsx").read_bytes())
    check([r["feasible_capacity"] for r in typologies] == [9, 12]
          and [r["selection"] for r in typologies] == ["Max_Profit", "MinDUPrice"],
          "alternative feasible selections stay separate")
    check(typologies[0]["price_unit"] == "NZD" and typologies[0]["median_dwelling_price"] == 150000,
          "model prices retain their units")
    hud, latest_month = hud_records((FIXTURES / "hud.xlsx").read_bytes())
    check(latest_month == "2026-08" and len(hud) == 2 and hud[0]["value"] == 17,
          "HUD defaults to Auckland latest Delivery observations")
    check(hud[1]["value"] == -3 and hud[1]["dimensions"][1]["value"] == "Removed or adjusted stock (SLED)",
          "HUD preserves negative stock adjustment and category meaning")
    historic, historic_month = hud_records((FIXTURES / "hud.xlsx").read_bytes(), month="2026-07")
    check(len(historic) == 1 and historic[0]["value"] == 6 and historic_month == "2026-07",
          "HUD observation month filter also selects the metadata period")
    newer_excluded = changed_cells((FIXTURES / "hud.xlsx").read_bytes(),
                                  "xl/worksheets/sheet2.xml", {"N5": 46266, "N6": 46266})
    hud, latest_month = hud_records(newer_excluded)
    check(len(hud) == 2 and latest_month == "2026-08",
          "HUD metadata excludes newer Stock and other-area rows")
    northland, latest_month = hud_records(newer_excluded, area="Northland")
    check(len(northland) == 1 and latest_month == "2026-09",
          "HUD metadata follows the selected area's Delivery rows")
    for filters in ({"area": "Unknown"}, {"month": "1900-01"}):
        hud, latest_month = hud_records(newer_excluded, **filters)
        check(hud == [] and latest_month == "", "HUD unmatched filters have no latest data period")
    inventory = cli.business_inventory((FIXTURES / "business.zip").read_bytes())
    check(len(inventory) == 2 and inventory[0]["files"] == 2
          and inventory[0]["record_type"] == "archive_inventory", "ZIP inventory counts files, not GIS features")
    page = (FIXTURES / "landing.html").read_text()
    check(cli.download_link(page, cli.HOUSING_PAGE, "housing-update-datasheet").endswith("fixture.xlsx"),
          "current XLSX discovery resolves relative public link")
    for payload in (b"<html>upstream response</html>", b"PK invalid workbook"):
        try:
            Workbook(payload)
        except SchemaError:
            check(True, "non-workbook response is a schema error")
        else:
            raise AssertionError("Invalid workbook accepted")
    try:
        cli.download_link('<a href="https://untrusted.invalid/housing-update-datasheet.xlsx">x</a>',
                          cli.HOUSING_PAGE, "housing-update-datasheet")
    except SchemaError:
        check(True, "discovered outbound host is validated")
    else:
        raise AssertionError("Undeclared host accepted")
    # Mutate the synthetic archive to exercise formula/error/schema failures.
    body = (FIXTURES / "housing.xlsx").read_bytes()
    for before, after in ((b">All dwellings consented<", b">Changed schema<"),):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            edited = io.BytesIO()
            with zipfile.ZipFile(edited, "w") as output:
                for name in archive.namelist():
                    output.writestr(name, archive.read(name).replace(before, after))
        try:
            council_records(edited.getvalue())
        except SchemaError:
            check(True, "changed Council headers fail instead of returning empty data")
        else:
            raise AssertionError("Changed schema accepted")
    for cached in (True, False):
        edited = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(body)) as archive, zipfile.ZipFile(edited, "w") as output:
            for name in archive.namelist():
                data = archive.read(name)
                if name == "xl/worksheets/sheet2.xml":
                    root = ET.fromstring(data)
                    cell = next(c for c in root.iter(f"{{{NS}}}c") if c.attrib["r"] == "F3")
                    ET.SubElement(cell, f"{{{NS}}}f").text = "SUM(B3:E3)"
                    if not cached:
                        cell.remove(cell.find(f"{{{NS}}}v"))
                    data = ET.tostring(root)
                output.writestr(name, data)
        try:
            observations = council_records(edited.getvalue())
        except SchemaError:
            check(not cached, "formula without cached result fails clearly")
        else:
            total = next(r for r in select_periods(observations) if r["sheet"] == "Dwellings Consented")
            check(cached and total["measures"]["all_dwellings"] == 13,
                  "cached formula value is read without evaluating the formula")
    try:
        Workbook((FIXTURES / "hud.xlsx").read_bytes()).month("2026-99-01")
    except SchemaError:
        check(True, "invalid source ISO reporting date is a schema error")
    else:
        raise AssertionError("Invalid source date accepted")
    return count


def provenance_checks():
    command = Path(__file__).with_name("cli.py")
    cases = [(["sources", "--json"], 0), (["--thecolab-invalid-option", "--json"], 2),
             (["housing-update", "--month", "2026-13", "--json"], 2),
             (["housing-update", "--area", "---", "--json"], 2),
             (["capacity", "--zone", "Mixed Housing Urban", "--json"], 7),
             (["capacity", "--dataset", "business", "--area", "Whau", "--json"], 7),
             (["demolitions", "--area", "Auckland", "--json"], 7)]
    for args, code in cases:
        result = subprocess.run([sys.executable, str(command), *args], capture_output=True, text=True, timeout=10)
        assert result.returncode == code and not result.stderr, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        meta = payload["meta"]
        assert meta["source_url"] and meta["publisher"] and meta["retrieved_at"].endswith("Z")
        assert datetime.fromisoformat(meta["retrieved_at"].replace("Z", "+00:00")).utcoffset() == timedelta(0)
        assert isinstance(payload["results"], list)
        if code:
            assert payload["error"]["code"] == code and payload["results"] == []
        else:
            assert all(r["source_url"] and r["publisher"] and r["retrieved_at"] for r in payload["results"])
    # Verify actual data-command JSON and rate limiting without network access.
    capture = io.StringIO()
    with patch.object(cli.nzfetch, "fetch_text", return_value=(FIXTURES / "landing.html").read_text()), \
         patch.object(cli, "fetch_workbook", return_value=(FIXTURES / "housing.xlsx").read_bytes()), \
         contextlib.redirect_stdout(capture):
        assert cli.main(["housing-update", "--area", "Henderson-Massey", "--json"]) == 0
    payload = json.loads(capture.getvalue())
    assert len(payload["results"]) == 1 and payload["meta"]["latest_data"] == "2026-08"
    assert payload["results"][0]["period"] == "2026-07"
    for month in ("2026-07", "1900-01"):
        capture = io.StringIO()
        with patch.object(cli.nzfetch, "fetch_text", return_value='<a href="/assets/housing-dashboard-data-download.xlsx">x</a>'), \
             patch.object(cli, "fetch_workbook", return_value=(FIXTURES / "hud.xlsx").read_bytes()), \
             contextlib.redirect_stdout(capture):
            assert cli.main(["housing-update", "--source", "hud", "--month", month, "--json"]) == 0
        payload = json.loads(capture.getvalue())
        if month == "2026-07":
            assert payload["meta"]["latest_data"] == month
            assert len(payload["results"]) == 1 and payload["results"][0]["period"] == month
        else:
            assert "latest_data" not in payload["meta"] and payload["results"] == []
    capture = io.StringIO()
    reordered = changed_cells((FIXTURES / "capacity.xlsx").read_bytes(),
                              "xl/worksheets/sheet1.xml", {"D4": "PLAN-ENABLED AND FEASIBLE CAPACITY BY VALUE BAND, ALL DWELLING TYPES by LBA"})
    with patch.object(cli, "fetch_workbook", return_value=reordered), contextlib.redirect_stdout(capture):
        assert cli.main(["capacity", "--json"]) == 6
    payload = json.loads(capture.getvalue())
    assert payload["error"]["type"] == "schema_failure" and payload["results"] == []
    capture = io.StringIO()
    failure = cli.nzfetch.RateLimited("network error: HTTP 429", retry_after="60")
    with patch.object(cli.nzfetch, "fetch_text", side_effect=failure), contextlib.redirect_stdout(capture):
        assert cli.main(["housing-update", "--json"]) == 4
    payload = json.loads(capture.getvalue())
    assert payload["error"]["retry_after"] == "60" and payload["error"]["type"] == "blocked"


def main():
    result = audit_skill(Path(__file__).resolve().parents[1])
    if result["ok"]:
        result["fixture_assertions"] += fixture_checks()
        provenance_checks()
        result["checks"].extend(["synthetic_xlsx_parsers", "provenance", "typed_json_errors", "retry_after"])
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
