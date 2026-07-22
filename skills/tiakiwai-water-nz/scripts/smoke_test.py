#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("tiakiwai_cli", CLI)
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

    def fixture_jobs():
        data = json.loads((FIXTURES / "job-status-sample.json").read_text(encoding="utf-8"))
        jobs = [cli.normalise_job(f) for f in data["features"]]
        assert jobs[0]["job_number"] == "900001" and jobs[0]["council"] == "WCC"
        assert jobs[0]["water_type"] == "Storm Water" and jobs[0]["status"] == "In Progress"
        assert jobs[0]["longitude"] == 174.78 and jobs[0]["latitude"] == -41.3
        assert jobs[0]["reported_at"] and jobs[0]["reported_at"].startswith("2026-")
        assert jobs[1]["latitude"] is None, "missing geometry must not crash"
        assert jobs[1]["reported_at"] is None, "non-numeric epoch must not crash"

    def fixture_where():
        ns = argparse.Namespace(council="wcc", water_type="storm", search="O'Brien 100%_x", include_resolved=False)
        where = cli.build_where(ns)
        assert "councilid = 'WCC'" in where and "watertype = 'Storm Water'" in where
        assert "O''BRIEN" in where, "single quotes must be doubled in SQL literals"
        assert "100$%$_X" in where and "ESCAPE '$'" in where, "LIKE wildcards must be escaped to match literally"
        assert "Do Not Display" in where and "Resolved" in where
        ns2 = argparse.Namespace(include_resolved=True)
        assert "Resolved" not in cli.build_where(ns2).replace("Do Not Display", "")
        for bad in ("", "   ", "x" * 201):
            try:
                cli.build_where(argparse.Namespace(search=bad))
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError(f"search {bad!r} must be rejected")

    def fixture_epoch():
        assert cli.epoch_to_nz(1784600000000).startswith("2026-")
        assert cli.epoch_to_nz(None) is None and cli.epoch_to_nz("x") is None
        assert cli.epoch_to_nz(0) is None and cli.epoch_to_nz(True) is None

    results.append(check("fixture job feature normalisation", fixture_jobs))
    results.append(check("fixture where-clause construction and quoting", fixture_where))
    results.append(check("fixture epoch conversion", fixture_epoch))

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
                "summary counts",
                ["summary", "--json"],
                lambda d: d["total_jobs"] > 0 and any(r["council"] == "WCC" for r in d["by_council_and_type"]),
            )
            live(
                "faults listing",
                ["faults", "--council", "wcc", "--limit", "3", "--json"],
                lambda d: bool(d["faults"]) and all(j["council"] == "WCC" for j in d["faults"]),
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
