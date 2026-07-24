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
    spec = importlib.util.spec_from_file_location("gns_hazards_cli", CLI)
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

    def fixture_service_layers():
        service = json.loads((FIXTURES / "service-sample.json").read_text(encoding="utf-8"))
        rows = cli.parse_service_layers(service)
        assert len(rows) == 3
        assert rows[0] == {
            "id": 0,
            "name": "1:250 000 Active Faults",
            "kind": "layer",
            "geometry_type": "esriGeometryPolyline",
        }
        assert rows[2]["kind"] == "table", "tables must be listed after layers"
        assert cli.parse_service_layers({}) == [], "an empty service must yield no rows, not crash"

    def fixture_bbox():
        params = cli.parse_bbox("174.7,-41.4,174.9,-41.2")
        assert params["geometry"] == "174.7,-41.4,174.9,-41.2"
        assert params["geometryType"] == "esriGeometryEnvelope"
        assert params["inSR"] == "4326"
        for bad in ("174.7,-41.4,174.9", "a,b,c,d", "174.9,-41.4,174.7,-41.2"):
            try:
                cli.parse_bbox(bad)
            except SystemExit as exc:
                assert exc.code == 2, f"bad bbox {bad!r} must exit 2"
            else:
                raise AssertionError(f"bad bbox {bad!r} was accepted")

    def fixture_shaking_contours():
        data = json.loads((FIXTURES / "shaking-geojson-sample.json").read_text(encoding="utf-8"))
        features = data["features"]
        contours = sorted(
            {p.get("Contour") for f in features if (p := f.get("properties") or {}).get("Contour") is not None}
        )
        assert contours == [7, 8], "distinct contour extraction must skip the Contour-less feature"
        assert data.get("exceededTransferLimit") is True

    def fixture_measure_map():
        assert cli.SHAKING_MEASURES == {
            "mmi": 1, "pga": 4, "pgv": 7, "psa0.3": 10, "psa1.0": 13, "psa3.0": 16,
        }, "measure→layer map must match the documented service layout"

    results.append(check("fixture service layer parser", fixture_service_layers))
    results.append(check("fixture bbox validation", fixture_bbox))
    results.append(check("fixture shaking contour extraction", fixture_shaking_contours))
    results.append(check("fixture measure layer map", fixture_measure_map))

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
                "fault service layers",
                ["layers", "--service", "faults", "--json"],
                lambda d: any(l["name"] == "1:250 000 Active Faults" for l in d["layers"]),
            )
            live(
                "fault trace query",
                ["faults", "--bbox", "174.6,-41.5,175.1,-41.0", "--limit", "3", "--json"],
                lambda d: d["feature_count"] >= 1 and all("properties" in f for f in d["features"]),
            )
            live(
                "shaking mmi contours",
                ["shaking", "--measure", "mmi", "--limit", "3", "--json"],
                lambda d: isinstance(d["features"], list) and d["measure"] == "mmi",
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
