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
                ["search", "coastal sensitivity", "--limit", "3", "--json"],
                lambda d: d["total_matches"] >= 1 and all(i["id"] for i in d["items"]),
            )
            live(
                "CSI erosion layer query",
                [
                    "query",
                    "c894b53b102f4f9db55278f7572ca4f6",
                    "--limit", "2",
                    "--fields", "OBJECTID",
                    "--json",
                ],
                lambda d: d["feature_count"] >= 1,
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
