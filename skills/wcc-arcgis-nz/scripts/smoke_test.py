#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
FLOOD_LAYER = (
    "https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/"
    "dp_ihp_recommended_flood_hazard_overlays/FeatureServer/51"
)


def load_cli():
    spec = importlib.util.spec_from_file_location("wcc_arcgis_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    cli = load_cli()
    results: list[bool] = []

    def fixture_search():
        data = json.loads((FIXTURES / "arcgis-search.json").read_text(encoding="utf-8"))
        items = [cli.normalise_item(r) for r in data["results"]]
        assert items[0]["title"] == "Synthetic Flood Overlay"
        assert items[0]["url"].endswith("/FeatureServer")
        assert items[0]["owner"] == "SyntheticTeam_WCC"
        assert items[1]["url"] is None and items[1]["tags"] == []

    def fixture_service():
        service = json.loads((FIXTURES / "arcgis-service.json").read_text(encoding="utf-8"))
        rows = cli.parse_service_layers(service)
        assert [(r["id"], r["kind"]) for r in rows] == [(51, "layer"), (60, "table")]
        assert rows[0]["geometry_type"] == "esriGeometryPolygon"

    def fixture_bbox():
        params = cli.parse_bbox("174.7,-41.4,174.9,-41.2")
        assert params["geometryType"] == "esriGeometryEnvelope" and params["inSR"] == "4326"
        assert params["geometry"] == "174.7,-41.4,174.9,-41.2"

    def fixture_sensor_meta():
        rows = list(csv.DictReader(io.StringIO((FIXTURES / "countline-meta-sample.csv").read_text(encoding="utf-8"))))
        rows.append(
            {
                "COUNTLINE_ID": "90003",
                "NAME": "Synthetic malformed coordinate",
                "LATITUDE_START_LINE": "N/A",
                "LONGITUDE_START_LINE": "174.8",
                "EARLIEST": "2026-07-01",
                "LATEST": "2026-07-20",
            }
        )
        sensors = cli.parse_sensor_meta(rows)
        assert len(sensors) == 3, "row without COUNTLINE_ID must be dropped"
        assert sensors[0]["countline_id"] == "90001" and sensors[0]["latitude"] == -41.3
        assert sensors[0]["latest"] == "2026-07-21"
        assert sensors[-1]["latitude"] is None and sensors[-1]["longitude"] == 174.8
        assert cli.parse_optional_float("NaN") is None
        assert cli.parse_optional_float("inf") is None
        assert cli.parse_optional_float("-inf") is None

    def fixture_mobility():
        rows = list(csv.DictReader(io.StringIO((FIXTURES / "countline-mobility-sample.csv").read_text(encoding="utf-8"))))
        rows.append(
            {
                "COUNTLINE_ID": "90003",
                "COUNTLINE_DATE": "2026-07-20",
                "COUNTLINE_HOUR": "8",
                "DIRECTION_COUNT": "9",
                "COUNTLINE_TRANSPORT_CLASS": "Car",
                "DIRECTION": "N",
            }
        )
        summary = cli.summarise_mobility(rows)
        assert summary["latest_date"] == "2026-07-21"
        by_key = {(r["countline_id"], r["transport_class"]): r for r in summary["rows"]}
        walker = by_key[("90001", "Pedestrian")]
        assert walker["latest_date_count"] == 12, "hours and directions must sum; bad counts skipped"
        assert walker["latest_observed_date"] == "2026-07-21" and walker["stale"] is False
        assert walker["days_observed"] == 2 and walker["daily_average"] == 18.0
        assert by_key[("90002", "Car")]["latest_date_count"] == 3
        stale = by_key[("90003", "Car")]
        assert stale["latest_date_count"] is None, "missing observations must not be fabricated as zero"
        assert stale["latest_observed_date"] == "2026-07-20" and stale["stale"] is True

    def fixture_council_scope():
        allowed = "https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/example/FeatureServer"
        allowed_gwrc_legacy = "https://services.arcgis.com/XTtANUDT8Va4DLwI/arcgis/rest/services/example/FeatureServer"
        unrelated = "https://services1.arcgis.com/0MSEUqKaxRlEPj5g/arcgis/rest/services/example/FeatureServer"
        for verified in (
            allowed,
            allowed_gwrc_legacy,
            "https://maps.gw.govt.nz/portal/rest/services/example/MapServer",
            "https://giswebprd.gw.govt.nz/arcgis/rest/services/example/MapServer",
        ):
            cli.check_layer_host(verified)
        for rejected in (unrelated, allowed.replace("https://", "http://", 1)):
            try:
                cli.check_layer_host(rejected)
            except SystemExit as exc:
                assert exc.code == 7
            else:
                raise AssertionError(f"unverified ArcGIS route must be rejected: {rejected}")

        calls = []

        def fake_fetch(url, params=None):
            calls.append(url)
            return {
                "id": "external-item",
                "orgId": "UNRELATED_ORG",
                "type": "Feature Service",
                "url": unrelated,
            }, url

        original = cli.fetch_json
        cli.fetch_json = fake_fetch
        try:
            try:
                cli.resolve_layer_url("externalitem123", 0)
            except SystemExit as exc:
                assert exc.code == 7
            else:
                raise AssertionError("item outside WCC/GWRC must be rejected")
        finally:
            cli.fetch_json = original
        assert len(calls) == 1, "unrelated service URL must fail before a second network request"

    results.append(check("fixture sharing-search item normalisation", fixture_search))
    results.append(check("fixture service layer/table parser", fixture_service))
    results.append(check("fixture bbox envelope parameters", fixture_bbox))
    results.append(check("fixture countline metadata parser", fixture_sensor_meta))
    results.append(check("fixture mobility count aggregation", fixture_mobility))
    results.append(check("fixture council ArcGIS scope enforcement", fixture_council_scope))

    def live(name: str, args: list[str], assertion) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            if "network error" in stderr or "upstream unavailable" in stderr:
                print(f"[SKIP] live {name}: {stderr}")
                return
            raise AssertionError(f"exit {completed.returncode}: {stderr}")
        if not assertion(json.loads(completed.stdout)):
            raise AssertionError(f"live assertion for {name} evaluated false")
        print(f"[PASS] live {name}")

    def run_live() -> bool:
        try:
            live(
                "org-scoped search",
                ["search", "flood", "--limit", "3", "--json"],
                lambda d: bool(d["items"]) and d["total_matches"] > 0 and all(i["id"] and i["owner"] for i in d["items"]),
            )
            live(
                "flood layer bbox query",
                ["query", FLOOD_LAYER, "--bbox", "174.75,-41.35,174.82,-41.27", "--limit", "2", "--json"],
                lambda d: d["feature_count"] >= 1,
            )
            live(
                "sensor countline metadata",
                ["sensors", "--limit", "3", "--json"],
                lambda d: d["sensors"] and d["total_countlines"] > 100,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] live probe: {exc}")
            return False

    results.append(run_live())
    if all(results):
        print("[PASS] live smoke assertions completed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
