#!/usr/bin/env python3
"""Deterministic parser and CLI tests written before implementation."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURE = SKILL_DIR / "tests" / "fixtures" / "source-sample.json"

spec = importlib.util.spec_from_file_location("nzta_highway_info_cli", CLI)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["responses"]

    def test_event_parser_preserves_freshness_and_scope(self) -> None:
        item = module.parse_response(self.fixture["events"], "roadevent", module.normalise_event)[0]
        self.assertEqual(item["id"], 9001)
        self.assertEqual(item["highway"], "SH1")
        self.assertEqual(item["region"], "Wellington")
        self.assertEqual(item["last_updated_at"], "2026-09-03T08:15:00+12:00")
        self.assertFalse(item["planned"])

    def test_camera_parser_builds_official_urls_and_status(self) -> None:
        item = module.parse_response(self.fixture["cameras"], "camera", module.normalise_camera)[0]
        self.assertEqual(item["status"], "maintenance")
        self.assertEqual(item["image_url"], "https://trafficnz.info/camera/7001.jpg")
        self.assertEqual(item["thumbnail_url"], "https://trafficnz.info/camera/thumb/7001.jpg")

    def test_vms_parser_splits_message_pages(self) -> None:
        item = module.parse_response(self.fixture["vms"], "vms", module.normalise_vms)[0]
        self.assertEqual(item["message_lines"], ["ROAD WORKS", "EXPECT DELAYS", "THANK YOU"])
        self.assertEqual(item["last_message_update"], "2026-09-03T08:20:00+12:00")

    def test_travel_time_parser_keeps_minutes_without_inferring_congestion(self) -> None:
        item = module.parse_response(self.fixture["travel_times"], "tim", module.normalise_tim)[0]
        self.assertEqual(item["destinations"], [{"name": "CITY", "minutes": 12}, {"name": "AIRPORT", "minutes": 24}])
        self.assertIsNone(item["congestion_status"])
        self.assertFalse(item["source_provides_baseline"])
        self.assertEqual(item["last_updated_at"], "2026-09-03T08:22:00+12:00")

    def test_schema_drift_is_not_an_empty_success(self) -> None:
        with self.assertRaises(module.SchemaError):
            module.parse_response({"response": {}}, "camera", module.normalise_camera)

    def test_filter_is_case_insensitive_and_bounded(self) -> None:
        items = [
            {"id": 1, "region": "Wellington", "name": "SH1 Ngauranga", "description": "Northbound"},
            {"id": 2, "region": "Auckland", "name": "SH1 Central", "description": "Southbound"},
        ]
        self.assertEqual([x["id"] for x in module.filter_items(items, region="well", query="NGAU", limit=1)], [1])
        with self.assertRaises(module.InputError):
            module.filter_items(items, region=None, query=None, limit=0)


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=SKILL_DIR,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def test_help_lists_bounded_read_commands(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        for command in ("events", "travel-times", "cameras", "vms", "regions"):
            self.assertIn(command, result.stdout)

    def test_invalid_limit_exits_two_without_traceback(self) -> None:
        result = self.run_cli("events", "--limit", "0", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
