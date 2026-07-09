#!/usr/bin/env python3
"""Smoke tests for eeca-ev-chargers-nz.

Live EECA/data.govt.nz checks skip rather than hard-fail on transient upstream
network errors. Deterministic CLI and validation-shape checks fail normally.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=60,
    )


def is_network_failure(result: subprocess.CompletedProcess) -> bool:
    text = (result.stderr + "\n" + result.stdout).lower()
    return any(
        marker in text
        for marker in [
            "network error",
            "timed out",
            "timeout",
            "http 403",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "urlopen error",
            # data.govt.nz / EECA sit behind Incapsula, which answers API
            # requests with an HTML bot-challenge (often HTTP 200) — a transient
            # block, not a real failure. Skip rather than hard-fail on these.
            "blocked",
            "bot-challenge",
            "bot-blocking",
            "incapsula",
        ]
    )


def report(status: str, name: str, detail: str = "") -> str:
    print(f"[{status}] {name}")
    if detail:
        print(f"  {detail}")
    return status


def json_command(name: str, args: list[str], check) -> str:
    result = run(args)
    if result.returncode != 0:
        if is_network_failure(result):
            return report("SKIP", name, result.stderr[:240] or result.stdout[:240])
        return report("FAIL", name, result.stderr[:240] or result.stdout[:240])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return report("FAIL", name, str(e))
    ok, detail = check(data)
    return report("PASS" if ok else "FAIL", name, detail)


results: list[str] = []


def test_help() -> str:
    result = run(["--help"])
    if result.returncode == 0 and "eeca" in result.stdout.lower():
        return report("PASS", "--help exits 0")
    return report("FAIL", "--help exits 0", result.stderr[:240] or result.stdout[:240])


results.append(test_help())

results.append(
    json_command(
        "datasets returns CKAN resources",
        ["datasets", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("resources"), list)
            and len(data["resources"]) >= 4,
            "expected at least four dashboard resources",
        ),
    )
)

results.append(
    json_command(
        "chargers filters DC fast units",
        ["chargers", "--current", "DC", "--min-kw", "50", "--limit", "5", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("records"), list)
            and len(data["records"]) > 0
            and all(row.get("current") == "DC" and row.get("kw_rated", 0) >= 50 for row in data["records"]),
            "expected non-empty DC records with kw_rated >= 50",
        ),
    )
)

results.append(
    json_command(
        "metrics returns regional EV ratios",
        ["metrics", "--level", "region", "--limit", "5", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("records"), list)
            and any(row.get("battery_electric_vehicles") for row in data["records"]),
            "expected regional BEV counts",
        ),
    )
)

results.append(
    json_command(
        "cofunded live filter returns rows",
        ["cofunded", "--status", "live", "--limit", "5", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("records"), list)
            and len(data["records"]) > 0
            and all((row.get("status") or "").lower() == "live" for row in data["records"]),
            "expected live co-funded charger rows",
        ),
    )
)

results.append(
    json_command(
        "summary aggregates Auckland",
        ["summary", "--level", "region", "--region", "Auckland", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and len(data.get("records", [])) == 1
            and data["records"][0].get("charge_points", 0) > 0
            and data["records"][0].get("bevs_per_charge_point") is not None,
            "expected one Auckland aggregate with EV ratio",
        ),
    )
)

results.append(
    json_command(
        "district summary honours region filter",
        ["summary", "--level", "district", "--region", "Auckland", "--limit", "10", "--json"],
        lambda data: (
            data.get("status") == "ok"
            and isinstance(data.get("records"), list)
            and len(data["records"]) == 1
            and data["records"][0].get("name") == "Auckland"
            and data["records"][0].get("dashboard_metric", {}).get("region") == "Auckland",
            "expected only the Auckland district when district summary is region-filtered",
        ),
    )
)

failures = results.count("FAIL")
skips = results.count("SKIP")
if failures:
    print(f"{failures} test(s) failed; {skips} skipped.")
    sys.exit(1)

print(f"All non-skipped tests passed; {skips} skipped.")
sys.exit(0)
