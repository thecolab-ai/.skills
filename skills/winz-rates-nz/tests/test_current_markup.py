#!/usr/bin/env python3
"""Regression tests for the current WINZ page layouts."""
import importlib.util
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURES = SKILL_DIR / "tests" / "fixtures"

spec = importlib.util.spec_from_file_location("winz_rates_current_markup_tests", CLI)
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)


class CurrentMarkupTests(unittest.TestCase):
    def test_flat_rates_page_groups_tables_under_h2_sections(self):
        fixture = (FIXTURES / "current-rates-page.html").read_text()
        data = cli.parse_rates_page(fixture, 2026, "https://example.test/rates", 200, 1)
        by_slug = {payment["slug"]: payment for payment in data["payments"]}
        self.assertIn("jobseeker-support", by_slug)
        self.assertEqual(
            by_slug["jobseeker-support"]["tables"][0]["rows"],
            [{"Category": "Single, 25 years or over", "Weekly rate after tax": "$372.55"}],
        )
        self.assertIn("funeral-grant", by_slug)
        self.assertEqual(by_slug["funeral-grant"]["tables"], [])
        self.assertIn("income and asset tested", " ".join(by_slug["funeral-grant"]["notes"]))

    def test_current_benefit_cards_support_extensionless_links(self):
        fixture = (FIXTURES / "current-benefit-list.html").read_text()
        data = cli.parse_benefit_list(fixture, "https://example.test/benefits", 200, 1)
        self.assertEqual(
            [benefit["slug"] for benefit in data["benefits"]],
            ["accommodation-supplement", "jobseeker-support"],
        )
        self.assertEqual(
            data["benefits"][0]["summary"],
            "A weekly payment towards accommodation costs.",
        )


if __name__ == "__main__":
    unittest.main()
