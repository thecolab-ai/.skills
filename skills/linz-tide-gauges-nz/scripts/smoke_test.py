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
DAILY_NAME = re.compile(r"^[A-Z][A-Z0-9]{3}_(?:00|[1-9][0-9]?)_[0-9]{4}[0-9]{3}\.zip$")
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


def expect_window(
    arguments: list[str],
    label: str,
    *,
    gauge: str,
    sensor: str,
    zip_name: str,
    first_at: str,
    first_height: str,
    latest: str,
    matched: int,
    dates: list[str],
    clock: str = "UTC",
    extra: dict[str, str] | None = None,
) -> None:
    payload = live_json(arguments, label)
    if payload is None:
        return
    meta = payload["meta"]
    assert meta["retrieval_kind"] == "live" and meta["query_status"] == "ok" and meta["observation_time"] == clock
    assert meta["archive_date"] == arguments[arguments.index("--date") + 1]
    assert meta["observation_dates"] == dates and meta["latest_data"] == latest and meta["matched_count"] == matched
    assert meta["source_url"].endswith("/" + zip_name)
    assert not meta["source_url"].endswith(f"/{gauge}_{sensor}_{arguments[arguments.index('--date') + 1][:4]}.zip")
    if len(dates) > 1:
        assert meta["observation_window"]["first_observed_at"] == first_at
        assert meta["observation_window"]["last_observed_at"] == latest
        assert meta["observation_window"]["observation_dates"] == dates
    else:
        assert "observation_window" not in meta
    row = payload["results"][0]
    assert row["gauge"] == gauge and row["sensor"] == sensor and row["observed_at"] == first_at and row["height_m"] == first_height
    for key, value in (extra or {}).items():
        assert row[key] == value
    print(f"[PASS] live {label}")


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

    expect_window(
        ["readings", "--gauge", "AUCT", "--date", "2020-06-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2020-06-01 sensor 40 spans into the next UTC day",
        gauge="AUCT",
        sensor="40",
        zip_name="AUCT_40_2020153.zip",
        first_at="2020-06-01T23:54:00Z",
        first_height="4.736",
        latest="2020-06-02T23:53:00Z",
        matched=1440,
        dates=["2020-06-01", "2020-06-02"],
    )
    expect_window(
        ["readings", "--gauge", "AUCT", "--date", "2020-01-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "AUCT 2020-01-01 sensor 40 spans the previous UTC year",
        gauge="AUCT",
        sensor="40",
        zip_name="AUCT_40_2020001.zip",
        first_at="2019-12-31T23:54:00Z",
        first_height="6.29",
        latest="2020-01-01T23:53:00Z",
        matched=1440,
        dates=["2019-12-31", "2020-01-01"],
    )
    expect_window(
        ["readings", "--gauge", "WLGT", "--date", "2020-06-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "WLGT 2020-06-01 sensor 40 spans into the next UTC day",
        gauge="WLGT",
        sensor="40",
        zip_name="WLGT_40_2020153.zip",
        first_at="2020-06-01T23:54:00Z",
        first_height="3.438",
        latest="2020-06-02T23:53:00Z",
        matched=1440,
        dates=["2020-06-01", "2020-06-02"],
    )
    expect_window(
        ["readings", "--gauge", "LOTT", "--date", "2020-06-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "LOTT 2020-06-01 sensor 40 spans into the next UTC day",
        gauge="LOTT",
        sensor="40",
        zip_name="LOTT_40_2020153.zip",
        first_at="2020-06-01T23:54:00Z",
        first_height="3.335",
        latest="2020-06-02T23:53:00Z",
        matched=1440,
        dates=["2020-06-01", "2020-06-02"],
    )
    expect_window(
        ["readings", "--gauge", "CHIT", "--date", "2020-01-01", "--sensor", "40", "--limit", "1", "--timeout", TIMEOUT],
        "CHIT 2020-01-01 sensor 40 spans the previous UTC year",
        gauge="CHIT",
        sensor="40",
        zip_name="CHIT_40_2020001.zip",
        first_at="2019-12-31T23:54:00Z",
        first_height="2.937",
        latest="2020-01-01T23:53:00Z",
        matched=1440,
        dates=["2019-12-31", "2020-01-01"],
    )
    for gauge in ("SCOT", "ROBT"):
        datasets = live_json(["datasets", "--gauge", gauge, "--timeout", TIMEOUT], f"{gauge} sensor 00 datasets")
        if datasets is not None:
            assert datasets["meta"]["query_status"] == "ok" and datasets["results"]
            assert {row["sensor"] for row in datasets["results"]} == {"00"}
            print(f"[PASS] live {gauge} datasets keep sensor 00")
    expect_window(
        ["readings", "--gauge", "SCOT", "--date", "2020-06-01", "--sensor", "00", "--limit", "1", "--timeout", TIMEOUT],
        "SCOT 2020-06-01 sensor 00",
        gauge="SCOT",
        sensor="00",
        zip_name="SCOT_00_2020153.zip",
        first_at="2020-06-01T00:00:00+12:00",
        first_height="2.144",
        latest="2020-06-01T23:55:00+12:00",
        matched=288,
        dates=["2020-06-01"],
        clock="NZST",
    )
    expect_window(
        ["readings", "--gauge", "ROBT", "--date", "2015-06-01", "--sensor", "00", "--limit", "1", "--timeout", TIMEOUT],
        "ROBT 2015-06-01 sensor 00",
        gauge="ROBT",
        sensor="00",
        zip_name="ROBT_00_2015152.zip",
        first_at="2015-06-01T00:05:00Z",
        first_height="6.182",
        latest="2015-06-02T00:00:00Z",
        matched=288,
        dates=["2015-06-01", "2015-06-02"],
        extra={"sample_count": "30", "sea_temperature_c": "-2.234", "pressure_hpa": "1002.8"},
    )
    scot_2024 = live_json(
        ["files", "--gauge", "SCOT", "--year", "2024", "--sensor", "00", "--limit", "5", "--timeout", TIMEOUT],
        "SCOT 2024 sensor 00 files",
    )
    if scot_2024 is not None:
        assert scot_2024["results"] == [] and scot_2024["meta"]["matched_count"] == 0
        assert any(bundle["kind"] == "annual" and bundle["name"] == "SCOT_00_2024.zip" for bundle in scot_2024["meta"]["archive_bundles"])
        print("[PASS] live SCOT 2024 directory placeholder stays out of the daily page")
    scot_2026 = live_json(
        ["files", "--gauge", "SCOT", "--year", "2026", "--sensor", "00", "--limit", "5", "--timeout", TIMEOUT],
        "SCOT 2026 sensor 00 files",
    )
    if scot_2026 is not None:
        assert scot_2026["results"] == []
        assert any(
            bundle["kind"] == "month_span" and bundle["name"] == "SCOT_00_2026_01-03.zip" and bundle["month_start"] == "01" and bundle["month_end"] == "03"
            for bundle in scot_2026["meta"]["archive_bundles"]
        )
        print("[PASS] live SCOT 2026 month bundle is labeled and not a daily file")
    missing_bundle = live_json(
        ["readings", "--gauge", "ROBT", "--date", "2020-06-01", "--sensor", "00", "--timeout", TIMEOUT],
        "ROBT 2020-06-01 sensor 00 without a daily zip",
    )
    if missing_bundle is not None:
        assert missing_bundle["results"] == [] and missing_bundle["meta"]["query_status"] == "no_match" and "error" not in missing_bundle
        assert not missing_bundle["meta"]["source_url"].endswith("/ROBT_00_2020.zip")
        print("[PASS] live ROBT annual-only year is an empty match")

    unknown = live_json(["datasets", "--gauge", "ZZZZ", "--timeout", TIMEOUT], "unknown gauge")
    if unknown is not None:
        assert unknown["results"] == [] and unknown["meta"]["query_status"] == "no_match" and "error" not in unknown
        print("[PASS] live unknown gauge is an empty match, not an outage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
