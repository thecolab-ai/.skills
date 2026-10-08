#!/usr/bin/env python3
"""Smoke tests for oia-statistics-nz.

Network-dependent commands return upstream_unavailable on blocked/outage states and
are treated as skip conditions.
"""
from __future__ import annotations

import json
import io
import zipfile
from xml.etree import ElementTree as ET
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=timeout)


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> dict:
    payload = (proc.stdout or proc.stderr).strip()
    return json.loads(payload or "{}") if payload else {}


def is_upstream_skip(proc: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    if proc.returncode != 2:
        return False, ""
    try:
        data = parse_json_output(proc)
    except Exception:
        return False, ""
    if data.get("error") == "upstream_unavailable":
        return True, str(data.get("message", ""))
    return False, ""


def main() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location("oia_statistics_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.row_enriched(
        {
            "OrgID": "42",
            "Agency": "Synthetic Agency",
            "Agency_Type": "Department",
            "SurveyPeriodEndDate": "2025-12-31T00:00:00",
            "OIA_RequestsHandled": "200",
            "OIAs_CompletedWithinTimeframe": "180",
            "OIA_refused": "10",
        }
    )
    if record["org_id"] != 42 or record["timeliness_pct"] != 90.0 or record["refusals_pct"] != 5.0:
        print("[FAIL] fixture OIA CSV row normalisation", file=sys.stderr)
        return 1
    print("[PASS] fixture OIA CSV row normalisation")

    # Small synthetic OOXML workbook in the current published response shape.
    from oia_workbooks import parse_release
    tables = json.loads((ROOT / 'tests/fixtures/release-tables.json').read_text())
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    workbook = ET.Element('workbook', xmlns=ns)
    sheets = ET.SubElement(workbook, 'sheets')
    relations = ET.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
    body = io.BytesIO()
    with zipfile.ZipFile(body, 'w') as archive:
        for index, (name, rows) in enumerate(tables.items(), 1):
            ET.SubElement(sheets, 'sheet', name=name, sheetId=str(index), attrib={'{' + relns + '}id': f'rId{index}'})
            ET.SubElement(relations, 'Relationship', Id=f'rId{index}', Target=f'worksheets/sheet{index}.xml')
            sheet = ET.Element('worksheet', xmlns=ns)
            data = ET.SubElement(sheet, 'sheetData')
            for number, values in enumerate(rows, 1):
                row = ET.SubElement(data, 'row', r=str(number))
                for col, value in enumerate(values):
                    if value is None:
                        continue
                    cell = ET.SubElement(row, 'c', r=f'{chr(65 + col)}{number}')
                    if isinstance(value, str):
                        cell.set('t', 'inlineStr')
                        ET.SubElement(ET.SubElement(cell, 'is'), 't').text = value
                    else:
                        ET.SubElement(cell, 'v').text = str(value)
            archive.writestr(f'xl/worksheets/sheet{index}.xml', ET.tostring(sheet))
        archive.writestr('xl/workbook.xml', ET.tostring(workbook))
        archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(relations))
    parsed = parse_release(body.getvalue(), '2026-06-30')
    assert len(parsed) == 2 and parsed[0]['OIA_extension'] == '4'
    assert parsed[0]['Ombudsman_Complaints'] == '3' and parsed[0]['OIA_refused'] == '10'
    assert 'OrgID' not in parsed[0] and parsed[0]['_identity_warning']
    raw = [dict(parsed[0], OrgID='42', SurveyPeriodEndDate='00:00.0'),
           dict(parsed[1], SurveyPeriodEndDate='00:00.0'),
           dict(parsed[1], SurveyPeriodEndDate='00:00.0')]
    repaired = module.recover_release_periods(raw, [('2026-06-30', 'https://www.publicservice.govt.nz/assets/synthetic.xlsx', '2026-10-08T00:00:00Z', parsed)])
    assert repaired[0]['SurveyPeriodEndDate'] == '2026-06-30'
    assert repaired[-1]['SurveyPeriodEndDate'] == '00:00.0'
    assert len(module._rows_by_period(repaired)['2026-06-30']) == 2
    assert module.periods_summary(repaired)[0]['period_end'] == '2026-06-30'
    assert module.row_enriched(repaired[0])['source_url'].endswith('synthetic.xlsx')
    assert module._norm_period('2026-99-99') == ''
    assert module._norm_period('00:00.0') == ''
    assert module.infer_period_from_text('OIA Statistics: 1 January to 30 June 2026(XLSX)') == '2026-06-30'
    try:
        parse_release(b'broken workbook', '2026-06-30')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid workbook must fail closed')
    print('[PASS] fixture official release discovery, stdlib OOXML, exact date recovery, conflicting IDs and ambiguous matches')

    help_proc = run(["--help"], timeout=20)
    if help_proc.returncode != 0 or "list-agencies" not in (help_proc.stdout or ""):
        print("FAIL: --help should list available commands", file=sys.stderr)
        print(help_proc.stdout)
        print(help_proc.stderr, file=sys.stderr)
        return 1

    periods = run(["periods", "--limit", "1", "--json"])
    if periods.returncode == 2:
        skip, message = is_upstream_skip(periods)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(periods.stderr or periods.stdout, file=sys.stderr)
        return 1
    if periods.returncode != 0:
        print(periods.stderr or periods.stdout, file=sys.stderr)
        return 1

    periods_data = parse_json_output(periods)
    if periods_data.get("kind") != "oia-periods" or not isinstance(periods_data.get("periods"), list):
        print("FAIL: periods command did not return expected JSON shape", file=sys.stderr)
        print(periods.stdout, file=sys.stderr)
        return 1
    latest_period = periods_data.get("latest_period")
    if not latest_period or not periods_data['periods']:
        print('[FAIL] live periods must contain dated source records', file=sys.stderr)
        return 1
    print(f"[PASS] live periods returned {periods_data.get('count')} period(s)")

    agencies = run(["list-agencies", "--limit", "3", "--json"])
    if agencies.returncode == 2:
        skip, message = is_upstream_skip(agencies)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(agencies.stderr or agencies.stdout, file=sys.stderr)
        return 1
    if agencies.returncode != 0:
        print(agencies.stderr or agencies.stdout, file=sys.stderr)
        return 1
    agencies_data = parse_json_output(agencies)
    agency_rows = agencies_data.get("agencies") or []
    if agencies_data.get("kind") != "oia-list-agencies" or not agency_rows:
        print("FAIL: list-agencies command did not return expected agency rows", file=sys.stderr)
        print(agencies.stdout, file=sys.stderr)
        return 1

    org_id = agency_rows[0].get("org_id")
    if isinstance(org_id, int):
        agency = run(["agency", str(org_id), "--json"], timeout=180)
        if agency.returncode == 2:
            skip, message = is_upstream_skip(agency)
            if skip:
                print(f"SKIP: upstream unavailable ({message})")
                return 0
            print(agency.stderr or agency.stdout, file=sys.stderr)
            return 1
        if agency.returncode != 0:
            print(agency.stderr or agency.stdout, file=sys.stderr)
            return 1
        agency_data = parse_json_output(agency)
        if agency_data.get("kind") != "oia-agency" or not agency_data.get("records"):
            print("FAIL: agency command did not return expected records", file=sys.stderr)
            print(agency.stdout, file=sys.stderr)
            return 1
        print(f"[PASS] live agency lookup by OrgID {org_id} returned {len(agency_data['records'])} rows")

    totals = run(["totals", "--period", latest_period or "latest", "--json"], timeout=120)
    if totals.returncode == 2:
        skip, message = is_upstream_skip(totals)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(totals.stderr or totals.stdout, file=sys.stderr)
        return 1
    if totals.returncode != 0:
        print(totals.stderr or totals.stdout, file=sys.stderr)
        return 1
    totals_data = parse_json_output(totals)
    if totals_data.get("kind") != "oia-totals" or not isinstance(totals_data.get("totals"), dict):
        print("FAIL: totals command did not return expected shape", file=sys.stderr)
        print(totals.stdout, file=sys.stderr)
        return 1
    if totals_data['totals'].get('requests_handled', 0) <= 0:
        print("FAIL: totals command returned no handled requests", file=sys.stderr)
        return 1
    print(f"[PASS] live totals returned requests_handled={totals_data['totals'].get('requests_handled')}")

    complaints = run(["complaints", "--period", latest_period or "latest", "--sort", "complaints", "--limit", "5", "--json"], timeout=120)
    if complaints.returncode != 0:
        print(complaints.stderr or complaints.stdout, file=sys.stderr)
        return 1
    complaints_data = parse_json_output(complaints)
    records = complaints_data.get("records", [])
    if any((r.get("org_id") in (0, None)) or r.get("agency_type") == "Agency Type Totals" for r in records):
        print("FAIL: complaints includes aggregate rows", file=sys.stderr)
        return 1
    counts = [r.get("complaints", 0) for r in records]
    if counts != sorted(counts, reverse=True):
        print("FAIL: complaints sort is not descending", file=sys.stderr)
        return 1
    print("[PASS] live complaints excludes aggregate rows and sorts descending")

    return 0


if __name__ == "__main__":
    sys.exit(main())
