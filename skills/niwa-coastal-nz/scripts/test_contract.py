#!/usr/bin/env python3
"""Fixture-backed capability tests plus the shared repository contract."""
from __future__ import annotations

import contextlib
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

from contract_test import run_contract_test  # noqa: E402


def load_cli():
    path = Path(__file__).with_name("cli.py")
    spec = importlib.util.spec_from_file_location("niwa_coastal_contract_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CapabilityContractTests(unittest.TestCase):
    def invoke(self, argv: list[str], fake_fetch):
        stdout = io.StringIO()
        with (
            mock.patch.object(CLI, "fetch_json", side_effect=fake_fetch),
            contextlib.redirect_stdout(stdout),
        ):
            CLI.main(argv)
        return json.loads(stdout.getvalue()), ""

    def assert_rejected(self, fn, code: int = 2):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        payload = json.loads(stderr.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["exit_code"], code)

    def test_search_maps_start_and_preserves_next_cursor(self):
        calls = []

        def fake_fetch(url, params=None):
            calls.append((url, params))
            return fixture("search-page.json"), "https://www.arcgis.com/synthetic-search"

        payload, _ = self.invoke(
            ["search", "coastal", "--limit", "2", "--start", "11", "--json"],
            fake_fetch,
        )
        self.assertEqual(calls[0][1]["start"], 11)
        self.assertEqual(payload["start"], 11)
        self.assertEqual(payload["next_start"], 13)
        self.assertEqual(payload["items"][0]["organisation"], CLI.NIWA_ORG_ID)

    def test_search_rejects_foreign_organisation_result(self):
        data = fixture("search-page.json")
        data["results"][0]["orgId"] = "foreign-org"

        def fake_fetch(url, params=None):
            return data, "https://www.arcgis.com/synthetic-search"

        self.assert_rejected(
            lambda: self.invoke(["search", "coastal", "--json"], fake_fetch),
            7,
        )

    def test_search_verifies_rows_when_arcgis_omits_org_id(self):
        data = fixture("search-page.json")
        missing = data["results"][1]
        missing.pop("orgId")
        verified = dict(missing, orgId=CLI.NIWA_ORG_ID, size=42)
        calls = []

        def fake_fetch(url, params=None):
            calls.append(url)
            if "/content/items/" in url:
                return verified, url + "?f=json"
            return data, "https://www.arcgis.com/synthetic-search"

        payload, _ = self.invoke(["search", "coastal", "--json"], fake_fetch)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1].endswith("/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))
        self.assertEqual(payload["items"][1]["organisation"], CLI.NIWA_ORG_ID)

    def test_item_normalises_catalogue_metadata(self):
        calls = []

        def fake_fetch(url, params=None):
            calls.append((url, params))
            return fixture("item.json"), url + "?f=json"

        payload, _ = self.invoke(
            ["item", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--json"],
            fake_fetch,
        )
        self.assertTrue(calls[0][0].endswith("/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        self.assertEqual(
            set(payload["item"]),
            {
                "id",
                "title",
                "type",
                "owner",
                "organisation",
                "access",
                "licence",
                "description",
                "tags",
                "created_epoch_ms",
                "modified_epoch_ms",
                "size_bytes",
                "url",
                "service_url",
            },
        )
        self.assertEqual(payload["item"]["licence"], "CC BY 4.0")
        self.assertEqual(payload["item"]["size_bytes"], 3210)
        self.assertEqual(payload["item"]["url"], payload["item"]["service_url"])

    def test_item_returns_non_service_catalogue_url_without_service_validation(self):
        item = fixture("web-map-item.json")

        def fake_fetch(url, params=None):
            return item, url + "?f=json"

        payload, _ = self.invoke(["item", item["id"], "--json"], fake_fetch)
        self.assertEqual(payload["item"]["type"], "Web Map")
        self.assertEqual(payload["item"]["url"], item["url"])
        self.assertIsNone(payload["item"]["service_url"])

    def test_item_rejects_invalid_id_foreign_org_and_host(self):
        self.assert_rejected(
            lambda: self.invoke(["item", "../bad", "--json"], lambda *_: self.fail("network called")),
            2,
        )
        foreign = fixture("item.json")
        foreign["orgId"] = "foreign"
        self.assert_rejected(
            lambda: self.invoke(["item", foreign["id"], "--json"], lambda url, params=None: (foreign, url)),
            7,
        )
        hostile = fixture("item.json")
        hostile["url"] = "https://evil.example/arcgis/rest/services/Coast/MapServer"
        self.assert_rejected(
            lambda: self.invoke(["item", hostile["id"], "--json"], lambda url, params=None: (hostile, url)),
            7,
        )

    def test_describe_service_and_selected_layer(self):
        service = fixture("service.json")
        layer = fixture("layer.json")

        def fake_fetch(url, params=None):
            if url.endswith("/3"):
                return layer, url + "?f=json"
            return service, url + "?f=json"

        base = "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer"
        payload, _ = self.invoke(["describe", base, "--json"], fake_fetch)
        self.assertEqual(payload["description"]["max_record_count"], 2000)
        self.assertEqual(payload["description"]["layers"][0]["id"], 3)
        payload, _ = self.invoke(
            ["describe", base, "--layer-id", "3", "--json"],
            fake_fetch,
        )
        description = payload["description"]
        self.assertEqual(description["object_id_field"], "OBJECTID")
        self.assertEqual(description["geometry_type"], "esriGeometryPolyline")
        self.assertEqual(description["fields"][1]["alias"], "Exposure class")
        self.assertEqual(description["fields"][1]["unit"], "class")
        self.assertEqual(description["spatial_reference"]["wkid"], 2193)

    def test_describe_rejects_implausible_empty_metadata(self):
        base = "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer"
        self.assert_rejected(
            lambda: self.invoke(
                ["describe", base, "--json"],
                lambda url, params=None: ({}, url + "?f=json"),
            ),
            6,
        )

    def test_query_shared_controls_map_to_arcgis_and_normalise_modes(self):
        base = "https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/Synthetic/FeatureServer/0"
        calls = []

        def fake_count(url, params=None):
            calls.append((url, params))
            return {"count": 17}, url + "?synthetic"

        payload, _ = self.invoke(
            [
                "query",
                base,
                "--count",
                "--no-geometry",
                "--offset",
                "5",
                "--order-by",
                "OBJECTID DESC",
                "--geometry-precision",
                "4",
                "--max-allowable-offset",
                "0.25",
                "--json",
            ],
            fake_count,
        )
        params = calls[0][1]
        self.assertEqual(payload["kind"], "query-count")
        self.assertEqual(payload["count"], 17)
        self.assertEqual(params["returnCountOnly"], "true")
        self.assertEqual(params["returnGeometry"], "false")
        self.assertEqual(params["resultOffset"], 5)
        self.assertEqual(params["orderByFields"], "OBJECTID DESC")
        self.assertEqual(params["geometryPrecision"], 4)
        self.assertEqual(params["maxAllowableOffset"], 0.25)
        self.assertEqual(params["f"], "json")

        def fake_ids(url, params=None):
            return fixture("query-ids.json"), url + "?synthetic"

        payload, _ = self.invoke(["query", base, "--ids-only", "--json"], fake_ids)
        self.assertEqual(payload["kind"], "query-ids")
        self.assertEqual(payload["object_id_field"], "OBJECTID")
        self.assertEqual(payload["object_ids"], [2, 5, 9])

    def test_query_keeps_geojson_output_shape(self):
        base = "https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/Synthetic/FeatureServer/0"

        def fake_fetch(url, params=None):
            self.assertEqual(params["f"], "geojson")
            return fixture("query-geojson.json"), url + "?synthetic"

        payload, _ = self.invoke(["query", base, "--limit", "2", "--json"], fake_fetch)
        self.assertEqual(payload["kind"], "query")
        self.assertEqual(payload["feature_count"], 2)
        self.assertEqual(payload["features"][0]["type"], "Feature")

    def test_count_and_ids_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            with contextlib.redirect_stderr(io.StringIO()):
                CLI.parse_args(["query", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--count", "--ids-only"])
        self.assertEqual(caught.exception.code, 2)

    def test_all_argument_parser_failures_use_structured_error_envelope(self):
        cases = (
            ["--unknown-option"],
            ["search", "coastal", "--limit", "not-an-int"],
            [
                "query",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "--count",
                "--ids-only",
            ],
        )
        for argv in cases:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                CLI.parse_args(argv)
            self.assertEqual(caught.exception.code, 2)
            payload = json.loads(stderr.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["category"], "invalid_input")
            self.assertEqual(payload["error"]["exit_code"], 2)

    def test_query_rejects_malformed_field_identifiers_before_network(self):
        for arguments in (
            ["--fields", "OBJECTID,bad field"],
            ["--fields", "OBJECTID..x"],
            ["--fields", "OBJECTID."],
            ["--order-by", "OBJECTID; DROP TABLE coast"],
            ["--order-by", "OBJECTID..x DESC"],
            ["--order-by", "OBJECTID. DESC"],
        ):
            with self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stderr(io.StringIO()):
                    CLI.parse_args(
                        ["query", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", *arguments]
                    )
            self.assertEqual(caught.exception.code, 2)

    def test_identify_builds_wgs84_request_and_accepts_negative_leading_point(self):
        base = "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer"
        for point_args in (["--point", "-41.29,74.78"], ["--point=-41.29,74.78"]):
            calls = []

            def fake_fetch(url, params=None):
                calls.append((url, params))
                return fixture("identify.json"), url + "?synthetic"

            payload, _ = self.invoke(
                [
                    "identify",
                    base,
                    *point_args,
                    "--layer-id",
                    "3",
                    "--tolerance",
                    "7",
                    "--no-geometry",
                    "--json",
                ],
                fake_fetch,
            )
            self.assertTrue(calls[0][0].endswith("/identify"))
            params = calls[0][1]
            self.assertEqual(json.loads(params["geometry"]), {"x": -41.29, "y": 74.78, "spatialReference": {"wkid": 4326}})
            self.assertEqual(params["layers"], "all:3")
            self.assertEqual(params["tolerance"], 7)
            self.assertEqual(params["returnGeometry"], "false")
            self.assertEqual(params["sr"], "4326")
            self.assertEqual(payload["kind"], "identify")
            self.assertEqual(payload["result_count"], 1)

    def test_point_and_bbox_reject_non_finite_and_out_of_range_values(self):
        for raw in ("NaN,0", "0,inf", "-181,0", "181,0", "0,-91", "0,91"):
            self.assert_rejected(lambda raw=raw: CLI.parse_point(raw), 2)
        for raw in (
            "NaN,-40,175,-39",
            "-181,-40,175,-39",
            "170,-91,175,-39",
            "175,-40,170,-39",
        ):
            self.assert_rejected(lambda raw=raw: CLI.parse_bbox(raw), 2)

    def test_service_path_and_redirect_validation(self):
        accepted = (
            "https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/Synthetic/FeatureServer",
            "https://services.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/Synthetic/MapServer/3",
            "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer",
        )
        for url in accepted:
            CLI.check_layer_host(url)
        rejected = (
            "https://services3.arcgis.com/fp1tibNcN9mbExhG/not/rest/Synthetic/FeatureServer",
            "https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/Synthetic/MapServer/3/extra",
            "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/ImageServer",
            "https://gis.niwa.co.nz/server/rest/services/COAST/%2e%2e/Admin/MapServer",
            "https://gis.niwa.co.nz/server/rest/services/COAST/%252e%252e/Admin/MapServer",
            "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic%25Name/MapServer",
            "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic%252fNested/MapServer",
            "https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer?token=no",
        )
        for url in rejected:
            self.assert_rejected(lambda url=url: CLI.check_layer_host(url), 7)

        body = json.dumps({"layers": []}).encode()
        with mock.patch.object(
            CLI.nzfetch,
            "fetch_bytes",
            return_value=(
                body,
                "application/json",
                "https://services3.arcgis.com/OTHERORG/arcgis/rest/services/X/MapServer",
            ),
        ):
            self.assert_rejected(
                lambda: CLI.fetch_json(
                    "https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/X/MapServer",
                    {"f": "json"},
                ),
                7,
            )

    def test_skill_documents_source_native_capabilities_and_limits(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        notes = (SKILL_DIR / "references" / "source-notes.md").read_text(encoding="utf-8")
        for marker in (
            "item ITEM_ID",
            "describe SERVICE",
            "identify SERVICE",
            "--start",
            "--count",
            "--ids-only",
            "--no-geometry",
            "--offset",
            "--order-by",
            "--geometry-precision",
            "--max-allowable-offset",
            "raw MapServer identify",
        ):
            self.assertIn(marker, skill)
        self.assertIn("next_start", skill)
        self.assertIn("not a hazard assessment", skill)
        self.assertIn("174.78,-41.29", skill)
        self.assertNotIn("--point -41.29,74.78", skill)
        self.assertIn("WGS84", notes)
        self.assertIn("redirect", notes.lower())


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CapabilityContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    return run_contract_test(SKILL_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
