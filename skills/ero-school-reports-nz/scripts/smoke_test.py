#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

S = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S.parents[1] / "lib"))
sys.path.insert(0, str(S))

from ero_reports import (
    parse_page,
    report_organisation_rows,
    report_sections,
    require_report,
    resolve_report_organisation_url,
)

page = parse_page(
    (S / "tests/fixtures/institution.html").read_text(),
    "https://www.ero.govt.nz/institution/54/auckland-grammar-school",
    "2026-07-19T00:00:00Z",
)
reports = report_sections(page)
assert reports and reports[0]["published_on"] == "2026-05-14" and reports[0]["report_type"] == "Auckland Grammar School"
assert reports[0]["id"].startswith("54/2026-05-14:") and all("999" not in row["source_url"] for row in page["institutions"])
assert {section["heading"] for section in reports[0]["sections"]} >= {"School Evaluation Report", "Findings", "Next steps for improvement", "Expected outcomes"}
actions = [s for s in require_report(reports, reports[0]["id"])["sections"] if "next steps" in s["heading"].casefold()]
assert actions and "equity" in actions[0]["text"]
try:
    require_report(reports, "54/1900-01-01:not-a-report")
except ValueError:
    pass
else:
    raise AssertionError("nonexistent ERO report ID must be rejected")

footer_page = parse_page(
    (S / "tests/fixtures/other_reports_footer.html").read_text(),
    "https://www.ero.govt.nz/institution/54/auckland-grammar-school",
    "2026-09-04T00:00:00Z",
)
footer_reports = report_sections(footer_page)
assert [report["report_type"] for report in footer_reports[:1]] == ["School Evaluation Report"]
assert footer_reports[0]["published_on"] == "2026-05-14"
assert all(report["report_type"] != "Other Reports" for report in footer_reports)

payload = json.loads((S / "tests/fixtures/reports_api.json").read_text())
api_rows = report_organisation_rows(payload, "2026-07-19T00:00:00Z", "54")
assert api_rows == [
    {
        "title": "Auckland Grammar School",
        "source_url": "https://www.ero.govt.nz/institution/54/auckland-grammar-school",
        "retrieved_at": "2026-07-19T00:00:00Z",
    }
]
assert report_organisation_rows(payload, "2026-07-19T00:00:00Z", "Auckland Grammar School") == api_rows
assert resolve_report_organisation_url(payload, "54") == "https://www.ero.govt.nz/institution/54/auckland-grammar-school"
assert report_organisation_rows({"reportOrganisation": []}, "2026-07-19T00:00:00Z", "54") == []
for broken_payload in ({}, {"reportOrganisation": None}, {"reportOrganisation": "oops"}):
    try:
        report_organisation_rows(broken_payload, "2026-07-19T00:00:00Z", "54")
    except ValueError as exc:
        assert "unexpected payload" in str(exc)
    else:
        raise AssertionError("malformed ERO reports payload must fail closed")
    try:
        resolve_report_organisation_url(broken_payload, "54")
    except ValueError as exc:
        assert "unexpected payload" in str(exc)
    else:
        raise AssertionError("malformed ERO reports payload must fail closed")
cli_probe = subprocess.run(
    [
        sys.executable,
        "-c",
        (
            "import sys; from pathlib import Path; "
            f"S = Path({str(S)!r}); "
            "sys.path.insert(0, str(S / 'scripts')); "
            "import cli as ero_cli; "
            "ero_cli.fetch_reports_index = lambda *a, **k: {}; "
            "sys.argv = ['cli.py', 'search', '54', '--json']; "
            "raise SystemExit(ero_cli.main())"
        ),
    ],
    capture_output=True,
    text=True,
    timeout=45,
    check=False,
)
assert cli_probe.returncode == 6
assert "unexpected payload" in cli_probe.stderr
print("[PASS] fixture ERO institution titles, strict report IDs, findings/actions text, section provenance and reports API lookup")

run = subprocess.run([sys.executable, str(S / "scripts/cli.py"), "latest", "54", "--json"], capture_output=True, text=True, timeout=45, check=False)
if run.returncode == 0:
    out = json.loads(run.stdout)
    assert "/institution/54/" in out["source"]["url"] and out["data"]
    print("[PASS] live official ERO institution report")
elif run.returncode in {4, 5}:
    print(f"[SKIP] ERO blocked/unavailable: {run.stderr.strip()}")
else:
    print(run.stderr, file=sys.stderr)
    raise SystemExit(1)
