#!/usr/bin/env python3
"""Deterministic parser and CLI tests written before implementation."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

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
        item = module.parse_response(
            self.fixture["events"], "roadevent", module.normalise_event
        )[0]
        self.assertEqual(item["id"], 9001)
        self.assertEqual(item["highway"], "SH1")
        self.assertEqual(item["region"], "Wellington")
        self.assertEqual(item["last_updated_at"], "2026-09-03T08:15:00+12:00")
        self.assertFalse(item["planned"])

    def test_camera_parser_builds_official_urls_and_status(self) -> None:
        item = module.parse_response(
            self.fixture["cameras"], "camera", module.normalise_camera
        )[0]
        self.assertEqual(item["status"], "maintenance")
        self.assertEqual(item["image_url"], "https://trafficnz.info/camera/7001.jpg")
        self.assertEqual(
            item["thumbnail_url"], "https://trafficnz.info/camera/thumb/7001.jpg"
        )

    def test_vms_parser_splits_message_pages(self) -> None:
        item = module.parse_response(self.fixture["vms"], "vms", module.normalise_vms)[
            0
        ]
        self.assertEqual(
            item["message_lines"], ["ROAD WORKS", "EXPECT DELAYS", "THANK YOU"]
        )
        self.assertEqual(item["last_message_update"], "2026-09-03T08:20:00+12:00")

    def test_travel_time_parser_keeps_minutes_without_inferring_congestion(
        self,
    ) -> None:
        item = module.parse_response(
            self.fixture["travel_times"], "tim", module.normalise_tim
        )[0]
        self.assertEqual(
            item["destinations"],
            [{"name": "CITY", "minutes": 12}, {"name": "AIRPORT", "minutes": 24}],
        )
        self.assertIsNone(item["congestion_status"])
        self.assertFalse(item["source_provides_baseline"])
        self.assertEqual(item["last_updated_at"], "2026-09-03T08:22:00+12:00")

    def test_schema_drift_is_not_an_empty_success(self) -> None:
        with self.assertRaises(module.SchemaError):
            module.parse_response({"response": {}}, "camera", module.normalise_camera)

    def test_null_collection_is_schema_error(self) -> None:
        with self.assertRaises(module.SchemaError):
            module.parse_response(
                {"response": {"camera": None}}, "camera", module.normalise_camera
            )

    def test_wrong_type_collection_is_schema_error(self) -> None:
        with self.assertRaises(module.SchemaError):
            module.parse_response(
                {"response": {"camera": {}}}, "camera", module.normalise_camera
            )

    def test_empty_collection_is_preserved(self) -> None:
        self.assertEqual(
            module.parse_response(
                {"response": {"camera": []}}, "camera", module.normalise_camera
            ),
            [],
        )

    def test_non_finite_number_at_ignored_nested_depth_is_schema_error(self) -> None:
        payload = {"response": {"camera": []}, "metadata": {"ignored": [float("nan")]}}
        with self.assertRaises(module.SchemaError):
            module.parse_response(payload, "camera", module.normalise_camera)

    def test_required_item_ids_reject_non_identifier_values(self) -> None:
        normalisers = (
            module.normalise_event,
            module.normalise_camera,
            module.normalise_vms,
            module.normalise_tim,
        )
        for normaliser in normalisers:
            for invalid_id in ({"nested": 1}, [1], True, 1.5, "  "):
                with (
                    self.subTest(normaliser=normaliser.__name__, invalid_id=invalid_id),
                    self.assertRaises(module.SchemaError),
                ):
                    normaliser({"id": invalid_id})

    def test_camera_operational_flags_are_required_booleans(self) -> None:
        valid = {"id": 1, "offline": False, "underMaintenance": False}
        for field in ("offline", "underMaintenance"):
            missing = dict(valid)
            missing.pop(field)
            with (
                self.subTest(field=field, state="missing"),
                self.assertRaises(module.SchemaError),
            ):
                module.normalise_camera(missing)
            malformed = {**valid, field: {"not": "boolean"}}
            with (
                self.subTest(field=field, state="malformed"),
                self.assertRaises(module.SchemaError),
            ):
                module.normalise_camera(malformed)

    def test_tim_enabled_is_a_required_boolean(self) -> None:
        for item in ({"id": 1}, {"id": 1, "enabled": [False]}):
            with self.subTest(item=item), self.assertRaises(module.SchemaError):
                module.normalise_tim(item)

    def test_filter_is_case_insensitive_and_bounded(self) -> None:
        items = [
            {
                "id": 1,
                "region": "Wellington",
                "name": "SH1 Ngauranga",
                "description": "Northbound",
            },
            {
                "id": 2,
                "region": "Auckland",
                "name": "SH1 Central",
                "description": "Southbound",
            },
        ]
        self.assertEqual(
            [
                x["id"]
                for x in module.filter_items(
                    items, region="well", query="NGAU", limit=1
                )
            ],
            [1],
        )
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

    def run_cli_with_read_failure(
        self, exception_name: str
    ) -> subprocess.CompletedProcess[str]:
        script = f"""
