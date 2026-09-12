#!/usr/bin/env python3
"""Deterministic aggregate-finance parser and CLI contract tests."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL.parents[1] / "lib"))

import cli  # noqa: E402
import nzfetch  # noqa: E402
from political_finance import (  # noqa: E402
    ANNUAL_URL,
    EXPENSE_URLS,
    filter_party,
    parse_annual_aggregates,
    parse_expense_aggregates,
    parse_money,
    parse_reporting_rules,
    safe_source_url,
)

STAMP = "2026-09-12T00:00:00Z"
FIXTURES = SKILL / "tests" / "fixtures"
ANNUAL = (FIXTURES / "finance-annual.html").read_text(encoding="utf-8")
EXPENSES = (FIXTURES / "finance-expenses.html").read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_annual_aggregate_grain_and_privacy_boundary(self) -> None:
        rows = parse_annual_aggregates(ANNUAL, ANNUAL_URL, STAMP, 2025)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["party_name_as_published"], "Kōwhai Example Party")
        self.assertEqual(rows[0]["amount_nzd"], "1234.50")
        self.assertEqual(rows[1]["amount_nzd"], "0.00")
        self.assertIsNone(rows[3]["amount_nzd"])
        self.assertEqual(rows[0]["filing_dates"], ["2026-04-30", "2026-05-08"])
        serialised = json.dumps(rows)
        for forbidden in ("Individual contributor", "document_url", "address"):
            self.assertNotIn(forbidden, serialised)

    def test_expense_aggregates_remain_distinct_metrics(self) -> None:
        rows = parse_expense_aggregates(EXPENSES, EXPENSE_URLS[2023], STAMP, 2023)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[2]["metric"], "broadcasting_allocation")
        self.assertEqual(rows[2]["amount_nzd"], "0.00")
        self.assertIsNone(rows[-1]["amount_nzd"])
        self.assertTrue(all(row["period_start"] == "2023-07-14" for row in rows))
        self.assertTrue(all(row["period_end"] == "2023-10-13" for row in rows))
        expense_rules = parse_reporting_rules(EXPENSES, EXPENSE_URLS[2023], STAMP, 2023)
        self.assertTrue(any(row["amounts_nzd_mentioned"] == ["1388000.00", "32600.00"] for row in expense_rules))
        self.assertTrue(any(row["rule_type"] == "component_party" for row in expense_rules))
        self.assertTrue(any("13 March, 2024" in str(row["evidence_text"]) and row["rule_type"] == "filing_deadline" for row in expense_rules))
        self.assertTrue(any("need to declare" in str(row["evidence_text"]) for row in expense_rules))
        self.assertTrue(any("required to include an audit report" in str(row["evidence_text"]) for row in expense_rules))
        self.assertTrue(all(row["reporting_year"] == 2023 for row in expense_rules))

    def test_rule_year_comes_from_reporting_section_not_deadline_year(self) -> None:
        rules_2024 = parse_reporting_rules(ANNUAL, ANNUAL_URL, STAMP, 2024)
        threshold = next(row for row in rules_2024 if row["amounts_nzd_mentioned"] == ["20000.00"])
        self.assertEqual(threshold["reporting_year"], 2024)
        self.assertIn("30 April 2025", str(threshold["evidence_text"]))
        with self.assertRaisesRegex(ValueError, "scoped to 2025"):
            parse_reporting_rules(
                '<h1>Party returns</h1><button class="accordion__title">2024 party returns</button>'
                '<p>Returns were due on 30 April 2025 and include donations over $20,000 during 2024.</p>',
                ANNUAL_URL,
                STAMP,
                2025,
            )

    def test_reporting_rules_retain_wording_without_effective_date_guess(self) -> None:
        rules = parse_reporting_rules(ANNUAL, ANNUAL_URL, STAMP, 2025)
        threshold = next(row for row in rules if row["amounts_nzd_mentioned"])
        self.assertEqual(threshold["reporting_year"], 2025)
        self.assertEqual(threshold["amounts_nzd_mentioned"], ["5000.00"])
        self.assertIsNone(threshold["effective_from"])
        self.assertEqual(threshold["interpretation_status"], "source_wording_only_not_normalised_legal_rule")

    def test_empty_party_filter_is_successful_empty_data(self) -> None:
        rows = parse_annual_aggregates(ANNUAL, ANNUAL_URL, STAMP, 2025)
        self.assertEqual(filter_party(rows, "No Such Synthetic Party"), [])

    def test_adversarial_layout_amount_duplicate_and_url_fail_closed(self) -> None:
        bad_layout = ANNUAL.replace("<td>$1,234.50</td>", '<td colspan="2">$1,234.50</td>', 1)
        with self.assertRaisesRegex(ValueError, "layout"):
            parse_annual_aggregates(bad_layout, ANNUAL_URL, STAMP, 2025)
        bad_amount = ANNUAL.replace("$1,234.50", "about $1,234", 1)
        with self.assertRaisesRegex(ValueError, "amount"):
            parse_annual_aggregates(bad_amount, ANNUAL_URL, STAMP, 2025)
        duplicate = ANNUAL.replace("</table>", "<tr><td>Kōwhai Example Party</td><td>$2</td><td>$3</td><td></td><td></td></tr></table>", 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_annual_aggregates(duplicate, ANNUAL_URL, STAMP, 2025)
        expense_row = '<tr><td>Kōwhai Example Party</td><td>$2</td><td>$3</td><td>$4</td><td>$5</td><td>Filed</td></tr>'
        duplicate_expense = EXPENSES.replace("</table>", expense_row + "</table>", 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_expense_aggregates(duplicate_expense, EXPENSE_URLS[2023], STAMP, 2023)
        for url in ("http://elections.nz/example", "https://elections.nz.evil.test/", "https://user:secret@elections.nz/"):
            with self.assertRaises(ValueError):
                safe_source_url(url)
        for value in ("$12,34", "1.234", "NaN", "-1", "1e3"):
            with self.assertRaises(ValueError):
                parse_money(value)
        with self.assertRaisesRegex(ValueError, "requested reporting year 2016"):
            parse_annual_aggregates(ANNUAL, ANNUAL_URL, STAMP, 2016)


class CliTests(unittest.TestCase):
    def invoke(self, argv: list[str], response: str | Exception) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        side_effect = response if isinstance(response, Exception) else None
        return_value = None if side_effect else response
        with patch.object(sys, "argv", ["cli.py", *argv]), patch.object(
            cli.nzfetch, "fetch_text", return_value=return_value, side_effect=side_effect
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_normal_and_empty_result_envelopes(self) -> None:
        code, stdout, _ = self.invoke(["finance-aggregates", "Kōwhai", "--year", "2025", "--json"], ANNUAL)
        payload = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["data"]), 2)
        self.assertFalse(payload["blocked"])

        code, stdout, _ = self.invoke(["finance-aggregates", "Missing", "--year", "2025", "--json"], ANNUAL)
        payload = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"], [])

    def test_cli_blocked_is_not_empty_success(self) -> None:
        code, stdout, stderr = self.invoke(
            ["finance-aggregates", "--year", "2025", "--json"],
            nzfetch.Blocked("official source challenge"),
        )
        self.assertEqual(code, 4)
        self.assertEqual(stdout, "")
        error = json.loads(stderr)
        self.assertEqual(error["error"], "blocked")
        self.assertNotIn("data", error)

    def test_cli_unsupported_requested_year_layout_is_schema_error(self) -> None:
        code, stdout, stderr = self.invoke(
            ["finance-aggregates", "--year", "2016", "--json"], ANNUAL
        )
        self.assertEqual(code, 6)
        self.assertEqual(stdout, "")
        error = json.loads(stderr)
        self.assertEqual(error["error"], "invalid_input_or_source_schema")
        self.assertIn("requested reporting year 2016", error["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
