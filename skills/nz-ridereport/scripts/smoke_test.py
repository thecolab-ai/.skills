#!/usr/bin/env python3
"""Fixture assertions plus a bounded Auckland Ride Report live probe."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]
VEHICLE = "scooter"
PERIOD = "2026-Q3"
METRICS_URL = (
    "https://public-data-exports-production.s3-us-west-2.amazonaws.com/"
    "auckland/data-export/scooter/2026-Q3/trip_metrics.json"
)
NETWORK_MARKERS = (
    "network error",
    "upstream unavailable",
    "timed out",
    "rate_limited",
    "http 429",
    "http 503",
    "http 403",
    "name or service not known",
    "temporary failure",
)


def run(arguments: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_checks() -> None:
    code, stdout, stderr = run(
        ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--fixture", "catalogue-ok", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr)
    require(payload["results"][0]["total_trip_count"] == 60, "fixture total changed")
    require("series" not in payload["results"][0], "fixture summary included a series")
    require(payload["meta"]["publisher"] == "Ride Report", "publisher changed")
    print("[PASS] fixture aggregate summary keeps the synthetic trip total and omits the series")

    code, stdout, _stderr = run(
        ["metrics", "--vehicle", "../scooter", "--period", PERIOD, "--json"]
    )
    payload = json.loads(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", "traversal token was accepted")
    require("Traceback" not in stdout, "traversal token traced")
    print("[PASS] fixture traversal vehicle token is invalid_input")

    code, stdout, _stderr = run(
        ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--fixture", "metrics-malformed", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", "malformed JSON was accepted")
    print("[PASS] fixture malformed metrics JSON is schema_failure")

    code, stdout, _stderr = run(
        ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--fixture", "metrics-absent", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and payload["results"] == [], "absent export was not empty")
    require(any("no_export" in item for item in payload.get("warnings", [])), payload.get("warnings"))
    print("[PASS] fixture absent export is an empty no_export success")

    code, stdout, _stderr = run(
        ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--fixture", "metrics-off-host", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host fixture was followed")
    print("[PASS] fixture off-host redirect is refused")

    code, stdout, _stderr = run(
        ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--series", "trips", "--limit", "2", "--fixture", "catalogue-ok", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and len(payload["results"][0]["series"]) == 2, "fixture series limit failed")
    print("[PASS] fixture series limit keeps two source-order buckets")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def live_checks() -> int:
    calls = (
        ("dashboard", ["dashboard", "--json"]),
        ("summary", ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--json"]),
        ("series", ["metrics", "--vehicle", VEHICLE, "--period", PERIOD, "--series", "trips", "--limit", "2", "--json"]),
        ("human", ["metrics", "--vehicle", VEHICLE, "--period", PERIOD]),
        ("unpublished", ["metrics", "--vehicle", VEHICLE, "--period", "1999-Q1", "--json"]),
    )
    outputs: dict[str, tuple[int, str, str]] = {}
    for name, arguments in calls:
        try:
            code, stdout, stderr = run(arguments)
        except subprocess.TimeoutExpired:
            print("[SKIP] live probe skipped: network error: source request timed out")
            return 0
        if transport_failure(code, stdout, stderr):
            print("[SKIP] live probe skipped: upstream unavailable or rate limited")
            return 0
        outputs[name] = (code, stdout, stderr)
    try:
        dashboard_code, dashboard_out, _dashboard_err = outputs["dashboard"]
        summary_code, summary_out, _summary_err = outputs["summary"]
        series_code, series_out, _series_err = outputs["series"]
        human_code, human_out, human_err = outputs["human"]
        unpublished_code, unpublished_out, _unpublished_err = outputs["unpublished"]

        dashboard = json.loads(dashboard_out)
        require(dashboard_code == 0 and dashboard["results"], dashboard_out[:500])
        record = dashboard["results"][0]
        require("Auckland" in record["name"], record.get("name"))
        require(isinstance(record["population"], int) and record["population"] > 1000000, record.get("population"))
        require(record["operators"] and all(isinstance(item, str) and item.strip() for item in record["operators"]), record.get("operators"))
        scooter = next(item for item in record["vehicles"] if item["vehicle"] == VEHICLE)
        require(any(item["key"] == PERIOD for item in scooter["periods"]), "live catalogue omitted 2026-Q3")
        require(dashboard["meta"]["licence"].find("public.ridereport.com") >= 0, "live licence omitted the required link")
        print("[PASS] live dashboard listed Auckland, a population over one million, and scooter 2026-Q3")

        summary = json.loads(summary_out)
        require(summary_code == 0 and summary["results"], summary_out[:500])
        metrics = summary["results"][0]
        require(metrics["vehicle"] == VEHICLE and metrics["period"] == PERIOD, metrics)
        require(isinstance(metrics["total_trip_count"], int) and metrics["total_trip_count"] > 100000, metrics.get("total_trip_count"))
        require(metrics["average_trip_speed_metres_per_second"] > 0, metrics.get("average_trip_speed_metres_per_second"))
        require("series" not in metrics, "live summary dumped a series")
        require(summary["meta"]["source_url"] == METRICS_URL, summary["meta"].get("source_url"))
        require(summary["meta"]["latest_data"] == "2026-09-30", summary["meta"].get("latest_data"))
        require(summary["meta"]["publisher"] == "Ride Report", summary["meta"].get("publisher"))
        print("[PASS] live scooter 2026-Q3 summary returned a six-figure trip total ending 2026-09-30")

        series = json.loads(series_out)
        require(series_code == 0 and len(series["results"][0]["series"]) == 2, series_out[:500])
        first = series["results"][0]["series"][0]
        require(first["x"] == "2026-07-01" and isinstance(first["y"], int) and first["y"] > 0, first)
        require(any("truncated" in item for item in series.get("warnings", [])), series.get("warnings"))
        print("[PASS] live trip series kept two buckets beginning 2026-07-01 and reported truncation")

        require(human_code == 0 and "Ride Report" in human_out and "Total trips" in human_out, human_out[:500])
        require("Traceback" not in human_err and "public.ridereport.com" in human_out, human_err)
        print("[PASS] live human metrics named Ride Report and the public dashboard link")

        unpublished = json.loads(unpublished_out)
        require(unpublished_code == 2 and unpublished["error"]["type"] == "invalid_input", unpublished_out[:500])
        require("not published" in unpublished["error"]["message"], unpublished["error"].get("message"))
        print("[PASS] live unpublished period 1999-Q1 was rejected from the catalogue")
    except (AssertionError, json.JSONDecodeError, KeyError, StopIteration) as exc:
        print(f"[FAIL] live probe {exc}")
        return 1
    return 0


def main() -> int:
    try:
        fixture_checks()
    except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    return live_checks()


if __name__ == "__main__":
    raise SystemExit(main())
