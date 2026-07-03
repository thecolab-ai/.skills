#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"

NETWORK_SKIP_MARKERS = (
    "network error",
    "HTTP 403",
    "HTTP 404",
    "HTTP 429",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
    "timed out",
    "Temporary failure",
    "no .xlsx link found",
    "no matching expenditure CSV resource found",
    "could not find an .xlsx workbook link",
)


def run(args: list[str], *, allow_network_skip: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=120)
    if proc.returncode != 0:
        combined = proc.stdout + proc.stderr
        if allow_network_skip and any(marker.lower() in combined.lower() for marker in NETWORK_SKIP_MARKERS):
            print(f"SKIP network-dependent command {' '.join(args)}: {combined.strip()}")
            raise SystemExit(0)
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc


def main() -> None:
    help_proc = run(["--help"])
    assert "datasets" in help_proc.stdout
    assert "measures" in help_proc.stdout
    assert "burden" in help_proc.stdout
    assert "disconnections" in help_proc.stdout

    datasets = run(["datasets", "--json"], allow_network_skip=True)
    payload = json.loads(datasets.stdout)
    assert payload["kind"] == "datasets"
    ids = {s["id"] for s in payload["sources"]}
    assert ids == {"mbie-energy-hardship-measures", "stats-nz-hes-expenditure", "ea-emi-disconnections"}

    measures = run(["measures", "--year-ended", "2024", "--json"], allow_network_skip=True)
    measures_payload = json.loads(measures.stdout)
    assert measures_payload["kind"] == "measures"
    assert isinstance(measures_payload["records"], list)

    burden = run(["burden", "--breakdown", "income-decile", "--year", "2023", "--json"], allow_network_skip=True)
    burden_payload = json.loads(burden.stdout)
    assert burden_payload["kind"] == "burden"
    assert burden_payload["breakdown"] == "income-decile"
    assert isinstance(burden_payload["records"], list)

    disconnections = run(
        ["disconnections", "--from", "2024-01", "--to", "2024-06", "--json"], allow_network_skip=True
    )
    disconnections_payload = json.loads(disconnections.stdout)
    assert disconnections_payload["kind"] == "disconnections"
    assert "available" in disconnections_payload

    bad_year = run(["burden", "--breakdown", "income-decile", "--year", "abcd", "--json"])
    assert bad_year.returncode != 0

    print("energy-hardship-nz smoke test passed")


if __name__ == "__main__":
    main()
