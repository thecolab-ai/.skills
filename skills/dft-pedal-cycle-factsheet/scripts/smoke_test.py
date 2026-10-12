#!/usr/bin/env python3
"""Fixture, bounds, and bounded live checks for the pedal-cycle factsheet."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import factsheet  # noqa: E402
from factsheet import FACTSHEET_URL, FactsheetError  # noqa: E402

CLI = Path(__file__).resolve().parent / "cli.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SIBLING_MARKERS = ("pedestrian", "escooter", "e-scooter", "motorcycle", "motorcyclist")


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def sample_content() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
<office:body><office:spreadsheet>
<table:table table:name="Cover_sheet">
<table:table-row>
<table:table-cell office:value-type="string"><text:p>Pedal cycle road safety factsheet, Great Britain, 2025</text:p></table:table-cell>
<table:table-cell table:number-columns-repeated="16383"/>
</table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Some column headings give units. When this is the case the units are presented in round brackets to differentiate them from note markers.</text:p></table:table-cell></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Shorthand is used when there is more than one reason for not having the data, for example: '[x] for no data'.</text:p></table:table-cell></table:table-row>
<table:table-row table:number-rows-repeated="1048561"/>
</table:table>
<table:table table:name="Table_of_contents">
<table:table-row><table:table-cell office:value-type="string"><text:p>Table of contents</text:p></table:table-cell></table:table-row>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>Worksheet title</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Table title</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Date this data was first published</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Next publication date</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Source</text:p></table:table-cell>
</table:table-row>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>Table_1</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Number of reported pedal cycle casualties by severity and traffic (pedal cycle billion vehicle miles), GB: 2004 to 2025</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>30th July 2026</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>July 2027</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Department for Transport, Road Safety Statistics, STATS19</text:p></table:table-cell>
</table:table-row>
</table:table>
<table:table table:name="Table_1">
<table:table-row><table:table-cell office:value-type="string"><text:p>Number of reported pedal cycle casualties by severity and traffic (pedal cycle billion vehicle miles), GB: 2004 to 2025</text:p></table:table-cell></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Shorthand is used in this table, [x] = not available.</text:p></table:table-cell></table:table-row>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>Year</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Killed</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Traffic</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Pedal cyclists (%)</text:p></table:table-cell>
</table:table-row>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>2004</text:p></table:table-cell>
<table:table-cell office:value-type="float" office:value="134"><text:p>134</text:p></table:table-cell>
<table:table-cell office:value-type="float" office:value="2.59"><text:p>3</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>2.3%</text:p></table:table-cell>
</table:table-row>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>2005</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>[x]</text:p></table:table-cell>
<table:table-cell/>
<table:table-cell office:value-type="string"><text:p>[note 1]</text:p></table:table-cell>
</table:table-row>
</table:table>
</office:spreadsheet></office:body></office:document-content>
"""


def ods_bytes(content: str, *, mimetype: str = "application/vnd.oasis.opendocument.spreadsheet") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, mimetype)
        archive.writestr("content.xml", content)
    return buffer.getvalue()


def expect_error(blob: bytes, code: int) -> None:
    try:
        factsheet.parse_ods_bytes(blob)
    except FactsheetError as exc:
        if exc.code != code:
            raise AssertionError(f"expected exit {code}, got {exc.code}: {exc}") from exc
        return
    raise AssertionError(f"malformed workbook was accepted, expected exit {code}")


def check_fixtures() -> None:
    good = run_cli("tables", "--fixture", str(FIXTURES / "pedal-cycle-sample.ods"), "--json")
    if good.returncode != 0 or good.stderr:
        raise AssertionError(good.stderr or good.stdout)
    payload = json.loads(good.stdout)
    publication = payload["results"][0]["publication"]
    if publication != "Pedal cycle road safety factsheet, Great Britain, 2025":
        raise AssertionError(publication)
    values = {(cell["value"], cell["display"]) for cell in payload["results"][0]["numeric_preview"]}
    if ("2.59", "3") not in values or ("134", "134") not in values:
        raise AssertionError(values)
    print("[PASS] fixture title cell and unrounded office value")

    bad = run_cli("tables", "--fixture", str(FIXTURES / "not-a-spreadsheet.bin"), "--json")
    if bad.returncode != 6 or json.loads(bad.stdout)["error"]["type"] != "schema_failure":
        raise AssertionError(bad.stdout or bad.stderr)
    print("[PASS] fixture malformed archive exits schema_failure")

    empty = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">