import importlib.util
import sys
from http.client import IncompleteRead

spec = importlib.util.spec_from_file_location("nzta_cli_subprocess", {str(CLI)!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

class FakeResponse:
    headers = {{}}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size):
        if {exception_name!r} == "reset":
            raise ConnectionResetError("connection reset by peer")
        raise IncompleteRead(b'{{"response":', 20)

class FakeOpener:
    def open(self, request, timeout):
        return FakeResponse()

module.build_opener = lambda *handlers: FakeOpener()
raise SystemExit(module.main(["cameras", "--json"]))
"""
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=SKILL_DIR,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def assert_json_error(
        self, result: subprocess.CompletedProcess[str], expected_code: int
    ) -> None:
        self.assertEqual(result.returncode, expected_code)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], expected_code)
        self.assertIsInstance(payload["source"], dict)
        self.assertIsInstance(payload["query"], dict)
        self.assertNotIn("Traceback", result.stderr + result.stdout)

    def assert_in_process_source_schema_error(
        self, command: str, source_payload: dict[str, Any]
    ) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(module, "fetch_json", return_value=source_payload),
            redirect_stdout(stdout),
        ):
            exit_code = module.main([command, "--json"])
        self.assertEqual(exit_code, 6)
        payload = self.strict_json_loads(stdout.getvalue())
        error = payload["error"]
        self.assertIsInstance(error, dict)
        self.assertEqual(error["code"], 6)
        self.assertEqual(error["category"], "source_schema")

    def strict_json_loads(self, text: str) -> dict[str, Any]:
        def reject_constant(value: str) -> None:
            raise ValueError(f"non-standard JSON constant: {value}")

        return json.loads(text, parse_constant=reject_constant)

    def test_help_lists_bounded_read_commands(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        for command in ("events", "travel-times", "cameras", "vms", "regions"):
            self.assertIn(command, result.stdout)

    def test_invalid_limit_exits_two_without_traceback(self) -> None:
        result = self.run_cli("events", "--limit", "0", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_invalid_integer_emits_json_error_envelope(self) -> None:
        result = self.run_cli("cameras", "--limit", "not-an-integer", "--json")
        self.assert_json_error(result, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "cameras")
        self.assertEqual(payload["source"]["url"], module.API_ROOT + "cameras/all")
        self.assertIsNone(payload["query"]["limit"])

    def test_connection_reset_during_read_emits_upstream_json_error(self) -> None:
        self.assert_json_error(self.run_cli_with_read_failure("reset"), 5)

    def test_incomplete_read_emits_upstream_json_error(self) -> None:
        self.assert_json_error(self.run_cli_with_read_failure("incomplete"), 5)

    def test_non_finite_normalised_output_emits_schema_error_as_standard_json(
        self,
    ) -> None:
        success_payload = {
            "schema_version": "1",
            "ok": True,
            "kind": "cameras",
            "source": {},
            "query": {},
            "data": [{"latitude": float("nan")}],
            "warnings": [],
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(module, "execute", return_value=success_payload),
            redirect_stdout(stdout),
        ):
            exit_code = module.main(["cameras", "--json"])
        self.assertEqual(exit_code, 6)
        payload = self.strict_json_loads(stdout.getvalue())
        self.assertIsInstance(payload, dict)
        error = payload["error"]
        self.assertIsInstance(error, dict)
        self.assertEqual(error["code"], 6)
        self.assertEqual(error["category"], "source_schema")

    def test_malformed_source_items_emit_structured_source_schema_exit(self) -> None:
        cases = (
            ("events", {"response": {"roadevent": [{"id": {"nested": 1}}]}}),
            (
                "cameras",
                {"response": {"camera": [{"id": 1, "underMaintenance": False}]}},
            ),
            ("travel-times", {"response": {"tim": [{"id": 1, "enabled": [False]}]}}),
        )
        for command, source_payload in cases:
            with self.subTest(command=command):
                self.assert_in_process_source_schema_error(command, source_payload)

    def test_success_output_is_strict_standard_json(self) -> None:
        success_payload = {
            "schema_version": "1",
            "ok": True,
            "kind": "cameras",
            "source": {"retrieved_at": "2026-09-03T00:00:00Z"},
            "query": {},
            "data": [{"latitude": -41.0}],
            "warnings": [],
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(module, "execute", return_value=success_payload),
            redirect_stdout(stdout),
        ):
            exit_code = module.main(["cameras", "--json"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(self.strict_json_loads(stdout.getvalue()), success_payload)


class NetworkBoundaryTests(unittest.TestCase):
    def test_non_standard_json_constants_are_rejected_at_every_depth(self) -> None:
        class FakeResponse:
            def __init__(self, body: bytes) -> None:
                self.body = body
                self.headers: dict[str, str] = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, size):
                return self.body

        for constant in (b"NaN", b"Infinity", b"-Infinity"):
            body = b'{"response":{"camera":[]},"metadata":{"deep":[' + constant + b"]}}"
            opener = mock.Mock()
            opener.open.return_value = FakeResponse(body)
            with (
                self.subTest(constant=constant),
                mock.patch.object(module, "build_opener", return_value=opener),
                self.assertRaises(module.SchemaError),
            ):
                module.fetch_json(module.API_ROOT + "cameras/all")

    def test_blocked_http_status_remains_distinct(self) -> None:
        opener = mock.Mock()
        opener.open.side_effect = module.HTTPError(
            module.API_ROOT, 403, "Forbidden", {}, None
        )
        with (
            mock.patch.object(module, "build_opener", return_value=opener),
            self.assertRaises(module.BlockedError),
        ):
            module.fetch_json(module.API_ROOT + "cameras/all")

    def test_other_http_status_remains_upstream_error(self) -> None:
        opener = mock.Mock()
        opener.open.side_effect = module.HTTPError(
            module.API_ROOT, 503, "Unavailable", {}, None
        )
        with (
            mock.patch.object(module, "build_opener", return_value=opener),
            self.assertRaises(module.UpstreamError),
        ):
            module.fetch_json(module.API_ROOT + "cameras/all")

    def test_off_host_redirect_is_rejected_before_follow_up(self) -> None:
        foreign_contacted = False

        class RedirectingOpener:
            def open(self, request, timeout):
                handler = module.NZTARedirectHandler()
                handler.redirect_request(
                    request,
                    None,
                    302,
                    "Found",
                    {},
                    "https://attacker.example/foreign.json",
                )
                nonlocal foreign_contacted
                foreign_contacted = True

        with (
            mock.patch.object(module, "build_opener", return_value=RedirectingOpener()),
            self.assertRaises(module.SchemaError),
        ):
            module.fetch_json(module.API_ROOT + "cameras/all")
        self.assertFalse(foreign_contacted)

    def test_malformed_content_length_is_schema_error(self) -> None:
        class FakeResponse:
            def __init__(self) -> None:
                self.headers = {"Content-Length": "not-a-number"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, size):
                return b'{"response":{"camera":[]}}'

        opener = mock.Mock()
        opener.open.return_value = FakeResponse()
        with (
            mock.patch.object(module, "build_opener", return_value=opener),
            self.assertRaises(module.SchemaError),
        ):
            module.fetch_json(module.API_ROOT + "cameras/all")


if __name__ == "__main__":
    unittest.main(verbosity=2)
