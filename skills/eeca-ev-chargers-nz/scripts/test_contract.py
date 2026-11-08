#!/usr/bin/env python3
"""Deterministic repository contract test for this skill."""
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = SKILL_DIR / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402

_spec = importlib.util.spec_from_file_location("eeca_ev_chargers_cli", SKILL_DIR / "scripts" / "cli.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

# Trimmed captures of the EECA dashboard CSVs taken 2026-11-07 (renamed headers;
# district export with two "Region" columns).
CAPTURES = {
    "chargers": "chargers-2026-11.csv",
    "cofunded": "cofunded-2026-11.csv",
    "metrics-region": "metrics-region-2026-11.csv",
    "metrics-district": "metrics-district-2026-11.csv",
}


def capture(resource: str) -> str:
    return (FIXTURES / CAPTURES[resource]).read_text(encoding="utf-8-sig")


def run_cli(argv: list[str]) -> dict:
    def fake_fetch(resource: str, timeout: int = 30):
        return cli.parse_csv(capture(resource), resource), "fixture://" + resource

    out = io.StringIO()
    with patch.object(cli, "fetch_csv_rows", side_effect=fake_fetch), contextlib.redirect_stdout(out):
        cli.main(argv)
    return json.loads(out.getvalue())


class CsvSchema(unittest.TestCase):
    def test_renamed_charger_points_column(self):
        rows = [cli.normalise_charger(r) for r in cli.parse_csv(capture("chargers"), "chargers")]
        self.assertEqual([r["points"] for r in rows], [1, 1, 2, 1])
        self.assertEqual(rows[0]["region"], "Auckland")

    def test_cofunded_renamed_id_and_points(self):
        rows = [cli.normalise_cofunded(r) for r in cli.parse_csv(capture("cofunded"), "cofunded")]
        self.assertEqual(rows[0]["application_id"], "01-001")
        self.assertEqual(rows[0]["points"], 24)

    def test_district_export_duplicate_region_header(self):
        rows = [cli.normalise_metric(r, "district") for r in cli.parse_csv(capture("metrics-district"), "metrics-district")]
        self.assertEqual([(r["name"], r["region"]) for r in rows],
                         [("Auckland", "Auckland"), ("Hamilton", "Waikato"), ("Taupo", "Waikato")])
        self.assertEqual(rows[0]["charge_points"], 470)
        self.assertAlmostEqual(rows[0]["bevs_per_charge_point"], 85.519, places=3)

    def test_legacy_headers_still_parse(self):
        text = "Region,Charge Points,Battery Electric Vehicles,BEVs per Charge Point\nAuckland,10,200,20\n"
        row = cli.normalise_metric(cli.parse_csv(text, "metrics-region")[0], "region")
        self.assertEqual((row["charge_points"], row["bevs_per_charge_point"]), (10, 20.0))

    def test_missing_column_is_schema_failure(self):
        with self.assertRaisesRegex(ValueError, "missing expected columns: Charge Points"):
            cli.parse_csv("Region,Points,Battery Electric Vehicles,BEVs per Charge Point\nAuckland,1,2,3\n", "metrics-region")
        with self.assertRaisesRegex(ValueError, "duplicate columns: Region"):
            cli.parse_csv("Region,Region,District,Charge Points,Battery Electric Vehicles,BEVs per Charge Point\n", "metrics-district")

    def test_region_summary_counts_points_and_ratio(self):
        data = run_cli(["summary", "--level", "region", "--region", "Auckland", "--json"])
        self.assertEqual(data["count"], 1)
        row = data["records"][0]
        self.assertEqual((row["name"], row["charge_points"], row["dc_fast_sites"]), ("Auckland", 4, 2))
        self.assertAlmostEqual(row["bevs_per_charge_point"], 40194 / 4)

    def test_district_summary_honours_region_filter(self):
        data = run_cli(["summary", "--level", "district", "--region", "Auckland", "--limit", "10", "--json"])
        self.assertEqual([r["name"] for r in data["records"]], ["Auckland"])
        self.assertEqual(data["records"][0]["dashboard_metric"]["region"], "Auckland")
        self.assertIsNotNone(data["records"][0]["bevs_per_charge_point"])


def main() -> int:
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(CsvSchema))
    audit = run_contract_test(SKILL_DIR)
    return 0 if audit == 0 and result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
