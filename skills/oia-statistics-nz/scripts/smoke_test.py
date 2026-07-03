#!/usr/bin/env python3
"""Smoke tests for oia-statistics-nz.

Network-dependent commands return upstream_unavailable on blocked/outage states and
are treated as skip conditions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, timeout=timeout)


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> dict:
    payload = (proc.stdout or proc.stderr).strip()
    return json.loads(payload or "{}") if payload else {}


def is_upstream_skip(proc: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    if proc.returncode != 2:
        return False, ""
    try:
        data = parse_json_output(proc)
    except Exception:
        return False, ""
    if data.get("error") == "upstream_unavailable":
        return True, str(data.get("message", ""))
    return False, ""


def main() -> int:
    help_proc = run(["--help"], timeout=20)
    if help_proc.returncode != 0 or "list-agencies" not in (help_proc.stdout or ""):
        print("FAIL: --help should list available commands", file=sys.stderr)
        print(help_proc.stdout)
        print(help_proc.stderr, file=sys.stderr)
        return 1

    periods = run(["periods", "--limit", "1", "--json"])
    if periods.returncode == 2:
        skip, message = is_upstream_skip(periods)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(periods.stderr or periods.stdout, file=sys.stderr)
        return 1
    if periods.returncode != 0:
        print(periods.stderr or periods.stdout, file=sys.stderr)
        return 1

    periods_data = parse_json_output(periods)
    if periods_data.get("kind") != "oia-periods" or not isinstance(periods_data.get("periods"), list):
        print("FAIL: periods command did not return expected JSON shape", file=sys.stderr)
        print(periods.stdout, file=sys.stderr)
        return 1
    latest_period = periods_data.get("latest_period")
    print(f"OK: periods returned {periods_data.get('count')} period(s)")

    agencies = run(["list-agencies", "--limit", "3", "--json"])
    if agencies.returncode == 2:
        skip, message = is_upstream_skip(agencies)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(agencies.stderr or agencies.stdout, file=sys.stderr)
        return 1
    if agencies.returncode != 0:
        print(agencies.stderr or agencies.stdout, file=sys.stderr)
        return 1
    agencies_data = parse_json_output(agencies)
    agency_rows = agencies_data.get("agencies") or []
    if agencies_data.get("kind") != "oia-list-agencies" or not agency_rows:
        print("FAIL: list-agencies command did not return expected agency rows", file=sys.stderr)
        print(agencies.stdout, file=sys.stderr)
        return 1

    org_id = agency_rows[0].get("org_id")
    if isinstance(org_id, int):
        agency = run(["agency", str(org_id), "--json"], timeout=180)
        if agency.returncode == 2:
            skip, message = is_upstream_skip(agency)
            if skip:
                print(f"SKIP: upstream unavailable ({message})")
                return 0
            print(agency.stderr or agency.stdout, file=sys.stderr)
            return 1
        if agency.returncode != 0:
            print(agency.stderr or agency.stdout, file=sys.stderr)
            return 1
        agency_data = parse_json_output(agency)
        if agency_data.get("kind") != "oia-agency" or not agency_data.get("records"):
            print("FAIL: agency command did not return expected records", file=sys.stderr)
            print(agency.stdout, file=sys.stderr)
            return 1
        print(f"OK: agency lookup by OrgID {org_id} returned {len(agency_data['records'])} rows")

    totals = run(["totals", "--period", latest_period or "latest", "--json"], timeout=120)
    if totals.returncode == 2:
        skip, message = is_upstream_skip(totals)
        if skip:
            print(f"SKIP: upstream unavailable ({message})")
            return 0
        print(totals.stderr or totals.stdout, file=sys.stderr)
        return 1
    if totals.returncode != 0:
        print(totals.stderr or totals.stdout, file=sys.stderr)
        return 1
    totals_data = parse_json_output(totals)
    if totals_data.get("kind") != "oia-totals" or not isinstance(totals_data.get("totals"), dict):
        print("FAIL: totals command did not return expected shape", file=sys.stderr)
        print(totals.stdout, file=sys.stderr)
        return 1
    print(f"OK: totals returned requests_handled={totals_data['totals'].get('requests_handled')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
