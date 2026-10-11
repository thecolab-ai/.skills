#!/usr/bin/env python3
"""Fixture contracts plus bounded live probes. Upstream outages skip, parser failures do not."""
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]


def run_fixture_checks() -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("test_contract.py"))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        print("[FAIL] fixture contract tests failed")
        print(completed.stdout[-2000:])
        print(completed.stderr[-1000:])
        raise SystemExit(1)
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert "parser_fixtures" in payload["checks"]
    print("[PASS] fixture UTC minute heights, empty files, duplicates, and bounds")


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )


def live_json(arguments: list[str], label: str) -> dict | None:
    try:
        completed = run_cli([*arguments, "--json"])
    except subprocess.TimeoutExpired:
        print(f"[SKIP] live {label}: network error: probe timed out")
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] live {label}: response was not JSON")
        raise SystemExit(1)
    if completed.returncode in (4, 5):
        message = payload.get("error", {}).get("message", "")
        assert payload["results"] == []
        assert "network error" in message
        print(f"[SKIP] live {label}: {message}")
        return None
    if completed.returncode != 0 or completed.stderr:
        print(f"[FAIL] live {label}: exit {completed.returncode} {completed.stderr or payload}")
        raise SystemExit(1)
    return payload


def main() -> int:
    run_fixture_checks()
    human = run_cli(["gauges"])
    if human.returncode in (4, 5) or "network error" in (human.stderr + human.stdout):
        print(f"[SKIP] live human gauges: network error: {human.stderr.strip() or human.stdout.strip()}")
    else:
        assert human.returncode == 0, human.stderr
        assert "AUCT" in human.stdout
        assert not human.stdout.lstrip().startswith("{")
        print("[PASS] live human gauges lists AUCT")

    readings = live_json(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--limit", "2"],
        "AUCT 2026-01-01 readings",
    )
    if readings is not None:
        assert readings["meta"]["retrieval_kind"] == "live"
        assert readings["meta"]["observation_time"] == "UTC"
        assert readings["meta"]["latest_data"] == "2026-01-01T23:59:00Z"
        assert readings["meta"]["matched_count"] == 1440 and readings["meta"]["truncated"] is True
        assert readings["meta"]["source_url"].endswith("/AUCT_40_2026001.zip")
        assert "3.0" in readings["meta"]["licence"]
        assert readings["results"][0]["observed_at"] == "2026-01-01T00:00:00Z"
        assert readings["results"][0]["height_m"] == "5.002"
        assert len(readings["results"]) == 2
        print("[PASS] live AUCT readings keep the UTC day and full-file latest minute")

    files = live_json(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--limit", "1"],
        "AUCT 2026 sensor 40 files",
    )
    if files is not None:
        assert files["meta"]["truncated"] is True and files["meta"]["matched_count"] > 1
        assert files["results"][0]["utc_date"] == "2026-01-01"
        assert "not an observation time" in files["meta"]["latest_data_meaning"]
        print("[PASS] live file page is bounded and modified dates stay dates")

    missing = live_json(
        ["readings", "--gauge", "AUCT", "--date", "2026-12-31", "--sensor", "40"],
        "AUCT unpublished UTC day",
    )
    if missing is not None:
        assert missing["results"] == [] and missing["meta"]["query_status"] == "no_match" and "error" not in missing
        print("[PASS] live unpublished UTC day is an empty match, not an outage")

    unknown = live_json(["datasets", "--gauge", "ZZZZ"], "unknown gauge")
    if unknown is not None:
        assert unknown["results"] == [] and unknown["meta"]["query_status"] == "no_match" and "error" not in unknown
        print("[PASS] live unknown gauge is an empty match, not an outage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
