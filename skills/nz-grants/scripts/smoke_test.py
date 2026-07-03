#!/usr/bin/env python3
"""Smoke tests for nz-grants skill.

Network-dependent checks skip cleanly when upstream public sites are blocked or unavailable.
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
    text = proc.stdout.strip() or proc.stderr.strip()
    return json.loads(text)


def main() -> int:
    help_proc = run(["--help"], timeout=20)
    if help_proc.returncode != 0 or "class4" not in help_proc.stdout or "funds" not in help_proc.stdout:
        print(help_proc.stdout)
        print(help_proc.stderr, file=sys.stderr)
        print("FAIL: --help did not expose expected commands", file=sys.stderr)
        return 1

    class4 = run(["class4", "--period", "2024-H2", "--limit", "1", "--json"], timeout=180)
    if class4.returncode == 2:
        data = parse_json_output(class4)
        if data.get("error") == "upstream_unavailable":
            print("SKIP: Class 4 upstream unavailable: " + data.get("message", ""))
        else:
            print(class4.stderr, file=sys.stderr)
            return 1
    elif class4.returncode != 0:
        print(class4.stdout)
        print(class4.stderr, file=sys.stderr)
        return 1
    else:
        data = json.loads(class4.stdout)
        assert data["kind"] == "class4_grants"
        assert "matched" in data and "totals" in data and "records" in data
        print(f"OK: class4 returned {data['returned']} of {data['matched']} matching rows")

    funds = run(["funds", "--limit", "3", "--json"], timeout=60)
    if funds.returncode == 2:
        data = parse_json_output(funds)
        if data.get("error") == "upstream_unavailable":
            print("SKIP: CommunityMatters upstream unavailable: " + data.get("message", ""))
            return 0
        print(funds.stderr, file=sys.stderr)
        return 1
    if funds.returncode != 0:
        print(funds.stdout)
        print(funds.stderr, file=sys.stderr)
        return 1
    data = json.loads(funds.stdout)
    assert data["kind"] == "fund_opportunities"
    assert isinstance(data["records"], list)
    print(f"OK: funds returned {data['count']} opportunities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
