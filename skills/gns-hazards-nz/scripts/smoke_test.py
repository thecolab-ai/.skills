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

    def fixture_archive_metadata():
        events = cli.normalise_events(
            json.loads((FIXTURES / "events.json").read_text(encoding="utf-8")),
            year=2026,
            source_url="https://shakinglayers.geonet.org.nz/api/v1/events?year=2026",
        )
        assert events["event_count"] == 2
        versions = cli.normalise_versions(
            json.loads((FIXTURES / "versions.json").read_text(encoding="utf-8")),
            requested_event_id="771645",
            source_url="https://shakinglayers.geonet.org.nz/api/v1/events/771645",
        )
        assert versions["versions"][0]["type"] == "reviewed"
        files = cli.normalise_event_files(
            json.loads((FIXTURES / "event-files.json").read_text(encoding="utf-8")),
            event_id="771645",
            requested_version="latest",
        )
        assert files["versionpath"] == "2023-09-07T22:28:40-reviewed"
        assert {row["measure"] for row in files["available_measures"]} == {
            "mmi", "pga", "pgv", "psa0.3", "psa1.0", "psa3.0",
        }

    def fixture_describe_and_controls():
        metadata = cli.normalise_description(
            json.loads((FIXTURES / "layer-description.json").read_text(encoding="utf-8")),
            service="faults",
            layer_id=0,
            layer_url=cli.FAULTS_SERVICE + "/0",
            source_url=cli.FAULTS_SERVICE + "/0?f=json",
        )
        assert metadata["object_id_field"] == "objectid"
        assert metadata["extent"]["spatial_reference"]["wkid"] == 4326
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "faults", "--count", "--offset", "10", "--order-by", "OBJECTID DESC",
                "--geometry-precision", "4", "--max-allowable-offset", "0.25",
            ]
        )
        params = cli.build_query_params(args)
        assert params["returnCountOnly"] == "true"
        assert params["resultOffset"] == 10
        assert params["orderByFields"] == "OBJECTID DESC"

    results.append(check("fixture service layer parser", fixture_service_layers))
    results.append(check("fixture bbox validation", fixture_bbox))
    results.append(check("fixture shaking contour extraction", fixture_shaking_contours))
    results.append(check("fixture measure layer map", fixture_measure_map))
    results.append(check("fixture archive metadata", fixture_archive_metadata))
    results.append(check("fixture describe and query controls", fixture_describe_and_controls))

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
                "shaking service layers",
                ["layers", "--service", "shaking", "--json"],
                lambda d: any(l["id"] == cli.SHAKING_MEASURES["mmi"] for l in d["layers"]),
            )
            live(
                "recent ShakingLayers events",
                ["events", "--json"],
                lambda d: d["event_count"] >= 1 and isinstance(d["event_ids"][0], str),
            )
            recent = subprocess.run(
                [sys.executable, str(CLI), "events", "--json"],
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )
            if recent.returncode == 0:
                event_id = json.loads(recent.stdout)["event_ids"][0]
                live(
                    "event versions",
                    ["versions", event_id, "--json"],
                    lambda d: d["event_id"] == event_id and d["version_count"] >= 1,
                )
                live(
                    "event files",
                    ["event-files", event_id, "--version", "latest", "--json"],
                    lambda d: d["event_id"] == event_id and d["file_count"] >= 1,
                )
            elif "network error" in recent.stderr or "upstream unavailable" in recent.stderr:
                print(f"[SKIP] live archive metadata: {recent.stderr.strip()}")
            else:
                raise AssertionError(f"events exit {recent.returncode}: {recent.stderr.strip()}")
            live(
                "fault layer description",
                ["describe", "faults", "--layer-id", "0", "--json"],
                lambda d: d["object_id_field"] and isinstance(d["fields"], list),
            )
            live(
                "bounded fault count",
                ["faults", "--bbox", "174.6,-41.5,175.1,-41.0", "--count", "--json"],
                lambda d: isinstance(d["count"], int) and d["count"] >= 0,
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
