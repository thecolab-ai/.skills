#!/usr/bin/env python3
"""Fixture contracts plus bounded live probes. Upstream outages skip, parser failures do not."""
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]
DAILY_NAME = re.compile(r"^[A-Z][A-Z0-9]{3}_[1-9][0-9]?_[0-9]{4}[0-9]{3}\.zip$")
TIMEOUT = "20"


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


def unpublished_utc_day(published: set[str], today: date) -> str:
    """Pick a UTC day this listing does not contain.

    A gap inside the published span was already skipped, so a later run cannot
    fill it during this probe. A day after the span, including 31 December of
    the open year, can be published later. When there is no gap, use 1 January
    two years after the later of today and the newest published day.
    """
    parsed = sorted(date.fromisoformat(value) for value in published if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value))
    if parsed:
        have = set(parsed)
        day = parsed[0]
        while day <= parsed[-1]:
            if day not in have:
                return day.isoformat()
            day += timedelta(days=1)
        anchor = max(parsed[-1], today)
    else:
        anchor = today
    year = anchor.year + 2
    if year < 1990:
        year = 1990
    if year > 2100:
        year = 2100
    candidate = date(year, 1, 1)
    if candidate.isoformat() not in published:
        return candidate.isoformat()
    for probe_year in (year, year - 1):
        if probe_year < 1990:
            continue
        start = date(probe_year, 1, 1)
        for offset in range(366):
            probe = start + timedelta(days=offset)
            if probe.year != probe_year:
                break
            if probe.isoformat() not in published:
                return probe.isoformat()
    raise RuntimeError("no unpublished UTC day inside 1990-2100")


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
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


