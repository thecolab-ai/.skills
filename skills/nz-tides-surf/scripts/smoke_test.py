#!/usr/bin/env python3
"""Fixture checks for standard-port levels, plus bounded live reads."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURE = SKILL_DIR / "tests" / "fixtures" / "standard-port-tidal-levels.html"
REPO_ROOT = SKILL_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import nzfetch  # noqa: E402
import standard_port_levels as levels  # noqa: E402

HEADER = (
    "<table><tr><th>Standard Port</th><th>MHWS</th><th>MHWN</th><th>MLWN</th>"
    "<th>MLWS</th><th>Spring Range</th><th>Neap Range</th><th>MSL</th><th>HAT</th><th>LAT</th></tr>"
)
NOTES = """
<h2>Notes</h2>
<ol>
<li>The above levels, in metres, are referred to Chart Datum, which is the same as the zero of the tidal predictions in all cases.</li>
<li>The values for the MHWS, MHWN, MLWN and MLWS tidal levels given in the table are the averages of the levels of all spring and neap tides predicted for the period 1 July 2026 – 30 June 2027 using the harmonic constituents derived from the analysis of the observations made at that port.</li>
<li>The values for the spring and neap ranges have been deduced from the spring and neap tidal level values.</li>
<li>The value of MSL for each port has been derived from the analysis of tidal observations made at the port.</li>
<li>The values for HAT and LAT given in the table above are the highest and lowest tidal levels that are predicted to occur under average meteorological conditions during the period 1 January 2000 – 31 December 2018 using the harmonic constituents.</li>
<li>This table is not intended to be used for the determination of cadastral or administrative boundaries.</li>
</ol>
"""


def run(args: list[str], env: dict[str, str] | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=timeout,
        env=merged,
        check=False,
    )


def network_failure(result: subprocess.CompletedProcess[str]) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode in {4, 5}:
        return True
    markers = (
        "network error",
        "upstream unavailable",
        "timed out",
        "timeout",
        "blocked",
        "http 403",
        "http 406",
        "http 429",
        "http 451",
        "http 500",
        "http 502",
        "http 503",
    )
    return any(marker in text for marker in markers)


def load_cli():
    spec = importlib.util.spec_from_file_location("nz_tides_surf_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_error(fn, code: int) -> levels.LevelsError:
    try:
        fn()
    except levels.LevelsError as exc:
        if exc.code != code:
            raise AssertionError(f"expected exit {code}, got {exc.code}: {exc.message}") from exc
        return exc
    raise AssertionError(f"expected LevelsError {code}")


def test_prediction_csv_fixture() -> None:
    module = load_cli()
    csv_text = "Day,Weekday,Month,Year,Time,Height,Time,Height\n19,Sun,7,2026,03:15,0.4,09:30,1.8\n"
    records = module.parse_linz_csv(csv_text, "Synthetic Port", "https://www.linz.govt.nz/tides.csv")
    assert len(records) == 2
    assert records[0]["time_local"] == "03:15"
    assert records[0]["type"] == "low"
    assert records[1]["type"] == "high"
    assert records[1]["height_m"] == 1.8
    print("[PASS] fixture tide prediction CSV parser is unchanged")


def test_levels_fixture() -> None:
    document = levels.parse_levels_document(FIXTURE.read_text(encoding="utf-8"))
    rows = document["rows"]
    assert len(rows) == 16
    auckland = levels.select_ports(rows, "Auckland")[0]
    assert auckland["standard_port"] == "Auckland"
    assert auckland["unit"] == "m"
    assert auckland["datum"] == "Chart Datum"
    assert "zero of the tidal predictions" in auckland["datum_note"]
    assert auckland["mhws_m"] == 3.37
    assert auckland["mhwn_m"] == 2.82
    assert auckland["mlwn_m"] == 1.07
    assert auckland["mlws_m"] == 0.51
    assert auckland["spring_range_m"] == 2.86
    assert auckland["neap_range_m"] == 1.75
    assert auckland["msl_m"] == 1.94
    assert auckland["hat_m"] == 3.74
    assert auckland["lat_m"] == 0.1
    assert auckland["mhws_mhwn_mlwn_mlws_period"] == "1 July 2026 – 30 June 2027"
    assert auckland["hat_lat_period"] == "1 January 2000 – 31 December 2018"
    assert auckland["msl_observation_period"] is None
    assert auckland["msl_observation_period_page_fetched"] is False
    assert auckland["msl_observation_period_page"] == (
        "https://www.linz.govt.nz/guidance/marine-information/"
        "tide-prediction-guidance/standard-port-periods-observation"
    )
    assert auckland["observed_gauge_reading"] is False
    assert auckland["tide_prediction_event"] is False
    assert auckland["cadastral_or_administrative_boundary_use"] is False
    assert auckland["level_basis"]["msl"] == "derived from analysis of tidal observations"
    assert auckland["level_basis"]["mhws_mhwn_mlwn_mlws"] == "averages of predicted spring and neap tides"
    dunedin = levels.select_ports(rows, "dunedin")[0]
    assert dunedin["lat_m"] == -0.12
    onehunga = levels.select_ports(rows, "Onehunga")[0]
    assert onehunga["mhws_m"] == 4.18
    assert onehunga["standard_port"] != auckland["standard_port"]
    envelope = levels.build_envelope(
        levels.select_ports(rows, None),
        retrieved_at="2026-10-12T00:00:00Z",
        cached=False,
    )
    assert envelope["meta"]["source_url"] == levels.LEVELS_URL
    assert envelope["meta"]["publisher"] == levels.PUBLISHER
    assert envelope["meta"]["licence"].startswith("Creative Commons Attribution 4.0 International")
    assert "Chart Datum" in envelope["meta"]["latest_data"]
    assert "metres" in envelope["meta"]["latest_data"]
    assert len(envelope["results"]) == 16
    print("[PASS] fixture standard-port levels pin Auckland metres on Chart Datum")


def test_malformed_levels() -> None:
    empty = expect_error(lambda: levels.parse_levels_document("   "), 6)
    assert "empty" in empty.message
    missing_header = expect_error(
        lambda: levels.parse_levels_document("<table><tr><td>Auckland</td><td>1</td></tr></table>" + NOTES),
        6,
    )
    assert "not found" in missing_header.message
    no_rows = expect_error(lambda: levels.parse_levels_document(HEADER + "</table>" + NOTES), 6)
    assert "no port rows" in no_rows.message
    bad_number = expect_error(
        lambda: levels.parse_levels_document(
            HEADER + "<tr><td>Auckland</td><td>3.37a</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr></table>" + NOTES
        ),
        6,
    )
    assert "non-numeric" in bad_number.message
    duplicate = expect_error(
        lambda: levels.parse_levels_document(
            HEADER
            + "<tr><td>Auckland</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr>"
            + "<tr><td>Auckland</td><td>2</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr></table>"
            + NOTES
        ),
        6,
    )
    assert "duplicate" in duplicate.message
    no_datum = expect_error(
        lambda: levels.parse_levels_document(
            HEADER + "<tr><td>Auckland</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr></table><h2>Notes</h2><ol><li>No datum here.</li></ol>"
        ),
        6,
    )
    assert "Chart Datum" in no_datum.message
    print("[PASS] fixture malformed, empty, and undatumed levels fail closed")


def test_port_bounds_and_aliases() -> None:
    rows = levels.parse_levels_document(FIXTURE.read_text(encoding="utf-8"))["rows"]
    unknown = expect_error(lambda: levels.select_ports(rows, "Piha"), 2)
    assert "Surf-beach" in unknown.message
    assert unknown.code == 2
    called = {"n": 0}

    def boom() -> tuple[str, str]:
        called["n"] += 1
        raise AssertionError("bounds check fetched a page")

    for query in ("", "   ", "x" * 81, "https://www.linz.govt.nz/levels", "../auckland"):
        expect_error(lambda query=query: levels.load_levels_table(query, fetch=boom), 2)
    assert called["n"] == 0
    off_host = expect_error(
        lambda: levels.assert_official_levels_url("https://example.invalid/standard-port-tidal-levels"),
        5,
    )
    assert "network error" in off_host.message
    query_string = expect_error(
        lambda: levels.assert_official_levels_url(levels.LEVELS_URL + "?next=1"),
        5,
    )
    assert query_string.code == 5
    mapped = levels.map_fetch_error(nzfetch.FetchError("timed out talking to upstream"))
    assert mapped.code == 5 and "network error" in mapped.message
    limited = levels.map_fetch_error(nzfetch.RateLimited("http 429", retry_after="30"))
    assert limited.code == 4 and limited.retry_after == "30"
    payload = levels.error_payload(limited)
    assert payload["results"] == []
    assert payload["error"]["type"] == "blocked"
    assert payload["error"]["code"] == 4
    assert payload["error"]["retry_after"] == "30"
    source = Path(levels.__file__).read_text(encoding="utf-8")
    assert "tide-tables" not in source
    assert "data.linz.govt.nz" not in source
    assert ".zip" not in source
    print("[PASS] fixture levels bounds reject aliases, redirects, and gauge hosts")


def test_cache_reuses_table() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        previous_dir = os.environ.get("NZ_TIDES_SURF_LEVELS_CACHE_DIR")
        previous_flag = os.environ.get("NZ_TIDES_SURF_LEVELS_CACHE")
        os.environ["NZ_TIDES_SURF_LEVELS_CACHE_DIR"] = directory
        os.environ["NZ_TIDES_SURF_LEVELS_CACHE"] = "1"
        try:
            fresh_stamp = levels._stamp()
            levels._write_cache(html, fresh_stamp)
            calls = {"n": 0}

            def boom() -> tuple[str, str]:
                calls["n"] += 1
                raise AssertionError("fresh cache refetched the page")

            payload = levels.load_levels_table("Auckland", fetch=boom)
            assert calls["n"] == 0
            assert payload["meta"]["cached"] == "true"
            assert payload["meta"]["retrieved_at"] == fresh_stamp
            assert payload["results"][0]["mhws_m"] == 3.37
            assert len(payload["results"]) == 1
            stale = levels.cache_file()
            stale.write_text(
                json.dumps(
                    {
                        "source_url": levels.LEVELS_URL,
                        "retrieved_at": "2020-01-01T00:00:00Z",
                        "html": html,
                    }
                ),
                encoding="utf-8",
            )

            def fresh() -> tuple[str, str]:
                calls["n"] += 1
                return html, "2026-10-12T01:00:00Z"

            refreshed = levels.load_levels_table(None, fetch=fresh)
            assert calls["n"] == 1
            assert refreshed["meta"]["cached"] == "false"
            assert len(refreshed["results"]) == 16
        finally:
            if previous_dir is None:
                os.environ.pop("NZ_TIDES_SURF_LEVELS_CACHE_DIR", None)
            else:
                os.environ["NZ_TIDES_SURF_LEVELS_CACHE_DIR"] = previous_dir
            if previous_flag is None:
                os.environ.pop("NZ_TIDES_SURF_LEVELS_CACHE", None)
            else:
                os.environ["NZ_TIDES_SURF_LEVELS_CACHE"] = previous_flag
    print("[PASS] fixture levels cache reuses one table and refetches when stale")


def test_cli_fixture_envelope() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        cache = Path(directory) / "standard-port-tidal-levels.json"
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        cache.write_text(
            json.dumps(
                {
                    "source_url": levels.LEVELS_URL,
                    "retrieved_at": stamp,
                    "html": html,
                }
            ),
            encoding="utf-8",
        )
        env = {
            "NZ_TIDES_SURF_LEVELS_CACHE_DIR": directory,
            "NZ_TIDES_SURF_LEVELS_CACHE": "1",
        }
        listed = run(["levels", "--json"], env=env)
        assert listed.returncode == 0, listed.stderr
        payload = json.loads(listed.stdout)
        assert len(payload["results"]) == 16
        assert payload["results"][0]["unit"] == "m"
        assert payload["results"][0]["datum"] == "Chart Datum"
        one = run(["levels", "Auckland", "--json"], env=env)
        assert one.returncode == 0, one.stderr
        row = json.loads(one.stdout)["results"][0]
        assert row["mhws_m"] == 3.37
        assert row["tide_prediction_event"] is False
        assert row["observed_gauge_reading"] is False
        unknown = run(["levels", "Piha", "--json"], env=env)
        assert unknown.returncode == 2, unknown.stdout
        error = json.loads(unknown.stdout)
        assert error["results"] == []
        assert error["error"]["type"] == "invalid_input"
        assert error["error"]["code"] == 2
        huge = run(["levels", "x" * 81, "--json"], env=env)
        assert huge.returncode == 2
        assert json.loads(huge.stdout)["results"] == []
    help_result = run(["levels", "--help"])
    assert help_result.returncode == 0
    assert "Chart Datum" in help_result.stdout
    tides_help = run(["tides", "--help"])
    assert tides_help.returncode == 0
    assert "--date" in tides_help.stdout
    print("[PASS] fixture levels CLI envelope keeps predictions addressable")


def test_local_breaks() -> None:
    result = run(["breaks", "--json"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data.get("breaks"), list) and data["breaks"]
    print("[PASS] fixture surf break list still resolves")


def live_levels() -> str:
    env = {"NZ_TIDES_SURF_LEVELS_CACHE": "0"}
    result = run(["levels", "Auckland", "--json"], env=env, timeout=20)
    if network_failure(result):
        print("[SKIP] live levels Auckland: network error: upstream unavailable")
        print(result.stderr[-400:])
        return "skip"
    if result.returncode != 0:
        print("[FAIL] live levels Auckland returned a non-network error")
        print(result.stderr[-400:])
        print(result.stdout[-400:])
        return "fail"
    payload = json.loads(result.stdout)
    row = payload["results"][0]
    required = ("mhws_m", "mhwn_m", "mlwn_m", "mlws_m", "spring_range_m", "neap_range_m", "msl_m", "hat_m", "lat_m")
    if row.get("standard_port") != "Auckland" or row.get("unit") != "m" or row.get("datum") != "Chart Datum":
        print("[FAIL] live levels Auckland lost the published port, unit, or datum")
        return "fail"
    if any(not isinstance(row.get(field), (int, float)) for field in required):
        print("[FAIL] live levels Auckland did not return numeric level columns")
        return "fail"
    if payload["meta"].get("source_url") != levels.LEVELS_URL:
        print("[FAIL] live levels source_url was not the official table")
        return "fail"
    if "Creative Commons Attribution 4.0 International" not in payload["meta"].get("licence", ""):
        print("[FAIL] live levels licence was not the verified CC BY 4.0 statement")
        return "fail"
    if row.get("msl_observation_period_page_fetched") is not False:
        print("[FAIL] live levels fetched the observation-period page")
        return "fail"
    print("[PASS] live levels Auckland has nine numeric columns on Chart Datum")
    return "pass"


def live_prediction() -> str:
    result = run(["next-tide", "Wellington", "--json"], timeout=30)
    if network_failure(result):
        print("[SKIP] live next-tide Wellington: network error: upstream unavailable")
        return "skip"
    if result.returncode != 0:
        print("[FAIL] live next-tide Wellington returned a non-network error")
        print(result.stderr[-300:])
        return "fail"
    data = json.loads(result.stdout)
    if not data.get("next_high") and not data.get("next_low"):
        print("[FAIL] live next-tide Wellington had no prediction event")
        return "fail"
    print("[PASS] live next-tide Wellington still returns a prediction")
    return "pass"


def main() -> int:
    fixtures = (
        test_prediction_csv_fixture,
        test_levels_fixture,
        test_malformed_levels,
        test_port_bounds_and_aliases,
        test_cache_reuses_table,
        test_cli_fixture_envelope,
        test_local_breaks,
    )
    try:
        for test in fixtures:
            test()
    except Exception as exc:
        print(f"[FAIL] fixture {type(exc).__name__}: {exc}")
        return 1
    levels_state = live_levels()
    prediction_state = live_prediction()
    if "fail" in {levels_state, prediction_state}:
        return 1
    if levels_state == "skip":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
