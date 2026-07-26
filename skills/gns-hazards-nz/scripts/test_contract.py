#!/usr/bin/env python3
"""Fixture-backed capability tests plus the repository skill contract."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, TextTestRunner, defaultTestLoader, mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = Path(__file__).with_name("cli.py")
FIXTURES = SKILL_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import run_contract_test  # noqa: E402


def load_cli():
    spec = importlib.util.spec_from_file_location("gns_hazards_contract_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CapabilityContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = load_cli()

    def capture_command(self, function, args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            function(args)
        return json.loads(stdout.getvalue())

    def capture_error(self, function):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            function()
        payload = json.loads(stderr.getvalue().strip().splitlines()[-1])
        return raised.exception.code, payload

    def test_cli_exposes_the_approved_commands(self):
        completed = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        for command in ("events", "versions", "event-files", "event-data", "describe"):
            with self.subTest(command=command):
                self.assertIn(command, completed.stdout)

    def test_source_licences_are_not_conflated(self):
        self.assertEqual(
            self.cli.ARCGIS_ATTRIBUTION,
            "CC BY 4.0 — attribute GNS Science",
        )
        self.assertEqual(
            self.cli.ARCHIVE_ATTRIBUTION,
            "CC BY 3.0 New Zealand — attribute GeoNet",
        )

    def test_negative_bbox_normalisation_and_bounds(self):
        self.assertEqual(
            self.cli.normalise_coordinate_options(
                ["faults", "--bbox", "-180,-90,180,90", "--json"]
            ),
            ["faults", "--bbox=-180,-90,180,90", "--json"],
        )
        params = self.cli.parse_bbox("-180,-90,180,90")
        self.assertEqual(params["geometry"], "-180.0,-90.0,180.0,90.0")
        for raw in (
            "nan,-41,175,-40",
            "174,-inf,175,-40",
            "-181,-41,175,-40",
            "174,-91,175,-40",
            "174,-41,181,-40",
            "174,-41,175,91",
        ):
            with self.subTest(raw=raw), self.assertRaises(SystemExit) as raised:
                self.cli.parse_bbox(raw)
            self.assertEqual(raised.exception.code, 2)

    def test_events_and_versions_preserve_source_identifiers(self):
        events = self.cli.normalise_events(
            fixture("events.json"),
            year=2026,
            source_url="https://shakinglayers.geonet.org.nz/api/v1/events?year=2026",
        )
        self.assertEqual(events["event_ids"], ["2026p359695", "771645"])
        self.assertEqual(events["event_count"], 2)
        self.assertEqual(events["year"], 2026)

        versions = self.cli.normalise_versions(
            fixture("versions.json"),
            requested_event_id="771645",
            source_url="https://shakinglayers.geonet.org.nz/api/v1/events/771645",
        )
        self.assertEqual(versions["event_id"], "771645")
        self.assertEqual(
            versions["versions"][0],
            {
                "versionpath": "2023-09-07T22:28:40-reviewed",
                "status": "published",
                "issue_time": "2023-09-07T22:28:40Z",
                "type": "reviewed",
            },
        )

    def test_event_files_resolve_latest_and_discover_measures(self):
        result = self.cli.normalise_event_files(
            fixture("event-files.json"),
            event_id="771645",
            requested_version="latest",
        )
        self.assertEqual(result["versionpath"], "2023-09-07T22:28:40-reviewed")
        self.assertEqual(result["requested_version"], "latest")
        self.assertEqual(
            result["source_url"],
            "https://shakinglayers.geonet.org.nz/api/v1/events/771645/"
            "2023-09-07T22%3A28%3A40-reviewed",
        )
        self.assertEqual(
            [row["measure"] for row in result["available_measures"]],
            ["mmi", "pga", "pgv", "psa0.3", "psa1.0", "psa3.0"],
        )
        self.assertEqual(result["available_measures"][0]["units"], "MMI")
        self.assertEqual(result["available_measures"][1]["units"], "g")
        self.assertEqual(result["available_measures"][2]["units"], "cm/s")
        self.assertTrue(
            all(
                row["source_url"].startswith(
                    "https://shakinglayers.geonet.org.nz/api/v1/events/771645/"
                    "2023-09-07T22%3A28%3A40-reviewed/"
                )
                for row in result["files"]
            )
        )

    def test_event_data_returns_geojson_with_units_and_provenance(self):
        responses = [
            (
                fixture("event-files.json"),
                "https://shakinglayers.geonet.org.nz/api/v1/events/771645/latest",
            ),
            (
                fixture("event-data-mmi.json"),
                "https://shakinglayers.geonet.org.nz/api/v1/events/771645/"
                "2023-09-07T22%3A28%3A40-reviewed/"
                "intensity_mmi_contour_lines.json",
            ),
        ]
        args = SimpleNamespace(
            event_id="771645", version="latest", measure="mmi", json=True
        )
        with mock.patch.object(self.cli, "fetch_json", side_effect=responses) as fetched:
            result = self.capture_command(self.cli.cmd_event_data, args)
        self.assertEqual(fetched.call_count, 2)
        self.assertEqual(
            fetched.call_args_list[1].args[0],
            "https://shakinglayers.geonet.org.nz/api/v1/events/771645/"
            "2023-09-07T22%3A28%3A40-reviewed/"
            "intensity_mmi_contour_lines.json",
        )
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(result["features"][0]["properties"]["value"], 5.0)
        self.assertEqual(result["provenance"]["event_id"], "771645")
        self.assertEqual(
            result["provenance"]["versionpath"],
            "2023-09-07T22:28:40-reviewed",
        )
        self.assertEqual(result["provenance"]["measure"], "mmi")
        self.assertEqual(result["provenance"]["units"], "MMI")
        self.assertEqual(
            result["provenance"]["file_name"],
            "intensity_mmi_contour_lines.json",
        )

    def test_unavailable_measure_reports_available_measures_and_files(self):
        args = SimpleNamespace(
            event_id="771645", version="latest", measure="sa", json=True
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(
                self.cli,
                "fetch_json",
                return_value=(
                    fixture("event-files.json"),
                    "https://shakinglayers.geonet.org.nz/api/v1/events/771645/latest",
                ),
            ),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            self.cli.cmd_event_data(args)
        self.assertEqual(raised.exception.code, 2)
        message = stderr.getvalue()
        self.assertIn("available measures", message)
        self.assertIn("intensity_mmi_contour_lines.json", message)

    def test_archive_path_and_host_validation(self):
        for event_id in ("../secret", "event/id", "", "x" * 81):
            with self.subTest(event_id=event_id), self.assertRaises(SystemExit):
                self.cli.validate_event_id(event_id)
        for version in ("../latest", "latest/extra", "https://evil.example"):
            with self.subTest(version=version), self.assertRaises(SystemExit):
                self.cli.validate_version(version)
        for file_name in ("../file.json", "folder/file.json", "https:evil.json"):
            with self.subTest(file_name=file_name), self.assertRaises(SystemExit):
                self.cli.validate_file_name(file_name)
        self.cli.validate_shakinglayers_url(
            "https://shakinglayers.geonet.org.nz/api/v1/events/771645/latest"
        )
        for url in (
            "http://shakinglayers.geonet.org.nz/api/v1/events",
            "https://shakinglayers.geonet.org.nz.evil.example/api/v1/events",
            "https://evil.example/api/v1/events",
            "https://user@shakinglayers.geonet.org.nz/api/v1/events",
        ):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                self.cli.validate_shakinglayers_url(url)

    def test_describe_normalises_arcgis_metadata(self):
        result = self.cli.normalise_description(
            fixture("layer-description.json"),
            service="faults",
            layer_id=0,
            layer_url="https://gis.gns.cri.nz/server/rest/services/"
            "Active_Faults/NZActiveFaultDatasets/MapServer/0",
            source_url="https://gis.gns.cri.nz/server/rest/services/"
            "Active_Faults/NZActiveFaultDatasets/MapServer/0?f=json",
        )
        self.assertEqual(result["geometry_type"], "esriGeometryPolyline")
        self.assertEqual(result["object_id_field"], "objectid")
        self.assertEqual(result["max_record_count"], 2000)
        self.assertEqual(result["fields"][1]["alias"], "Fault name")
        self.assertEqual(result["fields"][1]["description"], "Published fault name")
        self.assertEqual(result["extent"]["spatial_reference"]["wkid"], 4326)
        self.assertIn("Query", result["capabilities"])

    def test_arcgis_query_controls_map_to_rest_parameters(self):
        args = SimpleNamespace(
            where="status = 'active'",
            bbox="-180,-90,180,90",
            fields="OBJECTID,name",
            limit=25,
            count=False,
            ids_only=False,
            no_geometry=True,
            offset=10,
            order_by="name ASC",
            geometry_precision=4,
            max_allowable_offset=0.25,
        )
        params = self.cli.build_query_params(args)
        self.assertEqual(params["resultOffset"], 10)
        self.assertEqual(params["orderByFields"], "name ASC")
        self.assertEqual(params["geometryPrecision"], 4)
        self.assertEqual(params["maxAllowableOffset"], 0.25)
        self.assertEqual(params["returnGeometry"], "false")
        self.assertEqual(params["f"], "geojson")

        args.count = True
        count_params = self.cli.build_query_params(args)
        self.assertEqual(count_params["returnCountOnly"], "true")
        self.assertEqual(count_params["f"], "json")
        args.count = False
        args.ids_only = True
        ids_params = self.cli.build_query_params(args)
        self.assertEqual(ids_params["returnIdsOnly"], "true")
        self.assertEqual(ids_params["f"], "json")

    def test_arcgis_fields_and_order_by_reject_injection_syntax(self):
        parser = self.cli.build_parser()
        valid = parser.parse_args(
            [
                "faults",
                "--fields",
                "faults.name,OBJECTID",
                "--order-by",
                "faults.name DESC, OBJECTID ASC",
            ]
        )
        self.assertEqual(valid.fields, "faults.name,OBJECTID")
        self.assertEqual(valid.order_by, "faults.name DESC, OBJECTID ASC")
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                wildcard_fields = parser.parse_args(
                    ["faults", "--fields", "*"]
                ).fields
        except SystemExit:
            self.fail("the safe ArcGIS all-fields wildcard was rejected")
        self.assertEqual(wildcard_fields, "*")

        for fields in (
            "name;DROP TABLE faults",
            "faults.",
            ".name",
            "faults..name",
            "name DESC",
            "name,",
        ):
            with self.subTest(fields=fields):
                code, payload = self.capture_error(
                    lambda value=fields: parser.parse_args(
                        ["faults", "--fields", value]
                    )
                )
                self.assertEqual(code, 2)
                self.assertEqual(payload["error"].get("category"), "invalid_input")

        for order_by in (
            "name; DROP TABLE faults",
            "name DOWN",
            "COUNT(name) DESC",
            "faults..name ASC",
            "faults. DESC",
            "name DESC NULLS FIRST",
            "name,",
        ):
            with self.subTest(order_by=order_by):
                code, payload = self.capture_error(
                    lambda value=order_by: parser.parse_args(
                        ["faults", "--order-by", value]
                    )
                )
                self.assertEqual(code, 2)
                self.assertEqual(payload["error"].get("category"), "invalid_input")

    def test_fault_layer_id_is_bounded_before_network(self):
        parser = self.cli.build_parser()
        for layer_id in ("-1", "100001"):
            with self.subTest(layer_id=layer_id):
                code, payload = self.capture_error(
                    lambda value=layer_id: parser.parse_args(
                        ["faults", "--layer-id", value]
                    )
                )
                self.assertEqual(code, 2)
                self.assertEqual(payload["error"].get("category"), "invalid_input")

    def test_feature_query_rejects_non_list_features(self):
        args = SimpleNamespace(
            where=None,
            bbox=None,
            fields=None,
            limit=50,
            count=False,
            ids_only=False,
            no_geometry=False,
            offset=None,
            order_by=None,
            geometry_precision=None,
            max_allowable_offset=None,
        )
        with mock.patch.object(
            self.cli,
            "fetch_json",
            return_value=({"type": "FeatureCollection", "features": {}}, "https://example.invalid/query"),
        ):
            code, payload = self.capture_error(
                lambda: self.cli.query_layer("https://example.invalid/0", args)
            )
        self.assertEqual(code, 6)
        self.assertEqual(payload["error"].get("category"), "source_schema")

    def test_feature_query_rejects_malformed_feature_and_properties(self):
        args = SimpleNamespace(
            where=None,
            bbox=None,
            fields=None,
            limit=50,
            count=False,
            ids_only=False,
            no_geometry=False,
            offset=None,
            order_by=None,
            geometry_precision=None,
            max_allowable_offset=None,
        )
        malformed = (
            {"type": "FeatureCollection", "features": ["not-an-object"]},
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": ["not-an-object"]}],
            },
        )
        for response in malformed:
            with self.subTest(response=response), mock.patch.object(
                self.cli,
                "fetch_json",
                return_value=(response, "https://example.invalid/query"),
            ):
                code, payload = self.capture_error(
                    lambda: self.cli.query_layer("https://example.invalid/0", args)
                )
                self.assertEqual(code, 6)
                self.assertEqual(payload["error"].get("category"), "source_schema")

    def test_archive_http_404_is_structured_not_found(self):
        cases = (
            (self.cli.archive_url("events", "missing-event"), "event not found"),
            (
                self.cli.archive_url("events", "event-id", "missing-version"),
                "event version not found",
            ),
            (
                self.cli.archive_url(
                    "events", "event-id", "version-id", "missing-file.json"
                ),
                "event file not found",
            ),
        )
        for url, wording in cases:
            with self.subTest(url=url):
                cause = urllib.error.HTTPError(url, 404, "Not Found", {}, None)
                failure = self.cli.nzfetch.FetchError(f"HTTP 404 from {url}")
                failure.__cause__ = cause
                with mock.patch.object(
                    self.cli.nzfetch, "fetch_bytes", side_effect=failure
                ):
                    code, payload = self.capture_error(
                        lambda target=url: self.cli.fetch_json(target)
                    )
                self.assertEqual(code, 5)
                self.assertEqual(payload["error"].get("category"), "not_found")
                self.assertIn(wording, payload["error"]["message"].lower())
                self.assertNotIn("ArcGIS", payload["error"]["message"])

    def test_archive_api_error_is_not_labelled_arcgis(self):
        url = self.cli.archive_url("events", "missing-event")
        body = json.dumps({"error": {"message": "Event not found"}}).encode()
        with mock.patch.object(
            self.cli.nzfetch,
            "fetch_bytes",
            return_value=(body, "application/json", url),
        ):
            code, payload = self.capture_error(lambda: self.cli.fetch_json(url))
        self.assertEqual(code, 5)
        self.assertEqual(payload["error"].get("category"), "not_found")
        self.assertIn("GeoNet ShakingLayers", payload["error"]["message"])
        self.assertNotIn("ArcGIS", payload["error"]["message"])

    def test_archive_final_redirect_url_is_revalidated(self):
        requested = self.cli.archive_url("events")
        with mock.patch.object(
            self.cli.nzfetch,
            "fetch_bytes",
            return_value=(
                b"[]",
                "application/json",
                "https://evil.example/api/v1/events",
            ),
        ):
            code, payload = self.capture_error(
                lambda: self.cli.fetch_json(requested)
            )
        self.assertEqual(code, 7)
        self.assertEqual(payload["error"].get("category"), "unsafe_source")

    def test_archive_malformed_json_is_source_schema_error(self):
        url = self.cli.archive_url("events")
        with mock.patch.object(
            self.cli.nzfetch,
            "fetch_bytes",
            return_value=(b"not-json", "application/json", url),
        ):
            code, payload = self.capture_error(lambda: self.cli.fetch_json(url))
        self.assertEqual(code, 6)
        self.assertEqual(payload["error"].get("category"), "source_schema")
        self.assertIn("malformed JSON", payload["error"]["message"])

    def test_describe_requires_credible_layer_metadata(self):
        weak_payloads = (
            {"name": "Layer", "geometryType": "esriGeometryPoint", "fields": []},
            {
                "fields": [
                    {
                        "name": "OBJECTID",
                        "alias": "OBJECTID",
                        "type": "esriFieldTypeOID",
                    }
                ]
            },
        )
        for data in weak_payloads:
            with self.subTest(data=data):
                code, payload = self.capture_error(
                    lambda value=data: self.cli.normalise_description(
                        value,
                        service="faults",
                        layer_id=0,
                        layer_url=self.cli.FAULTS_SERVICE + "/0",
                        source_url=self.cli.FAULTS_SERVICE + "/0?f=json",
                    )
                )
                self.assertEqual(code, 6)
                self.assertEqual(payload["error"].get("category"), "source_schema")

    def test_count_and_ids_query_envelopes_and_mutual_exclusion(self):
        args = SimpleNamespace(
            where=None,
            bbox=None,
            fields=None,
            limit=50,
            count=True,
            ids_only=False,
            no_geometry=False,
            offset=None,
            order_by=None,
            geometry_precision=None,
            max_allowable_offset=None,
        )
        with mock.patch.object(
            self.cli,
            "fetch_json",
            return_value=(fixture("count.json"), "https://example.invalid/query"),
        ):
            result, _ = self.cli.query_layer("https://example.invalid/0", args)
        self.assertEqual(result, {"mode": "count", "count": 42})

        args.count = False
        args.ids_only = True
        with mock.patch.object(
            self.cli,
            "fetch_json",
            return_value=(fixture("ids.json"), "https://example.invalid/query"),
        ):
            result, _ = self.cli.query_layer("https://example.invalid/0", args)
        self.assertEqual(
            result,
            {
                "mode": "ids",
                "object_id_field": "OBJECTID",
                "object_ids": [9, 3],
            },
        )

        parser = self.cli.build_parser()
        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(["faults", "--count", "--ids-only"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    suite = defaultTestLoader.loadTestsFromTestCase(CapabilityContractTests)
    result = TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    raise SystemExit(run_contract_test(SKILL_ROOT))
