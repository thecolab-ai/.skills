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


def check(name: str, fn) -> bool | str:
    try:
        outcome = fn()
        if outcome == "skip":
            print(f"[SKIP] {name}: upstream unavailable or blocked")
            return "skip"
        ok = bool(outcome)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def parse_json(args: list[str]) -> dict:
    result = run(args)
    if result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout: {result.stdout[:300]}\nstderr: {result.stderr[:300]}")
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


def make_xlsx(path: Path, absolute_target: bool = False) -> None:
    target = "/xl/worksheets/sheet1.xml" if absolute_target else "worksheets/sheet1.xml"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{target}"/></Relationships>')
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            xml_file(
                [
                    ["Sector", "Region", "2024", "2025"],
                    ["Primary", "Auckland", "1500", "1990"],
                    ["Secondary", "Canterbury", "875", "1105"],
                ]
            ),
        )


results: list[bool | str] = []

results.append(check("contract --help exits 0", lambda: run(["--help"]).returncode == 0))


def test_list() -> bool:
    data = parse_json(["list", "--json"])
    assert data["status"] == "ok"
    names = {item["name"] for item in data["datasets"]}
    assert {"ite", "teacher-movement", "teacher-turnover", "teacher-numbers", "tds"} <= names
    return True


results.append(check("contract list returns supported dataset families", test_list))


def test_ite_enrolments_live_or_blocked() -> bool | str:
    try:
        result = run(["ite-enrolments", "--from", "2024", "--to", "2025", "--json"], timeout=30)
    except subprocess.TimeoutExpired:
        return "skip"
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] in {"ok", "blocked"}
    if data["status"] == "ok":
        assert data["kind"] == "workbook_rows"
        assert data["records"]
    else:
        assert data["code"] in {"blocked", "timeout", "unreachable"}
        return "skip"
    return True


results.append(check("live ite-enrolments returns evidenced rows", test_ite_enrolments_live_or_blocked))


def test_tds_live_or_blocked() -> bool | str:
    try:
        result = run(["tds", "--year", "2025", "--json"], timeout=30)
    except subprocess.TimeoutExpired:
        return "skip"
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] in {"ok", "blocked"}
    if data["status"] == "ok":
        assert data["kind"] == "tds_publications"
        assert data["publications"]
        assert all(item.get("year") == 2025 for item in data["publications"])
    else:
        assert data["code"] in {"blocked", "timeout", "unreachable"}
        return "skip"
    return True


results.append(check("live tds returns evidenced publications", test_tds_live_or_blocked))


def test_tds_detail_fixture() -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("education_counts_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    detail_html = """
    <html><body>
      <h1>Teacher Demand and Supply Planning Projection - 2025 results</h1>
      <p>Date Published: February 2026</p>
      <h2>Key findings</h2>
      <a href="/files/national.pdf">A3: Teacher Demand and Supply Planning Projection 2025 - The National Picture</a>
      <a href="/files/auckland.pdf">A3: Teacher Demand and Supply Planning Projection 2025 - Auckland region</a>
    </body></html>
    """
    parser = module.ResourceParser("https://www.educationcounts.govt.nz/publications/tds-2025")
    parser.feed(detail_html)
    parser.close()
    assert parser.release_date == "February 2026"
    assert len(parser.links) == 2
    assert parser.links[0]["format"] == "pdf"
    return True


results.append(check("fixture tds detail parser finds regional source documents", test_tds_detail_fixture))


def test_combined_ite_resource_fixture() -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("education_counts_resource_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    label = "ITE Statistics (XLS, 839.2 KB)"
    url = "https://www.educationcounts.govt.nz/ITE-tables-full-year-enrolments-2005-2025-and-completions-2005-2024.xlsx"
    assert module.resource_key(label, url) == "ite-enrolments-completions"
    return True


results.append(check("fixture combined ITE workbook supports enrolments and completions", test_combined_ite_resource_fixture))


def test_workbook() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.xlsx"
        make_xlsx(path)
        data = parse_json(["workbook", "--url", path.as_uri(), "--from", "2025", "--to", "2025", "--json"])
    assert data["status"] == "ok"
    assert data["sheet"] == "Data"
    assert any(row["year"] == 2025 and row["value"] == "1990" for row in data["records"])
    return True


results.append(check("fixture workbook parses local XLSX source", test_workbook))


def test_workbook_absolute_target() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture-absolute.xlsx"
        make_xlsx(path, absolute_target=True)
        data = parse_json(["workbook", "--url", path.as_uri(), "--sheet", "Data", "--json"])
    assert data["status"] == "ok"
    assert data["row_count"] == 3
    return True


results.append(check("fixture workbook handles absolute relationship targets", test_workbook_absolute_target))


def test_resources_block_or_ok() -> bool | str:
    try:
        result = run(["resources", "--dataset", "teacher-numbers", "--json"], timeout=30)
    except subprocess.TimeoutExpired:
        return "skip"
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] in {"ok", "blocked"}
    if data["status"] == "ok":
        assert data["count"] > 0
        assert data["resources"]
    else:
        assert data["code"] in {"blocked", "timeout", "unreachable"}
        return "skip"
    return True


results.append(check("live resources returns evidenced records", test_resources_block_or_ok))

if all(results):
    print("All tests passed.")
    raise SystemExit(0)

print(f"{results.count(False)} test(s) failed.")
raise SystemExit(1)
