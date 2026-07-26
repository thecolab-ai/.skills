#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("niwa_coastal_cli", CLI)
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

    def fixture_search_normalise():
        data = json.loads((FIXTURES / "search-sample.json").read_text(encoding="utf-8"))
        items = [cli.normalise_item(r) for r in data["results"]]
        assert len(items) == 2
        assert items[0]["id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert items[0]["title"].startswith("Synthetic Coastal Sensitivity")
        assert items[0]["url"].startswith("https://services3.arcgis.com/fp1tibNcN9mbExhG/")
        assert items[1]["url"] is None, "items without a service URL must stay None, not become ''"
        assert items[1]["tags"] == []

    def fixture_capability_shapes():
        item = json.loads((FIXTURES / "item.json").read_text(encoding="utf-8"))
        cli.validate_item_org(item, item["id"])
        metadata = cli.normalise_catalogue_item(item)
        assert metadata["licence"] == "CC BY 4.0"
        assert metadata["service_url"].endswith("/FeatureServer")

        layer = json.loads((FIXTURES / "layer.json").read_text(encoding="utf-8"))
        description = cli.normalise_description(layer)
        assert description["object_id_field"] == "OBJECTID"
        assert description["fields"][1]["alias"] == "Exposure class"
        assert description["spatial_reference"]["wkid"] == 2193

        lon, lat = cli.parse_point("174.78,-41.29")
        assert (lon, lat) == (174.78, -41.29)

    def fixture_host_allowlist():
        cli.check_layer_host("https://services3.arcgis.com/fp1tibNcN9mbExhG/arcgis/rest/services/X/FeatureServer")
        cli.check_layer_host("https://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer")
        rejected = [
            "http://gis.niwa.co.nz/server/rest/services/COAST/Synthetic/MapServer",  # not HTTPS
            "https://services3.arcgis.com/OTHERORG00000000/arcgis/rest/services/X/FeatureServer",  # wrong tenant
            "https://evil.example/arcgis/rest/services/X/FeatureServer",  # unknown host
            "https://gis.niwa.co.nz:8443/server/rest/services/X/MapServer",  # explicit port
        ]
        for url in rejected:
            try:
                cli.check_layer_host(url)
            except SystemExit as exc:
                assert exc.code == 7, f"{url} must exit 7"
            else:
                raise AssertionError(f"{url} was accepted")

    def fixture_org_validation():
        cli.validate_item_org({"orgId": "fp1tibNcN9mbExhG"}, "ok-item")
        try:
            cli.validate_item_org({"orgId": "SomeoneElse"}, "bad-item")
        except SystemExit as exc:
            assert exc.code == 7
        else:
            raise AssertionError("foreign org item was accepted")

    def fixture_bbox():
        params = cli.parse_bbox("166.0,-47.5,179.0,-34.0")
        assert params["geometryType"] == "esriGeometryEnvelope"
        try:
            cli.parse_bbox("179.0,-47.5,166.0,-34.0")
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("inverted bbox was accepted")

    results.append(check("fixture search item normaliser", fixture_search_normalise))
    results.append(check("fixture item/describe/point capabilities", fixture_capability_shapes))
    results.append(check("fixture layer host allowlist", fixture_host_allowlist))
    results.append(check("fixture item org validation", fixture_org_validation))
    results.append(check("fixture bbox validation", fixture_bbox))

    def live(name: str, args: list[str], assertion) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            timeout=90,
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
                "catalogue search",
                ["search", "coastal sensitivity", "--limit", "2", "--start", "1", "--json"],
                lambda d: d["total_matches"] >= 1
                and d["start"] == 1
                and "next_start" in d
                and all(i["id"] for i in d["items"]),
            )
            live(
                "CSI erosion item metadata",
                ["item", "c894b53b102f4f9db55278f7572ca4f6", "--json"],
                lambda d: d["item"]["organisation"] == "fp1tibNcN9mbExhG"
                and bool(d["item"]["service_url"]),
            )
            live(
                "CSI erosion service layers",
                ["layers", "c894b53b102f4f9db55278f7572ca4f6", "--json"],
                lambda d: bool(d["layers"]),
            )
            live(
                "CSI erosion layer describe",
                [
                    "describe",
                    "c894b53b102f4f9db55278f7572ca4f6",
                    "--layer-id", "0",
                    "--json",
                ],
                lambda d: d["description"]["object_id_field"] is not None,
            )
            live(
                "CSI erosion layer count",
                [
                    "query",
                    "c894b53b102f4f9db55278f7572ca4f6",
                    "--count",
                    "--json",
                ],
                lambda d: d["kind"] == "query-count" and d["count"] >= 1,
            )
            live(
                "beach exposure MapServer identify",
                [
                    "identify",
                    "2e2f8ea5ea31453e808b36b2a1ca43a0",
                    "--point", "174.78,-41.29",
                    "--no-geometry",
                    "--json",
                ],
                lambda d: d["kind"] == "identify" and isinstance(d["results"], list),
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
