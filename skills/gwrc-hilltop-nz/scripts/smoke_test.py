#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("gwrc_hilltop_cli", CLI)
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

    def fixture_sites():
        root = ET.parse(FIXTURES / "hilltop-site-list.xml").getroot()
        sites = cli.parse_site_list(root)
        assert len(sites) == 2, "empty-name site must be dropped"
        assert sites[0]["name"] == "Synthetic River at Example Gorge"
        assert sites[0]["latitude"] == -41.1 and sites[0]["longitude"] == 175.1
        assert sites[1]["latitude"] is None

    def fixture_measurements():
        root = ET.parse(FIXTURES / "hilltop-measurement-list.xml").getroot()
        rows = cli.parse_measurement_list(root)
        assert [r["measurement"] for r in rows] == ["Stage", "Flow"]
        assert rows[0]["units"] == "mm" and rows[0]["data_source"] == "Water Level"
        assert rows[1]["units"] == "m³/sec"
        assert rows[0]["from"] == "1979-03-16T12:15:00"

        duplicate = {
            **rows[0],
            "data_source": "Gauging Results",
            "request_as": "Stage [Gauging Results]",
            "to": "2026-07-23T14:15:00",
        }
        assert cli.select_measurement_request([rows[0], duplicate], "Stage") == "Stage [Gauging Results]"
        assert cli.select_measurement_request([rows[0], duplicate], "Stage", exact=True) == "Stage"
        try:
            cli.select_measurement_request([rows[0], duplicate], "NotARequestAs", exact=True)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("unknown exact RequestAs must fail before GetData")
        assert cli.select_measurement_request([rows[0], duplicate], "Stage [Gauging Results]") == "Stage [Gauging Results]"

        original = cli.fetch_root
        cli.fetch_root = lambda *_args, **_kwargs: root
        output = StringIO()
        try:
            with redirect_stdout(output):
                cli.cmd_measurements(SimpleNamespace(base_url=cli.DEFAULT_BASE, site="Synthetic River", json=False))
        finally:
            cli.fetch_root = original
        assert "request as:" in output.getvalue().lower()
        assert rows[0]["request_as"] in output.getvalue()

    def fixture_time_series():
        root = ET.parse(FIXTURES / "hilltop-get-data.xml").getroot()
        blocks = cli.parse_time_series(root)
        assert len(blocks) == 4
        stage = blocks[0]
        assert stage["site"] == "Synthetic River at Example Gorge"
        assert stage["item_name"] == "Stage" and stage["units"] == "mm"
        assert len(stage["points"]) == 5 and stage["points"][-1]["value"] == 980.0
        assert cli.is_backup(blocks[1]) and not cli.is_backup(stage)
        rain = blocks[2]
        assert rain["item_name"] == "Rainfall" and rain["points"][-1]["value"] == 12.5
        assert blocks[3]["points"] == [], "non-numeric values must be skipped"

    def fixture_summary():
        root = ET.parse(FIXTURES / "hilltop-get-data.xml").getroot()
        blocks = cli.parse_time_series(root)
        summary = cli.summarise_block(blocks[0])
        assert summary["trend"] == "rising"
        assert summary["latest_value"] == 980.0 and summary["window_min"] == 900.0
        assert cli.summarise_block(blocks[3]) is None
        cutoff = cli.freshness_cutoff(["2016-05-29T18:15:00", "2026-07-22T14:00:00"], 24)
        assert cutoff is not None and "2016-05-29T18:15:00" < cutoff < "2026-07-22T14:00:00"

    def fixture_registry_only():
        original = cli.nzfetch.fetch_text
        called = False

        def unexpected_network(*_args, **_kwargs):
            nonlocal called
            called = True
            raise AssertionError("unregistered Hilltop host reached the network layer")

        probe_host = ".".join(("127", "0", "0", "1"))
        probe_base = f"http://{probe_host}:18765/data.hts"
        cli.nzfetch.fetch_text = unexpected_network
        try:
            try:
                cli.fetch_root(
                    f"{probe_base}?Service=Hilltop&Request=CollectionList",
                    probe_base,
                )
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("unregistered Hilltop base URL must be rejected")
        finally:
            cli.nzfetch.fetch_text = original
        assert not called, "unregistered Hilltop host must fail before network access"

    results.append(check("fixture Hilltop site-list parser", fixture_sites))
    results.append(check("fixture Hilltop measurement-list parser", fixture_measurements))
    results.append(check("fixture Hilltop GetData time-series parser", fixture_time_series))
    results.append(check("fixture trend summary and staleness cutoff", fixture_summary))
    results.append(check("fixture registry-only host enforcement", fixture_registry_only))

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
            live("sites", ["sites", "--search", "hutt river", "--limit", "3", "--json"], lambda d: d["sites"])
            live(
                "rainfall totals",
                ["rainfall", "--hours", "6", "--limit", "3", "--json"],
                lambda d: isinstance(d["gauges"], list) and d["total_sites"] > 0,
            )
            live(
                "river levels",
                ["rivers", "--hours", "6", "--limit", "3", "--json"],
                lambda d: isinstance(d["rivers"], list) and d["total_sites"] > 0,
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
