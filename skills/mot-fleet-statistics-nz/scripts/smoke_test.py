#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check(name: str, fn) -> bool:
    try:
        ok = bool(fn())
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def parse_json(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}")
    return json.loads(result.stdout)


def xml_file(rows: list[list[str]]) -> str:
    body = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{chr(ord('A') + col_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def make_xlsx(path: Path) -> None:
    sheets = {
        "8.2a VKT by fuel": [
            ["Table 8.2a", "Annual VKT by main fuel", ""],
            ["Vehicle type", "Fuel", "2023", "2024"],
            ["Light passenger", "Petrol", "25100", "25050"],
            ["Light passenger", "Diesel", "9300", "9100"],
            ["Light passenger", "Pure electric", "1150", "1700"],
        ],
        "8.4 Light fleet fuel": [
            ["Table 8.4", "Light fleet by main fuel", ""],
            ["Vehicle type", "Fuel", "2023", "2024"],
            ["Light passenger", "Petrol", "2620000", "2600000"],
            ["Light passenger", "Pure electric", "86000", "118000"],
        ],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheet_nodes = []
        rel_nodes = []
        for index, name in enumerate(sheets, start=1):
            sheet_nodes.append(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>')
            rel_nodes.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
        zf.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{"".join(sheet_nodes)}</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(rel_nodes)}</Relationships>')
        for index, rows in enumerate(sheets.values(), start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", xml_file(rows))


results: list[bool] = []
results.append(check("contract --help exits 0", lambda: run(["--help"]).returncode == 0))


def with_fixture(fn) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "NZ Vehicle Fleet 2024.xlsx"
        make_xlsx(path)
        return fn(path.as_uri())


def test_workbook() -> bool:
    def inner(uri: str) -> bool:
        data = parse_json(["workbook", "--url", uri, "--sheet", "8.2a VKT by fuel", "--limit", "3", "--json"])
        assert data["status"] == "ok"
        assert data["sheet"] == "8.2a VKT by fuel"
        assert data["row_count"] == 5
        return True

    return with_fixture(inner)


results.append(check("fixture workbook parses a local XLSX source", test_workbook))


def test_tables() -> bool:
    def inner(uri: str) -> bool:
        data = parse_json(["tables", "--url", uri, "--json"])
        assert data["status"] == "ok"
        assert len(data["tables"]) == 2
        assert data["tables"][0]["years"] == [2023, 2024]
        return True

    return with_fixture(inner)


results.append(check("fixture tables lists worksheet previews and years", test_tables))


def test_vkt() -> bool:
    def inner(uri: str) -> bool:
        data = parse_json(["vkt", "--url", uri, "--year", "2024", "--json"])
        assert data["status"] == "ok"
        assert data["kind"] == "vkt"
        assert any(row["dimensions"].get("fuel") == "Pure electric" and row["value"] == "1700" for row in data["records"])
        return True

    return with_fixture(inner)


results.append(check("fixture vkt returns year-specific rows", test_vkt))


def test_fuel_counts() -> bool:
    def inner(uri: str) -> bool:
        data = parse_json(["fuel-counts", "--url", uri, "--year", "2024", "--limit", "1", "--json"])
        assert data["status"] == "ok"
        assert data["kind"] == "fuel_counts"
        assert data["matched_sheets"] == ["8.4 Light fleet fuel"]
        assert data["records"][0]["value"] == "2600000"
        return True

    return with_fixture(inner)


results.append(check("fixture fuel-counts returns year-specific rows", test_fuel_counts))


def test_datasets_live_or_blocked() -> bool:
    result = run(["datasets", "--json"], timeout=30)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["source"]["source_url"].startswith("https://www.transport.govt.nz/")
    assert data["workbook_discovery"]["status"] in {"ok", "blocked"}
    if data["workbook_discovery"]["status"] == "blocked":
        assert data["release_notes"] == []
        assert data["release_notes_status"] == "blocked"
    return True


results.append(check("datasets returns source context or explicit blocked discovery", test_datasets_live_or_blocked))

if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
