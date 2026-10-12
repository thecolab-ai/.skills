#!/usr/bin/env python3
"""Fixture assertions plus one bounded live probe of Paris permanent counters."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]

NETWORK_MARKERS = (
    "network error",
    "upstream unavailable",
    "timed out",
    "rate_limited",
    "http 429",
    "http 503",
    "name or service not known",
    "temporary failure",
)


def run(arguments: list[str], timeout: int = 20) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def payload_of(code: int, stdout: str, stderr: str, expected: int) -> dict:
    require(code == expected, f"exit {code}, expected {expected}: {stderr or stdout[:400]}")
    require("Traceback" not in stdout and "Traceback" not in stderr, stderr or stdout[:400])
    require(stderr == "", stderr)
    return json.loads(stdout)


def fixture_checks() -> None:
    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-positive", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    row = body["results"][0]
    require(row["iu_ac"] == "900001", row["iu_ac"])
    require(row["q_vehicles_per_hour"] == 100 and row["q_observed"] is True, row["q_vehicles_per_hour"])
    require(row["k_occupancy_percent"] == 10 and row["k_observed"] is True, row["k_occupancy_percent"])
    require(row["t_1h"] == "2026-01-15T08:00:00+01:00", row["t_1h"])
    require(row["derived_period_start"] == "2026-01-15T07:00:00+01:00", row["derived_period_start"])
    require(row["direction"] == "Noeud_amont -> Noeud_aval", row["direction"])
    require(body["meta"]["licence"].startswith("Open Database License (ODbL) "), body["meta"]["licence"])
    require("opendatacommons.org/licenses/odbl" in body["meta"]["licence"], body["meta"]["licence"])
    require(body["meta"]["latest_data"] == "2026-01-15T01:02:03+00:00", body["meta"]["latest_data"])
    require("not zero" in " ".join(body["warnings"]), body["warnings"])
    require("Share-alike" in " ".join(body["warnings"]), body["warnings"])
    require("total_vehicles" not in row, "fixture invented a summed total")
    print("[PASS] fixture positive arc-hour keeps flow, occupancy, and the Paris hour-ending stamp")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-occupancy-only"])
    require(code == 0 and stderr == "", stderr)
    require("unobserved (not zero)" in stdout, stdout)
    require("flow q: 0" not in stdout and "0 vehicles" not in stdout, stdout)
    require("Pré-saturé" in stdout, stdout)
    print("[PASS] fixture occupancy-only station does not print a zero flow")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-empty", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    require(body["results"] == [], body["results"])
    require(any("matched 0 arc-hours" in item for item in body["warnings"]), body["warnings"])
    print("[PASS] fixture empty match stays an empty result")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-invalid-arc", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    row = body["results"][0]
    require(row["q_vehicles_per_hour"] is None and row["k_occupancy_percent"] is None, row)
    require(row["q_observed"] is False and row["etat_trafic"] == "Inconnu", row)
    require(row["etat_barre"] == "Invalide", row["etat_barre"])
    require(any("not marked Ouvert" in item for item in body["warnings"]), body["warnings"])
    print("[PASS] fixture invalid arc keeps null measurements and the closure label")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-band-mismatch", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    row = body["results"][0]
    require(row["k_occupancy_percent"] == 60 and row["etat_trafic"] == "Fluide", row)
    require(any("outside the published band" in item for item in body["warnings"]), body["warnings"])
    print("[PASS] fixture occupancy band disagreement preserves both source values")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-reference-date", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    row = body["results"][0]
    require(row["t_1h"] == "2026-01-15T08:00:00+01:00", row["t_1h"])
    require(row["reference_date_fin_before_observation"] is True, row)
    require(any("date_fin" in item for item in body["warnings"]), body["warnings"])
    print("[PASS] fixture earlier date_fin does not relabel t_1h")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "counts-midnight", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    row = body["results"][0]
    require(row["t_1h"] == "2026-10-11T00:00:00+02:00", row["t_1h"])
    require(row["derived_period_start"] == "2026-10-10T23:00:00+02:00", row["derived_period_start"])
    print("[PASS] fixture midnight hour-ending belongs to the previous Paris evening")

    code, stdout, stderr = run(
        ["counts", "--limit", "1", "--format", "geojson", "--fixture", "counts-positive"]
    )
    body = payload_of(code, stdout, stderr, 0)
    feature = body["features"][0]
    require(body["type"] == "FeatureCollection", body["type"])
    require(feature["geometry"]["coordinates"][0] == [2.35, 48.86], feature["geometry"])
    require(feature["properties"]["lon"] == 2.35 and feature["properties"]["lat"] == 48.86, feature["properties"])
    require("ODbL" in body["meta"]["licence"], body["meta"])
    print("[PASS] fixture GeoJSON keeps longitude then latitude")

    code, stdout, stderr = run(
        [
            "counts",
            "--limit",
            "1",
            "--bbox=2.35,48.85,2.36,48.86",
            "--from",
            "2026-01-01T00:00:00",
            "--to",
            "2026-01-02T23:00:00",
            "--fixture",
            "counts-positive",
            "--json",
        ]
    )
    body = payload_of(code, stdout, stderr, 0)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(body["meta"]["source_url"]).query)
    where = query["where"][0]
    require("in_bbox(geo_point_2d, 48.85, 2.35, 48.86, 2.36)" in where, where)
    require("t_1h>=date'2026-01-01T00:00:00'" in where and "t_1h<=date'2026-01-02T23:00:00'" in where, where)
    require(query["timezone"] == ["Europe/Paris"], query["timezone"])
    require(query["limit"] == ["1"], query["limit"])
    require(body["meta"]["source_url"].startswith("https://opendata.paris.fr/"), body["meta"]["source_url"])
    print("[PASS] fixture bbox query uses south, west, north, east on the Paris host")

    failures = (
        (["counts", "--limit", "1", "--fixture", "counts-missing-hour", "--json"], 6, "missing t_1h"),
        (["counts", "--limit", "1", "--fixture", "counts-naive-time", "--json"], 6, "naive t_1h"),
        (["counts", "--limit", "1", "--fixture", "counts-bool-flow", "--json"], 6, "boolean q"),
        (["counts", "--limit", "1", "--fixture", "counts-inconsistent", "--json"], 6, "inconsistent total"),
        (["counts", "--limit", "1", "--fixture", "counts-over-limit", "--json"], 6, "over limit"),
        (["counts", "--limit", "1", "--fixture", "transport-malformed", "--json"], 6, "malformed JSON"),
        (["counts", "--limit", "1", "--fixture", "transport-truncated", "--json"], 6, "truncated JSON"),
        (["counts", "--limit", "1", "--fixture", "metadata-missing-licence", "--json"], 6, "missing licence"),
        (["counts", "--limit", "21", "--json"], 2, "huge limit"),
        (["counts", "--limit", "1", "--arc", "abc", "--json"], 2, "bad arc"),
        (["counts", "--limit", "1", "--from", "2026-01-03T00:00:00", "--to", "2026-01-01T00:00:00", "--json"], 2, "reversed window"),
        (["counts", "--limit", "1", "--from", "2026-01-01T00:00:00", "--to", "2026-01-03T00:00:00", "--json"], 2, "long window"),
        (["counts", "--limit", "1", "--bbox=2.36,48.86,2.35,48.85", "--json"], 2, "reversed bbox"),
    )
    for arguments, expected, label in failures:
        code, stdout, stderr = run(arguments)
        body = payload_of(code, stdout, stderr, expected)
        require(body["results"] == [], f"{label} invented rows")
        require(body["error"]["code"] == expected, label)
    print("[PASS] fixture malformed payloads, bounds, and bad hours fail closed")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "transport-429", "--json"])
    body = payload_of(code, stdout, stderr, 4)
    require(body["error"]["type"] == "blocked" and body["error"]["retry_after"] == "30", body["error"])
    print("[PASS] fixture HTTP 429 keeps Retry-After and blocks")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "transport-503", "--json"])
    body = payload_of(code, stdout, stderr, 5)
    require(body["error"]["type"] == "upstream_unavailable", body["error"])
    require("503" in body["error"]["message"], body["error"])
    print("[PASS] fixture HTTP 503 is upstream_unavailable")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "transport-timeout", "--json"])
    body = payload_of(code, stdout, stderr, 5)
    require("timed out" in body["error"]["message"], body["error"])
    print("[PASS] fixture timeout is upstream_unavailable")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "transport-off-host", "--json"])
    body = payload_of(code, stdout, stderr, 7)
    require(body["error"]["type"] == "unsupported_operation", body["error"])
    print("[PASS] fixture off-host redirect is refused")

    code, stdout, stderr = run(["counts", "--limit", "1", "--fixture", "metadata-other-licence", "--json"])
    body = payload_of(code, stdout, stderr, 7)
    require("Creative Commons" in body["error"]["message"], body["error"]["message"])
    require(body["results"] == [], body["results"])
    require("licence" not in body["meta"] or "ODbL" not in body["meta"].get("licence", "Open Database License"), body["meta"])
    print("[PASS] fixture non-ODbL catalogue licence refuses the records")

    code, stdout, stderr = run(["dataset", "--fixture", "dataset-odbl", "--json"])
    body = payload_of(code, stdout, stderr, 0)
    info = body["results"][0]
    require(info["dataset_id"] == "comptages-routiers-permanents", info["dataset_id"])
    require(info["timezone"] == "Europe/Paris", info["timezone"])
    require(info["records_count"] == 3, info["records_count"])
    require("q_vehicles_per_hour" not in info, "dataset command returned a counter row")
    require(any("no counter rows" in item for item in body["warnings"]), body["warnings"])
    print("[PASS] fixture dataset command reports ODbL catalogue facts without counter rows")

    code, stdout, stderr = run(["--help"])
    require(code == 0 and "counts" in stdout and "dataset" in stdout, stdout)
    code, stdout, stderr = run(["counts", "--help"])
    require(code == 0 and "--json" in stdout and "--limit" in stdout, stdout)
    print("[PASS] contract counts and dataset help expose --json")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def live_checks() -> int:
    calls = (
        ("dataset", ["dataset", "--json"]),
        ("counts", ["counts", "--limit", "1", "--flow", "observed", "--json"]),
    )
    outputs: dict[str, tuple[int, str, str]] = {}
    for name, arguments in calls:
        try:
            code, stdout, stderr = run(arguments, timeout=40)
        except subprocess.TimeoutExpired:
            print("[SKIP] live probe skipped: network error: source request timed out")
            return 0
        if transport_failure(code, stdout, stderr):
            print("[SKIP] live probe skipped: upstream unavailable or rate limited")
            return 0
        outputs[name] = (code, stdout, stderr)
    try:
        dataset_code, dataset_out, dataset_err = outputs["dataset"]
        info_body = payload_of(dataset_code, dataset_out, dataset_err, 0)
        info = info_body["results"][0]
        require(info["licence"] == "Open Database License (ODbL)", info.get("licence"))
        require("opendatacommons.org/licenses/odbl" in info["licence_url"], info.get("licence_url"))
        require(info["publisher"] == "Direction de la Voirie et des Déplacements - Ville de Paris", info.get("publisher"))
        require(info["timezone"] == "Europe/Paris", info.get("timezone"))
        require(info["dataset_id"] == "comptages-routiers-permanents", info.get("dataset_id"))
        require(isinstance(info["records_count"], int) and info["records_count"] > 1_000_000, info.get("records_count"))
        require(info_body["meta"]["latest_data"] == info["data_processed"], info_body["meta"])
        require(info_body["meta"]["source_url"].startswith("https://opendata.paris.fr/"), info_body["meta"]["source_url"])
        print("[PASS] live catalogue still states ODbL, Europe/Paris, and a non-empty arc-hour count")

        counts_code, counts_out, counts_err = outputs["counts"]
        counts_body = payload_of(counts_code, counts_out, counts_err, 0)
        require(len(counts_body["results"]) == 1, counts_body["results"])
        row = counts_body["results"][0]
        flow = row["q_vehicles_per_hour"]
        require(row["q_observed"] is True and isinstance(flow, (int, float)) and not isinstance(flow, bool), flow)
        require("k_occupancy_percent" in row and "etat_trafic" in row and row["etat_trafic"], row)
        require(row["t_1h"].endswith("+01:00") or row["t_1h"].endswith("+02:00"), row["t_1h"])
        require(row["derived_period_start"] < row["t_1h"], row["derived_period_start"])
        require("opendata.paris.fr" in counts_body["meta"]["source_url"], counts_body["meta"]["source_url"])
        require("Europe/Paris" in urllib.parse.unquote(counts_body["meta"]["source_url"]), counts_body["meta"]["source_url"])
        require("Open Database License (ODbL)" in counts_body["meta"]["licence"], counts_body["meta"]["licence"])
        require(any("not a vehicle count" in item for item in counts_body["warnings"]), counts_body["warnings"])
        print("[PASS] live limit-1 observed flow is one Paris hour-ending arc, with q separate from k")
    except (AssertionError, json.JSONDecodeError, KeyError) as exc:
        print(f"[FAIL] live probe {exc}")
        return 1
    return 0


def main() -> int:
    try:
        fixture_checks()
    except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired, KeyError) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    return live_checks()


if __name__ == "__main__":
    raise SystemExit(main())
