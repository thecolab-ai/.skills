#!/usr/bin/env python3
"""Fixture-backed behavior and repository contract tests for SeaRise NZ."""
from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
FIXTURES = SKILL_DIR / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))

import nzfetch  # noqa: E402
from contract_test import run_contract_test  # noqa: E402


def load_cli():
    spec = importlib.util.spec_from_file_location("searise_contract_cli", SKILL_DIR / "scripts" / "cli.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_rows(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO((FIXTURES / name).read_text(encoding="utf-8"))))


class SeaRiseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cli = load_cli()

    def run_command(self, function, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                function(args)
            except SystemExit as exc:
                return exc.code, stdout.getvalue(), stderr.getvalue()
        return 0, stdout.getvalue(), stderr.getvalue()

    def test_record_normalizes_zenodo_metadata_and_file_inventory(self):
        args = self.cli.parse_cli_args(["record", "--json"])
        with mock.patch.object(self.cli.nzfetch, "fetch_json", return_value=fixture_json("record-sample.json")) as fetch:
            code, stdout, stderr = self.run_command(self.cli.cmd_record, args)

        self.assertEqual((code, stderr), (0, ""))
        fetch.assert_called_once_with(
            self.cli.RECORD_API_URL,
            timeout=30,
            allowed_hosts=[self.cli.HOST],
        )
        payload = json.loads(stdout)
        self.assertEqual(payload["kind"], "record")
        self.assertEqual(payload["record_id"], 14722058)
        self.assertEqual(payload["doi"], "10.5281/zenodo.14722058")
        self.assertEqual(payload["version"], "4")
        self.assertEqual(payload["publication_date"], "2025-01-23")
        self.assertEqual(payload["title"], "New Zealand Vertical land movement and sea rise projections")
        self.assertEqual(payload["creators"][0]["name"], "Hamling, Ian")
        self.assertEqual(payload["licence"], "cc-by-4.0")
        self.assertEqual(payload["file_count"], 2)
        # Site details are NOT in this record; provenance must say where they come from.
        self.assertTrue(payload["site_details_record_url"].endswith("/11398538"))
        self.assertEqual(
            payload["files"][0],
            {
                "key": "NZ_Searise_noVLM-2005.csv",
                "size": 57854135,
                "checksum": "md5:11111111111111111111111111111111",
                "download_url": (
                    "https://zenodo.org/api/records/14722058/files/"
                    "11111111-1111-1111-1111-111111111111/content"
                ),
            },
        )

    def test_record_rejects_malformed_upstream_payload_with_structured_error(self):
        args = self.cli.parse_cli_args(["record", "--json"])
        with mock.patch.object(self.cli.nzfetch, "fetch_json", return_value={"id": 14722058, "metadata": []}):
            code, _stdout, stderr = self.run_command(self.cli.cmd_record, args)

        self.assertEqual(code, 6)
        error = json.loads(stderr)
        self.assertEqual(error["error"], "source_schema_failure")
        self.assertIn("metadata", error["message"])

    def test_record_reports_structured_upstream_failure(self):
        args = self.cli.parse_cli_args(["record", "--json"])
        with mock.patch.object(
            self.cli.nzfetch,
            "fetch_json",
            side_effect=nzfetch.FetchError("HTTP 503 for record"),
        ):
            code, _stdout, stderr = self.run_command(self.cli.cmd_record, args)

        self.assertEqual(code, 5)
        error = json.loads(stderr)
        self.assertEqual(error["error"], "source_unavailable")
        self.assertIn("HTTP 503", error["message"])

    def test_fetch_csv_returns_an_iterator_instead_of_a_materialized_list(self):
        text = (FIXTURES / "projections-sample.csv").read_text(encoding="utf-8")
        with mock.patch.object(self.cli.nzfetch, "fetch_text", return_value=text):
            rows = self.cli.fetch_csv(self.cli.PROJ_VLM_URL)

        self.assertNotIsInstance(rows, list)
        self.assertIs(iter(rows), rows)
        self.assertEqual(next(rows)["site"], "2503")

    def test_single_site_projection_payload_is_backward_compatible(self):
        args = self.cli.parse_cli_args(["projections", "2503", "--json"])
        with mock.patch.object(
            self.cli,
            "fetch_csv",
            return_value=iter(fixture_rows("projections-sample.csv")),
        ) as fetch:
            code, stdout, stderr = self.run_command(self.cli.cmd_projections, args)

        self.assertEqual((code, stderr), (0, ""))
        fetch.assert_called_once_with(self.cli.PROJ_VLM_URL, timeout=120)
        payload = json.loads(stdout)
        self.assertEqual(
            set(payload),
            {
                "kind",
                "source",
                "source_url",
                "licence",
                "note",
                "site_id",
                "vlm_included",
                "available_scenarios",
                "row_count",
                "projections",
            },
        )
        self.assertEqual(payload["site_id"], 2503)
        self.assertEqual(payload["row_count"], 6)
        # Sorted by (scenario, confidence, year): the 2005 baseline sorts first
        # within SSP1-2.6/low, so SSP2-4.5/medium/2100 is index 2.
        self.assertEqual(payload["projections"][0]["year"], 2005)
        self.assertEqual(payload["projections"][2]["p50_m"], 0.71)

    def test_projection_scan_rejects_every_corrupt_required_value(self):
        valid = fixture_rows("projections-sample.csv")[0]
        corruptions = (
            ("blank site", "site", ""),
            ("malformed site", "site", "34.14"),
            ("negative site", "site", "-1"),
            ("blank year", "year", ""),
            ("malformed year", "year", "twenty-twenty"),
            ("year below source bounds", "year", "2004"),
            ("year above source bounds", "year", "2301"),
            ("blank SSP", "SSP", ""),
            ("unsupported SSP", "SSP", "SSP9"),
            ("blank scenario", "scenario", ""),
            ("unsupported scenario", "scenario", "9.9"),
            ("blank confidence", "Confidence", ""),
            ("malformed confidence", "Confidence", "medium"),
            ("unsupported confidence", "Confidence", "high_confidence"),
            ("blank p17", "17", ""),
            ("non-numeric p50", "50", "not-a-number"),
            ("NaN p83", "83", "nan"),
            ("infinite p17", "17", "inf"),
            ("negative infinite p50", "50", "-inf"),
        )
        for label, field, value in corruptions:
            with self.subTest(label=label):
                row = dict(valid)
                row[field] = value
                with self.assertRaises(self.cli.SourceSchemaError):
                    self.cli.scan_projection_rows(iter([row]), [2503])

    def test_corrupt_projection_rows_are_structured_failures_for_single_and_multi_site(self):
        valid = fixture_rows("projections-sample.csv")[0]
        cases = (
            (["projections", "2503", "--json"], "50", "nan"),
            (["projections", "2503", "9999", "--json"], "scenario", ""),
        )
        for argv, field, value in cases:
            with self.subTest(argv=argv, field=field):
                row = dict(valid)
                row[field] = value
                args = self.cli.parse_cli_args(argv)
                with mock.patch.object(self.cli, "fetch_csv", return_value=iter([row])):
                    code, stdout, stderr = self.run_command(self.cli.cmd_projections, args)
                self.assertEqual((code, stdout), (6, ""))
                error = json.loads(stderr)
                self.assertEqual(error["error"], "source_schema_failure")
                self.assertIn(field, error["message"])

    def test_multi_site_projection_scan_is_one_pass_and_preserves_order_duplicates_and_missing(self):
        class OnePassRows:
            def __init__(self, rows):
                self.rows = rows
                self.iterations = 0

            def __iter__(self):
                self.iterations += 1
                if self.iterations > 1:
                    raise AssertionError("projection CSV was scanned more than once")
                return iter(self.rows)

        source = OnePassRows(fixture_rows("projections-sample.csv"))
        args = self.cli.parse_cli_args(["projections", "9999", "2503", "2503", "7777", "--json"])
        with mock.patch.object(self.cli, "fetch_csv", return_value=source) as fetch:
            code, stdout, stderr = self.run_command(self.cli.cmd_projections, args)

        self.assertEqual((code, stderr), (0, ""))
        fetch.assert_called_once_with(self.cli.PROJ_VLM_URL, timeout=120)
        self.assertEqual(source.iterations, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["requested_site_ids"], [9999, 2503, 2503, 7777])
        self.assertEqual([site["site_id"] for site in payload["sites"]], [9999, 2503, 2503, 7777])
        self.assertEqual([site["status"] for site in payload["sites"]], ["ok", "ok", "ok", "not_found"])
        self.assertEqual(payload["sites"][1], payload["sites"][2])
        self.assertEqual(payload["sites"][3]["row_count"], 0)
        self.assertEqual(payload["sites"][3]["projections"], [])

    def test_multi_site_filters_and_no_vlm_apply_to_every_site(self):
        args = self.cli.parse_cli_args(
            [
                "projections",
                "2503",
                "9999",
                "--scenario",
                "SSP2-4.5",
                "--confidence",
                "medium",
                "--year",
                "2100",
                "--no-vlm",
                "--json",
            ]
        )
        with mock.patch.object(
            self.cli,
            "fetch_csv",
            return_value=iter(fixture_rows("projections-sample.csv")),
        ) as fetch:
            code, stdout, stderr = self.run_command(self.cli.cmd_projections, args)

        self.assertEqual((code, stderr), (0, ""))
        fetch.assert_called_once_with(self.cli.PROJ_NOVLM_URL, timeout=120)
        payload = json.loads(stdout)
        self.assertFalse(payload["vlm_included"])
        self.assertEqual([site["row_count"] for site in payload["sites"]], [1, 1])
        for site in payload["sites"]:
            self.assertEqual(site["projections"][0]["scenario"], "SSP2-4.5")
            self.assertEqual(site["projections"][0]["confidence"], "medium")
            self.assertEqual(site["projections"][0]["year"], 2100)

    def test_multi_site_distinguishes_filtered_empty_from_missing(self):
        args = self.cli.parse_cli_args(
            ["projections", "2503", "7777", "--scenario", "SSP1-1.9", "--json"]
        )
        with mock.patch.object(
            self.cli,
            "fetch_csv",
            return_value=iter(fixture_rows("projections-sample.csv")),
        ):
            code, stdout, stderr = self.run_command(self.cli.cmd_projections, args)

        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["sites"][0]["status"], "empty")
        self.assertEqual(payload["sites"][1]["status"], "not_found")

    def test_invalid_site_ids_fail_before_fetch_with_structured_error(self):
        for raw in ("-1", "abc"):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    self.cli.parse_cli_args(["projections", raw, "--json"])
            self.assertEqual(raised.exception.code, 2)
            error = json.loads(stderr.getvalue())
            self.assertEqual(error["error"], "invalid_input")

    def test_projection_year_filter_is_bounded_and_zero_never_disables_filtering(self):
        for raw in ("0", "2004", "2301", "not-a-year"):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    self.cli.parse_cli_args(["projections", "2503", "--year", raw, "--json"])
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(json.loads(stderr.getvalue())["error"], "invalid_input")
        for raw in ("2005", "2020", "2300"):
            args = self.cli.parse_cli_args(["projections", "2503", "--year", raw, "--json"])
            self.assertEqual(args.year, int(raw))

        rows = [
            {
                "scenario": "SSP1-2.6",
                "confidence": "low",
                "year": 2020,
                "p17_m": -0.19,
                "p50_m": 0.08,
                "p83_m": 0.36,
            }
        ]
        direct_args = argparse.Namespace(
            scenario=None,
            confidence="all",
            year=0,
            no_vlm=False,
        )
        self.assertEqual(self.cli.filtered_projection_rows(rows, direct_args), [])
        captured_stderr = io.StringIO()
        with contextlib.redirect_stderr(captured_stderr):
            with self.assertRaises(SystemExit) as raised:
                self.cli.single_projection_payload(
                    rows,
                    2503,
                    self.cli.PROJ_VLM_URL,
                    direct_args,
                )
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(json.loads(captured_stderr.getvalue())["error"], "empty_result")

    def test_near_requires_finite_wgs84_coordinates_and_keeps_negative_leading_form(self):
        self.assertEqual(self.cli.parse_latlon("-90,-180"), (-90.0, -180.0))
        self.assertEqual(self.cli.parse_latlon("90,180"), (90.0, 180.0))
        args = self.cli.parse_cli_args(["sites", "--near", "-41.29,174.78", "--json"])
        self.assertEqual(args.near, "-41.29,174.78")

        for raw in (
            "nan,174.78",
            "-41.29,nan",
            "inf,174.78",
            "-41.29,-inf",
            "-90.0001,174.78",
            "-41.29,180.0001",
            "-41.29,-180.0001",
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    self.cli.parse_latlon(raw)
            self.assertEqual(raised.exception.code, 2)
            error = json.loads(stderr.getvalue())
            self.assertEqual(error["error"], "invalid_input")
            self.assertIn("lat must be -90..90, lon -180..180", error["message"])

    def test_malformed_projection_response_is_structured_schema_failure(self):
        malformed = csv.DictReader(io.StringIO("wrong,headers\n1,2\n"))
        args = self.cli.parse_cli_args(["projections", "2503", "--json"])
        with mock.patch.object(self.cli, "fetch_csv", return_value=malformed):
            code, _stdout, stderr = self.run_command(self.cli.cmd_projections, args)

        self.assertEqual(code, 6)
        error = json.loads(stderr)
        self.assertEqual(error["error"], "source_schema_failure")
        self.assertIn("columns", error["message"])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SeaRiseContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    return run_contract_test(SKILL_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
