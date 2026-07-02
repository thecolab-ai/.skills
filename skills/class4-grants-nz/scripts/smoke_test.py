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

    print("class4-grants-nz smoke test passed")


if __name__ == "__main__":
    main()
