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
    spec = importlib.util.spec_from_file_location("wcc_arcgis_contract_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CapabilityContractTests(unittest.TestCase):
    def setUp(self):
        missing = [
            name
            for name in ("parse_args", "parse_point")
            if not hasattr(CLI, name)
        ]
        self.assertEqual(
            missing,
            [],
            f"required capability entrypoints are not implemented: {', '.join(missing)}",
        )

    def invoke(self, argv: list[str], fake_fetch):
        stdout = io.StringIO()
        with (
            mock.patch.object(CLI, "fetch_json", side_effect=fake_fetch),
            contextlib.redirect_stdout(stdout),
        ):
            CLI.main(argv)
        return json.loads(stdout.getvalue())

    def assert_rejected(self, fn, code: int = 2, category: str | None = None):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        payload = json.loads(stderr.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["exit_code"], code)
        if category:
            self.assertEqual(payload["error"]["category"], category)

    def test_search_maps_start_and_preserves_next_cursor(self):
        calls = []

        def fake_fetch(url, params=None):
            calls.append((url, params))
            return fixture("search-page.json"), "https://www.arcgis.com/synthetic-search"

        payload = self.invoke(
            ["search", "flood", "--limit", "2", "--start", "11", "--json"],
            fake_fetch,
        )
        self.assertEqual(calls[0][1]["start"], 11)
        self.assertEqual(payload["start"], 11)
        self.assertEqual(payload["next_start"], 13)
        self.assertEqual(payload["items"][0]["organisation"], CLI.PORTALS["wcc"]["org_id"])

    def test_search_rejects_foreign_org_and_verifies_omitted_org(self):
        foreign = fixture("search-page.json")
        foreign["results"][0]["orgId"] = "foreign-org"
        self.assert_rejected(
            lambda: self.invoke(
                ["search", "flood", "--json"],
                lambda url, params=None: (foreign, url),
            ),
            7,
            "blocked_organisation",
        )

        missing = fixture("search-page.json")
        missing["results"][1].pop("orgId")
        verified = dict(
            missing["results"][1],
            orgId=CLI.PORTALS["wcc"]["org_id"],
        )
        calls = []

        def fake_fetch(url, params=None):
            calls.append(url)
            if "/content/items/" in url:
                return verified, url + "?f=json"
            return missing, "https://www.arcgis.com/synthetic-search"

        payload = self.invoke(["search", "flood", "--json"], fake_fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(payload["items"][1]["organisation"], CLI.PORTALS["wcc"]["org_id"])

    def test_item_normalises_catalogue_metadata_and_accepts_both_councils(self):
        for name, org_id in (
            ("item-wcc.json", CLI.PORTALS["wcc"]["org_id"]),
            ("item-gwrc.json", CLI.PORTALS["gwrc"]["org_id"]),
        ):
            data = fixture(name)
            self.assertEqual(data["orgId"], org_id)
            payload = self.invoke(
                ["item", data["id"], "--json"],
                lambda url, params=None, data=data: (data, url + "?f=json"),
            )
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
            self.assertTrue(payload["item"]["owner"].startswith("synthetic_"))
            self.assertEqual(payload["item"]["licence"], "CC BY 4.0")
            self.assertEqual(payload["item"]["url"], payload["item"]["service_url"])

    def test_item_preserves_owned_non_service_url_without_service_validation(self):
        item = fixture("item-web-map.json")
        try:
            payload = self.invoke(
                ["item", item["id"], "--json"],
                lambda url, params=None: (item, url + "?f=json"),
            )
        except SystemExit as exc:
            self.fail(f"owned non-service item must not be rejected (exit {exc.code})")
        self.assertEqual(payload["item"]["type"], "Web Mapping Application")
        self.assertEqual(payload["item"]["url"], item["url"])
        self.assertIsNone(payload["item"]["service_url"])

    def test_item_rejects_invalid_id_foreign_org_and_host(self):
        self.assert_rejected(
            lambda: self.invoke(
                ["item", "../bad", "--json"],
                lambda *_: self.fail("network called"),
            ),
            2,
            "invalid_input",
        )
        foreign = fixture("item-wcc.json")
        foreign["orgId"] = "foreign"
        self.assert_rejected(
            lambda: self.invoke(
                ["item", foreign["id"], "--json"],
                lambda url, params=None: (foreign, url),
            ),
            7,
            "blocked_organisation",
        )
        hostile = fixture("item-wcc.json")
        hostile["url"] = "https://evil.example/arcgis/rest/services/Hazard/MapServer"
        self.assert_rejected(
            lambda: self.invoke(
                ["item", hostile["id"], "--json"],
                lambda url, params=None: (hostile, url),
            ),
            7,
            "blocked_host",
        )

    def test_describe_service_and_selected_layer(self):
        service = fixture("service-metadata.json")
        layer = fixture("layer-metadata.json")

        def fake_fetch(url, params=None):
            return (layer if url.endswith("/10") else service), url + "?f=json"

        base = "https://mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer"
        payload = self.invoke(["describe", base, "--json"], fake_fetch)
        self.assertEqual(payload["description"]["max_record_count"], 2000)
        self.assertEqual(payload["description"]["layers"][0]["id"], 10)
        payload = self.invoke(
            ["describe", base, "--layer-id", "10", "--json"],
            fake_fetch,
        )
        description = payload["description"]
        self.assertEqual(description["object_id_field"], "OBJECTID")
        self.assertEqual(description["geometry_type"], "esriGeometryPolygon")
        self.assertEqual(description["fields"][1]["alias"], "Hazard class")
        self.assertEqual(description["fields"][1]["unit"], "category")
        self.assertEqual(description["spatial_reference"]["wkid"], 2193)

    def test_describe_rejects_implausible_service_and_layer_payloads(self):
        base = "https://mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer"
        for argv, malformed in (
            (["describe", base, "--json"], {}),
            (
                ["describe", base, "--json"],
                {"currentVersion": 11.1, "layers": [{}], "tables": []},
            ),
            (
                ["describe", base, "--layer-id", "10", "--json"],
                {"name": "looks like metadata but has no layer identity"},
            ),
            (
                ["describe", base, "--layer-id", "10", "--json"],
                {
                    "id": 10,
                    "name": "Looks plausible",
                    "type": "Feature Layer",
                    "fields": {},
                },
            ),
        ):
            self.assert_rejected(
                lambda argv=argv, malformed=malformed: self.invoke(
                    argv,
                    lambda url, params=None: (malformed, url),
                ),
                6,
                "malformed_response",
            )

    def test_query_shared_controls_map_to_arcgis_and_normalise_modes(self):
        layer = (
            "https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/"
            "Synthetic/FeatureServer/0"
        )
        calls = []

        def fake_count(url, params=None):
            calls.append((url, params))
            return {"count": 17}, url + "?synthetic"

        payload = self.invoke(
            [
                "query",
                layer,
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

        payload = self.invoke(
            ["query", layer, "--ids-only", "--json"],
            lambda url, params=None: (fixture("query-ids.json"), url + "?synthetic"),
        )
        self.assertEqual(payload["kind"], "query-ids")
        self.assertEqual(payload["object_id_field"], "OBJECTID")
        self.assertEqual(payload["object_ids"], [2, 5, 9])

    def test_query_keeps_geojson_output_shape_and_accepts_negative_bbox(self):
        layer = (
            "https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/"
            "Synthetic/FeatureServer/0"
        )
        calls = []

        def fake_fetch(url, params=None):
            calls.append(params)
            return fixture("query-geojson.json"), url + "?synthetic"

        payload = self.invoke(
            [
                "query",
                layer,
                "--bbox",
                "-41.4,-41.3,174.9,-41.2",
                "--limit",
                "2",
                "--json",
            ],
            fake_fetch,
        )
        self.assertEqual(calls[0]["f"], "geojson")
        self.assertEqual(payload["kind"], "query")
        self.assertEqual(payload["feature_count"], 2)
        self.assertEqual(payload["features"][0]["type"], "Feature")

    def test_count_and_ids_are_mutually_exclusive(self):
        self.assert_parser_rejected(
            [
                "query",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "--count",
                "--ids-only",
            ]
        )

    def assert_parser_rejected(self, argv: list[str]):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            CLI.parse_args(argv)
        self.assertEqual(caught.exception.code, 2)
        raw = stderr.getvalue()
        self.assertTrue(raw.lstrip().startswith("{"), raw)
        payload = json.loads(raw)
        self.assertEqual(payload["error"]["skill"], "wcc-arcgis-nz")
        self.assertEqual(payload["error"]["category"], "invalid_input")
        self.assertEqual(payload["error"]["exit_code"], 2)

    def test_all_parser_and_type_failures_use_structured_json(self):
        for argv in (
            ["query", "a" * 32, "--offset", "-1"],
            ["query", "a" * 32, "--geometry-precision", "16"],
            ["query", "a" * 32, "--max-allowable-offset", "NaN"],
            ["identify", "a" * 32, "--point", "174,-41", "--tolerance", "101"],
            ["query", "a" * 32, "--unknown"],
        ):
            self.assert_parser_rejected(argv)

    def test_fields_and_order_by_use_strict_arcgis_identifier_grammar(self):
        parsed = CLI.parse_args(
            [
                "query",
                "a" * 32,
                "--fields",
                "OBJECTID, hazards.CLASS_CODE",
                "--order-by",
                "hazards.CLASS_CODE desc, OBJECTID ASC",
            ]
        )
        self.assertEqual(parsed.fields, "OBJECTID,hazards.CLASS_CODE")
        self.assertEqual(
            parsed.order_by,
            "hazards.CLASS_CODE DESC,OBJECTID ASC",
        )
        for flag, value in (
            ("--fields", ""),
            ("--fields", "hazards."),
            ("--fields", ".OBJECTID"),
            ("--fields", "OBJECTID,,NAME"),
            ("--fields", "OBJECTID;DROP TABLE x"),
            ("--order-by", "OBJECTID DOWN"),
            ("--order-by", "OBJECTID DESC;DROP"),
            ("--order-by", "hazards..CLASS ASC"),
            ("--order-by", "OBJECTID ASC,"),
        ):
            self.assert_parser_rejected(["query", "a" * 32, flag, value])

    def test_identify_builds_wgs84_request_and_accepts_negative_leading_point(self):
        base = "https://mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer"
        for point_args in (["--point", "-41.29,74.78"], ["--point=-41.29,74.78"]):
            calls = []

            def fake_fetch(url, params=None):
                calls.append((url, params))
                return fixture("identify.json"), url + "?synthetic"

            payload = self.invoke(
                [
                    "identify",
                    base,
                    *point_args,
                    "--layer-id",
                    "10",
                    "--tolerance",
                    "7",
                    "--no-geometry",
                    "--json",
                ],
                fake_fetch,
            )
            self.assertTrue(calls[0][0].endswith("/identify"))
            params = calls[0][1]
            self.assertEqual(
                json.loads(params["geometry"]),
                {"x": -41.29, "y": 74.78, "spatialReference": {"wkid": 4326}},
            )
            self.assertEqual(params["layers"], "all:10")
            self.assertEqual(params["tolerance"], 7)
            self.assertEqual(params["returnGeometry"], "false")
            self.assertEqual(params["sr"], "4326")
            self.assertEqual(payload["kind"], "identify")
            self.assertEqual(payload["result_count"], 1)

    def test_point_bbox_and_numeric_controls_reject_invalid_values(self):
        for raw in ("NaN,0", "0,inf", "-181,0", "181,0", "0,-91", "0,91"):
            self.assert_rejected(lambda raw=raw: CLI.parse_point(raw), 2)
        for raw in (
            "NaN,-40,175,-39",
            "-181,-40,175,-39",
            "170,-91,175,-39",
            "175,-40,170,-39",
        ):
            self.assert_rejected(lambda raw=raw: CLI.parse_bbox(raw), 2)
        for argv in (
            ["query", "a" * 32, "--offset", "-1"],
            ["query", "a" * 32, "--geometry-precision", "16"],
            ["query", "a" * 32, "--max-allowable-offset", "NaN"],
            ["identify", "a" * 32, "--point", "174,-41", "--tolerance", "101"],
        ):
            self.assert_parser_rejected(argv)

    def test_service_paths_across_all_wellington_hosts_and_redirects(self):
        accepted = (
            "https://services.arcgis.com/RS7BXJAO6ksvblJm/arcgis/rest/services/Synthetic/MapServer",
            "https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/Synthetic/FeatureServer/0",
            "https://services2.arcgis.com/XTtANUDT8Va4DLwI/arcgis/rest/services/Synthetic/MapServer",
            "https://gis.wcc.govt.nz/arcgis/rest/services/Synthetic/FeatureServer",
            "https://giswebprd.gw.govt.nz/arcgis/rest/services/Synthetic/MapServer",
            "https://mapping.gw.govt.nz/arcgis/rest/services/Synthetic/MapServer",
            "https://mapping1.gw.govt.nz/arcgis/rest/services/Synthetic/MapServer/10",
            "https://maps.gw.govt.nz/portal/rest/services/Synthetic/MapServer",
            "https://gis.wellingtonwater.co.nz/server1/rest/services/Modelling/Synthetic/MapServer",
        )
        for url in accepted:
            CLI.check_layer_host(url)
        rejected = (
            "https://services1.arcgis.com/FOREIGN/arcgis/rest/services/Synthetic/MapServer",
            "https://mapping1.gw.govt.nz/not/rest/services/Synthetic/MapServer",
            "https://maps.gw.govt.nz/portal/rest/services/Synthetic/MapServer/0/extra",
            "https://gis.wellingtonwater.co.nz/server2/rest/services/Synthetic/MapServer",
            "https://gis.wcc.govt.nz/arcgis/rest/services/Synthetic/ImageServer",
            "https://mapping1.gw.govt.nz/arcgis/rest/services/%2e%2e/Admin/MapServer",
            "https://mapping1.gw.govt.nz/arcgis/rest/services/Synthetic/MapServer?token=no",
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
                "https://evil.example/arcgis/rest/services/X/MapServer",
            ),
        ):
            self.assert_rejected(
                lambda: CLI.fetch_json(
                    "https://mapping1.gw.govt.nz/arcgis/rest/services/X/MapServer",
                    {"f": "json"},
                ),
                7,
                "blocked_host",
            )

    def test_empty_results_are_honest_and_malformed_responses_are_structured(self):
        base = "https://mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer"
        payload = self.invoke(
            ["identify", base, "--point", "174.78,-41.29", "--json"],
            lambda url, params=None: ({"results": []}, url),
        )
        self.assertEqual(payload["result_count"], 0)
        self.assertEqual(payload["results"], [])

        self.assert_rejected(
            lambda: self.invoke(
                ["search", "flood", "--json"],
                lambda url, params=None: ({"total": 1}, url),
            ),
            6,
            "malformed_response",
        )
        self.assert_rejected(
            lambda: self.invoke(
                ["query", base + "/10", "--json"],
                lambda url, params=None: ({"notFeatures": []}, url),
            ),
            6,
            "malformed_response",
        )

    def test_sensor_fetch_uses_exact_host_and_structured_network_categories(self):
        with mock.patch.object(CLI.nzfetch, "fetch_text", return_value="A,B\n") as fetch:
            self.assertEqual(CLI.fetch_csv_rows(CLI.SENSOR_META_URL), [])
        self.assertEqual(
            fetch.call_args.kwargs.get("allowed_hosts"),
            ["gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com"],
        )

        cases = (
            (CLI.nzfetch.RateLimited("slow", retry_after="10"), 4, "rate_limited"),
            (CLI.nzfetch.Blocked("blocked"), 4, "blocked"),
            (CLI.nzfetch.FetchError("down"), 5, "upstream_http_failure"),
        )
        for error, code, category in cases:
            with mock.patch.object(CLI.nzfetch, "fetch_text", side_effect=error):
                self.assert_rejected(
                    lambda: CLI.fetch_csv_rows(CLI.SENSOR_META_URL),
                    code,
                    category,
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
        self.assertIn("WGS84", notes)
        self.assertIn("redirect", notes.lower())
        self.assertIn("Wellington Water", notes)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CapabilityContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    return run_contract_test(SKILL_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
