#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("class4_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)

NETWORK_SKIP_MARKERS = (
    "network error",
    "HTTP 403",
    "HTTP 429",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
    "timed out",
    "Temporary failure",
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
    cleaned = fixture_cli.clean_row(
        {
            "Society_Name": "Fixture Trust",
            "Amount_Requested_Final": "$1,234.50",
            "Amount_Granted_Final": "1000",
            "Amount_Refunded_Clean": "",
        }
    )
    assert cleaned["Amount_Requested_Final_Number"] == 1234.5
    assert cleaned["Amount_Granted_Final_Number"] == 1000.0
    assert cleaned["Amount_Refunded_Clean_Number"] == 0.0
    print("[PASS] fixture grant CSV money normalisation")

    help_proc = run(["--help"])
    assert "datasets" in help_proc.stdout
    assert "grants" in help_proc.stdout

    datasets = run(["datasets", "--json"], allow_network_skip=True)
    datasets_payload = json.loads(datasets.stdout)
    assert datasets_payload["kind"] == "datasets"
    assert any(d["name"] == "class-4-grants-data" for d in datasets_payload["datasets"])

    preview = run(["preview", "--limit", "2", "--json"], allow_network_skip=True)
    preview_payload = json.loads(preview.stdout)
    assert preview_payload["kind"] == "preview"
    assert preview_payload["count"] == 2
    assert "Society_Name" in preview_payload["records"][0]

    filtered = run(["grants", "--year", "2024", "--status", "Accepted", "--limit", "1", "--json"], allow_network_skip=True)
    filtered_payload = json.loads(filtered.stdout)
    assert filtered_payload["kind"] == "grants"
    assert filtered_payload["matched"] >= 1
    assert filtered_payload["records"][0]["Status"] == "Accepted"

    edge = run(["grants", "--query", "definitely-not-a-real-class4-recipient-xyz", "--limit", "1", "--json"], allow_network_skip=True)
    edge_payload = json.loads(edge.stdout)
    assert edge_payload["kind"] == "grants"
    assert edge_payload["matched"] == 0
    assert edge_payload["records"] == []

    print("[PASS] live class 4 datasets, preview, filtering and empty-result assertions")


if __name__ == "__main__":
    main()
