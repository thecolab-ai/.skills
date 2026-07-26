#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes.

The projections command downloads a ~54 MB CSV, so the live probes here stay
with the small site/VLM file only; the projections parser is exercised against
a fixture.
"""
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


def load_cli():
    spec = importlib.util.spec_from_file_location("searise_cli", CLI)
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


def read_rows(name: str) -> list[dict[str, str]]:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main() -> int:
    cli = load_cli()
    results: list[bool] = []

    def fixture_sites():
        sites = cli.parse_sites(read_rows("vlm-sample.csv"))
        assert len(sites) == 3, "the malformed row must be dropped, not crash"
        wellington = next(s for s in sites if s["site_id"] == 3414)
        assert wellington["vlm_mm_yr"] == -2.10
        assert wellington["vlm_1sigma_mm_yr"] == 1.204
        assert wellington["quality_factor"] == 1.5

    def fixture_haversine():
        d = cli.haversine_km(-41.29, 174.78, -41.29, 174.78)
        assert d == 0.0
        d = cli.haversine_km(-41.29, 174.78, -36.85, 174.76)
        assert 490 < d < 500, f"Wellington-Auckland should be ~494 km, got {d}"

    def fixture_projections():
        rows = cli.parse_projection_rows(read_rows("projections-sample.csv"), 3414)
        assert len(rows) == 4, "other sites' rows and non-numeric years must be excluded"
        scenarios = sorted({r["scenario"] for r in rows})
        assert scenarios == ["SSP1-2.6", "SSP2-4.5", "SSP5-8.5"]
        ssp245_2100 = next(r for r in rows if r["scenario"] == "SSP2-4.5" and r["year"] == 2100)
        assert ssp245_2100["p50_m"] == 0.71
        assert ssp245_2100["confidence"] == "medium"

    def fixture_latlon():
        assert cli.parse_latlon("-41.29,174.78") == (-41.29, 174.78)
        for bad in ("-41.29", "a,b", "-95,174.78"):
            try:
                cli.parse_latlon(bad)
            except SystemExit as exc:
                assert exc.code == 2, f"bad --near {bad!r} must exit 2"
            else:
                raise AssertionError(f"bad --near {bad!r} was accepted")

    def fixture_negative_near_cli():
        args = cli.parse_cli_args(
            ["sites", "--near", "-41.29,174.78", "--limit", "3", "--json"]
        )
        assert args.near == "-41.29,174.78"
        assert args.limit == 3
        assert args.json is True
        assert args.func is cli.cmd_sites

    results.append(check("fixture VLM site parser", fixture_sites))
    results.append(check("fixture haversine distance", fixture_haversine))
    results.append(check("fixture projections parser", fixture_projections))
    results.append(check("fixture lat,lon validation", fixture_latlon))
    results.append(check("fixture CLI accepts a negative --near latitude", fixture_negative_near_cli))

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
                "nearest sites to Wellington",
                ["sites", "--near", "-41.29,174.78", "--limit", "3", "--json"],
                lambda d: d["total_sites"] > 7000
                and len(d["sites"]) == 3
                and d["sites"][0]["distance_km"] < 10,
            )
            live(
                "VLM detail for the nearest site",
                ["vlm", "3414", "--json"],
                lambda d: d["site"]["site_id"] == 3414 and d["site"]["vlm_mm_yr"] is not None,
            )
            print("[SKIP] live projections probe: intentionally not run (54 MB download); parser covered by fixture")
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