def expect_historical(
    arguments: list[str],
    label: str,
    *,
    gauge: str,
    day: str,
    sensor: str,
    zip_name: str,
    height: str,
    matched: int,
) -> None:
    payload = live_json(arguments, label)
    if payload is None:
        return
    meta = payload["meta"]
    assert meta["retrieval_kind"] == "live" and meta["query_status"] == "ok"
    assert meta["height_reference"] == "gauge zero (TG0)"
    assert meta["sensor_origin"] == "archive_name" and meta["sensor_verified"] is True
    assert meta["latest_data"] == f"{day}T23:59:00Z"
    assert meta["matched_count"] == matched and meta["truncated"] is True
    assert meta["source_url"].endswith("/" + zip_name)
    assert not meta["source_url"].endswith(f"/{gauge}_{sensor}_{day[:4]}.zip")
    assert payload["results"][0] == {
        "gauge": gauge,
        "sensor": sensor,
        "observed_at": f"{day}T00:00:00Z",
        "height_m": height,
    }
    print(f"[PASS] live {label} reads the daily zip")


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
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "40", "--limit", "2", "--timeout", TIMEOUT],
        "AUCT 2026-01-01 sensor 40 readings",
    )
    if readings is not None:
        assert readings["meta"]["retrieval_kind"] == "live"
        assert readings["meta"]["observation_time"] == "UTC"
        assert readings["meta"]["height_reference"] == "gauge zero (TG0)"
        assert readings["meta"]["quality_control"] == "unquality-controlled"
        assert readings["meta"]["sensor_origin"] == "archive_name" and readings["meta"]["sensor_verified"] is True
        assert readings["meta"]["latest_data"] == "2026-01-01T23:59:00Z"
        assert readings["meta"]["matched_count"] == 1440 and readings["meta"]["truncated"] is True
        assert readings["meta"]["source_url"].endswith("/AUCT_40_2026001.zip")
        assert "3.0" in readings["meta"]["licence"]
        assert readings["results"][0]["observed_at"] == "2026-01-01T00:00:00Z"
        assert readings["results"][0]["height_m"] == "5.002"
        assert len(readings["results"]) == 2
        print("[PASS] live AUCT readings keep the UTC day and full-file latest minute")

    other_sensor = live_json(
        ["readings", "--gauge", "AUCT", "--date", "2026-01-01", "--sensor", "41", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2026-01-01 sensor 41 readings",
    )
    if other_sensor is not None:
        assert other_sensor["results"][0]["height_m"] == "4.777"
        assert other_sensor["results"][0]["height_m"] != "5.002"
        assert other_sensor["meta"]["height_reference"] == "gauge zero (TG0)"
        assert "separate series" in other_sensor["meta"]["series_note"]
        assert other_sensor["meta"]["source_url"].endswith("/AUCT_41_2026001.zip")
        print("[PASS] live AUCT sensor 41 is a separate series from sensor 40")

    files = live_json(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2026 sensor 40 files",
    )
    if files is not None:
        assert files["meta"]["truncated"] is True and files["meta"]["matched_count"] > 1
        assert files["results"][0]["utc_date"] == "2026-01-01"
        assert DAILY_NAME.fullmatch(files["results"][0]["name"])
        assert files["results"][0]["size"] <= 2_000_000
        assert "not an observation time" in files["meta"]["latest_data_meaning"]
        print("[PASS] live file page is bounded and modified dates stay dates")

    full_year = live_json(
        ["files", "--gauge", "AUCT", "--year", "2026", "--sensor", "40", "--limit", "366", "--timeout", TIMEOUT],
        "AUCT 2026 full daily listing",
    )
    if full_year is not None:
        assert full_year["meta"]["truncated"] is False
        assert full_year["meta"]["matched_count"] == len(full_year["results"])
        published = set()
        for row in full_year["results"]:
            assert DAILY_NAME.fullmatch(row["name"])
            assert row["size"] <= 2_000_000
            published.add(row["utc_date"])
        for bundle in full_year["meta"].get("archive_bundles", []):
            assert bundle["kind"] in {"annual", "part_year"}
            assert bundle["name"] not in {row["name"] for row in full_year["results"]}
        missing_day = unpublished_utc_day(published, date.today())
        assert missing_day not in published
        missing = live_json(
            ["readings", "--gauge", "AUCT", "--date", missing_day, "--sensor", "40", "--timeout", TIMEOUT],
            f"AUCT unpublished UTC day {missing_day}",
        )
        if missing is not None:
            assert missing["results"] == [] and missing["meta"]["query_status"] == "no_match" and "error" not in missing
            print("[PASS] live unpublished UTC day is an empty match, not an outage")

    past_files = live_json(
        ["files", "--gauge", "AUCT", "--year", "2025", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2025 files",
    )
    if past_files is not None:
        assert past_files["results"][0]["name"] == "AUCT_40_2025001.zip"
        assert past_files["results"][0]["size"] <= 2_000_000
        bundles = past_files["meta"]["archive_bundles"]
        assert any(bundle["kind"] == "annual" and bundle["name"] == "AUCT_40_2025.zip" and bundle["size"] > 2_000_000 for bundle in bundles)
        assert all(DAILY_NAME.fullmatch(row["name"]) for row in past_files["results"])
        print("[PASS] live AUCT 2025 annual bundle stays out of the daily page")

    expect_historical(
        ["readings", "--gauge", "AUCT", "--date", "2025-06-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2025-06-01 sensor 40",
        gauge="AUCT",
        day="2025-06-01",
        sensor="40",
        zip_name="AUCT_40_2025152.zip",
        height="6.346",
        matched=1440,
    )
    expect_historical(
        ["readings", "--gauge", "AUCT", "--date", "2009-12-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2009-12-01 sensor 40",
        gauge="AUCT",
        day="2009-12-01",
        sensor="40",
        zip_name="AUCT_40_2009335.zip",
        height="4.369",
        matched=1440,
    )
    expect_historical(
        ["readings", "--gauge", "AUCT", "--date", "2012-08-28", "--sensor", "41", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2012-08-28 sensor 41",
        gauge="AUCT",
        day="2012-08-28",
        sensor="41",
        zip_name="AUCT_41_2012241.zip",
        height="4.813",
        matched=1260,
    )
    expect_historical(
        ["readings", "--gauge", "WLGT", "--date", "2015-01-01", "--sensor", "41", "--limit", "1", "--timeout", TIMEOUT],
        "WLGT 2015-01-01 sensor 41",
        gauge="WLGT",
        day="2015-01-01",
        sensor="41",
        zip_name="WLGT_41_2015001.zip",
        height="3.603",
        matched=1440,
    )

    unknown = live_json(["datasets", "--gauge", "ZZZZ", "--timeout", TIMEOUT], "unknown gauge")
    if unknown is not None:
        assert unknown["results"] == [] and unknown["meta"]["query_status"] == "no_match" and "error" not in unknown
        print("[PASS] live unknown gauge is an empty match, not an outage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