<office:body><office:spreadsheet></office:spreadsheet></office:body></office:document-content>"""
    expect_error(ods_bytes(empty), 6)
    expect_error(ods_bytes(sample_content(), mimetype="text/plain"), 6)
    expect_error(ods_bytes("<!DOCTYPE foo [<!ENTITY x 'y'>]><a/>"), 6)
    repeated = sample_content().replace(
        'office:value="134"',
        'office:value="134" table:number-columns-repeated="100"',
        1,
    )
    expect_error(ods_bytes(repeated), 7)
    huge = zipfile.ZipInfo("content.xml")
    huge.file_size = 50_000_000
    huge.compress_size = 20
    try:
        factsheet.assess_members([huge])
    except FactsheetError as exc:
        if exc.code != 7:
            raise
    else:
        raise AssertionError("over-cap member was accepted")
    slipped = zipfile.ZipInfo("../content.xml")
    slipped.file_size = 10
    slipped.compress_size = 10
    try:
        factsheet.assess_members([slipped])
    except FactsheetError as exc:
        if exc.code != 7:
            raise
    else:
        raise AssertionError("path traversal member was accepted")
    print("[PASS] fixture rejects empty, malformed, repeated, and unsafe ODS input")

    blocked = factsheet.error_for_http_status(429, "30")
    unavailable = factsheet.error_for_http_status(503)
    if blocked.code != 4 or blocked.retry_after != "30" or not str(blocked).startswith("network error:"):
        raise AssertionError(blocked)
    if unavailable.code != 5 or not str(unavailable).startswith("network error:"):
        raise AssertionError(unavailable)
    for unsafe in (
        "https://evil.example/pedal-cycle.ods",
        "http://www.gov.uk/government/statistics/pedal-cycle",
        "https://www.gov.uk/government/statistics/pedal-cycle?download=1",
        "https://assets.publishing.service.gov.uk:8443/media/pedal-cycle.ods",
    ):
        try:
            factsheet.official_url(unsafe)
        except FactsheetError as exc:
            if exc.code != 7:
                raise
        else:
            raise AssertionError(f"accepted unsafe URL {unsafe}")
    print("[PASS] fixture outage status and official URL bounds")

    parent_html = """
    <html><body>
    <a href="https://assets.publishing.service.gov.uk/media/sibling/Pedestrian_factsheet_tables.ods">Pedestrian factsheet: data tables</a>
    <a href="https://assets.publishing.service.gov.uk/media/sibling/Escooter_factsheet_tables.ods">E-scooter factsheet: data tables</a>
    <a href="https://assets.publishing.service.gov.uk/media/sibling/Motorcycle_factsheet_tables.ods">Motorcycle factsheet: data tables</a>
    <a href="https://assets.publishing.service.gov.uk/media/current/Pedal_cycle_factsheet_tables.ods">Pedal cycle factsheet: data tables</a>
    </body></html>
    """
    selected = factsheet.pedal_ods_links(parent_html, "https://www.gov.uk/government/statistics/release")
    if selected != [
        "https://assets.publishing.service.gov.uk/media/current/Pedal_cycle_factsheet_tables.ods"
    ]:
        raise AssertionError(selected)
    page = f"""
    <html><body>
    <h1>Reported road casualties Great Britain: pedal cycle factsheet, 2025</h1>
    <p>This publication is licensed under the terms of the Open Government Licence v3.0 except where otherwise stated.</p>
    <a href="{factsheet.release_parent_url(FACTSHEET_URL)}">Vulnerable road user factsheets</a>
    <a href="https://www.gov.uk/government/collections/road-traffic-statistics">Road traffic statistics</a>
    </body></html>
    """
    factsheet.assert_factsheet_page(page)
    if factsheet.pedal_ods_links(page, FACTSHEET_URL):
        raise AssertionError("factsheet narrative linked an ODS")
    parent = factsheet.linked_parent_release(page, FACTSHEET_URL)
    if parent != factsheet.release_parent_url(FACTSHEET_URL):
        raise AssertionError(parent)
    try:
        factsheet.assert_factsheet_page("<html><h1>pedal cycle factsheet</h1></html>")
    except FactsheetError as exc:
        if exc.code != 6:
            raise
    else:
        raise AssertionError("missing licence statement was accepted")
    print("[PASS] fixture keeps sibling factsheets unselected and requires the publication licence")


def check_live() -> int:
    completed = subprocess.run(
        [sys.executable, str(CLI), "tables", "--sheet", "Table_1", "--limit", "8", "--json"],
        capture_output=True,
        text=True,
        timeout=55,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    network = completed.returncode in {4, 5} or "network error:" in output.casefold()
    if network:
        print(f"[SKIP] live network error: pedal-cycle factsheet request failed ({completed.returncode})")
        return 0
    if completed.returncode != 0:
        print("[FAIL] live pedal-cycle factsheet request")
        print(output)
        return 1
    payload = json.loads(completed.stdout)
    result = payload["results"][0]
    title = "Pedal cycle road safety factsheet, Great Britain, 2025"
    preview = result["numeric_preview"]
    if title not in result["publication"] or not preview or result["numeric_cell_count"] < 100:
        print("[FAIL] live pedal-cycle title and numeric cell")
        print(output[:1000])
        return 1
    print("[PASS] live pedal-cycle title and numeric cell")
    table = next(sheet for sheet in result["sheets"] if sheet["name"] == "Table_1")
    percent_units = [
        header["unit"]
        for sheet in result["sheets"]
        for header in sheet["headers"]
        if header.get("unit") == "%"
    ]
    names = set(result["worksheets"])
    requests = result["requests"]
    ods_urls = [item["url"] for item in requests if item["kind"] == "ods"]
    if (
        "pedal cycle billion vehicle miles" not in table["title_units"]
        or not percent_units
        or not {"Table_1", "Table_2", "Table_3", "Table_4", "Table_5"} <= names
        or len(ods_urls) != 1
        or not ods_urls[0].endswith(".ods")
        or "pedal" not in ods_urls[0].casefold()
        or "cycle" not in ods_urls[0].casefold()
        or any(marker in item["url"].casefold() for item in requests for marker in SIBLING_MARKERS)
        or any(sheet["max_row"] >= 500 or sheet["max_column"] >= 40 for sheet in result["sheets"])
        or any("," in str(cell["value"]) for cell in preview if "," in str(cell["display"]))
        or payload["meta"]["retrieved_at"] == payload["meta"].get("latest_data")
    ):
        print("[FAIL] live units, worksheet bounds, and official ODS link")
        print(output[:1000])
        return 1
    print("[PASS] live units, worksheet bounds, and official ODS link")
    return 0


def main() -> int:
    try:
        check_fixtures()
    except (AssertionError, OSError, json.JSONDecodeError, FactsheetError) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    return check_live()


if __name__ == "__main__":
    raise SystemExit(main())
