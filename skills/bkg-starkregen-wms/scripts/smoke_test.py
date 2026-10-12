#!/usr/bin/env python3
"""Fixture parser checks and one bounded live probe of the BKG WMS."""
import json
import subprocess
import sys
from pathlib import Path

import cli

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CLI = Path(__file__).with_name("cli.py")


def fixture_record(name: str, lat: str, lon: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(CLI), "velocity", "--lat", lat, "--lon", lon,
         "--fixture", str(FIXTURES / name), "--json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    return json.loads(completed.stdout)["results"][0]


def check_fixtures() -> None:
    contract = json.loads((FIXTURES / "contract.json").read_text(encoding="utf-8"))
    assert contract["skill"] == "bkg-starkregen-wms"
    assert contract["contains_live_credentials"] is False
    assert contract["contains_personal_data"] is False
    layers = cli.parse_capabilities((FIXTURES / "capabilities-layers.xml").read_bytes())
    assert [row["name"] for row in layers[0]] == [
        "geschwindigkeit_agw", "ni_geschw_agw", "hh_geschw_agw",
    ]
    assert layers[1] == "latitude,longitude"
    zero = fixture_record("featureinfo-zero.txt", "52", "10")
    assert zero["state"] == "value" and zero["geschwindigkeit"] == 0
    assert zero["geschwindigkeit_text"] == "0.0"
    positive = fixture_record("featureinfo-positive.txt", "50.110", "8.682")
    assert positive["state"] == "value" and positive["geschwindigkeit"] != 0
    absent = fixture_record("featureinfo-no-feature.txt", "47.5", "10")
    assert absent["state"] == "no_data" and absent["geschwindigkeit"] is None
    assert absent["no_data_reason"] == "no_feature"
    masked = fixture_record("featureinfo-sentinel.txt", "50.937", "6.960")
    assert masked["state"] == "no_data" and masked["geschwindigkeit"] is None
    assert masked["source_token"] == "-9999.0"
    assert cli.bbox_parameter(cli.point_bbox(52, 10)).startswith("51.9995,9.9995")
    print("[PASS] fixture zero: measured Geschwindigkeit 0.0 stays a value")
    print("[PASS] fixture no-feature: absent Geschwindigkeit is not zero")
    print("[PASS] fixture sentinel: -9999 is no data and is not emitted as a velocity")
    print("[PASS] fixture positive: a non-zero Geschwindigkeit stays numeric")
    print("[PASS] fixture axis: EPSG:4326 point bbox is latitude then longitude")


def live_command(arguments: list[str]) -> tuple[int, dict | None, str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments, "--json"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    text = completed.stdout.strip() or completed.stderr.strip()
    payload = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None
    return completed.returncode, payload, text


def network_failure(code: int, text: str) -> bool:
    if code == 5:
        return True
    lowered = text.lower()
    return code == 4 and ("http 429" in lowered or "http 403" in lowered or "http 451" in lowered or "challenge" in lowered)


def check_live() -> int:
    passes: list[str] = []
    code, payload, text = live_command(["layers"])
    if network_failure(code, text):
        print(f"[SKIP] live layers: network error: {text[:300]}")
        return 0
    if code != 0 or payload is None:
        print(f"[FAIL] live layers: {text[:400]}")
        return 1
    names = [row["name"] for row in payload["results"]]
    assert "geschwindigkeit_agw" in names
    assert 1 <= len(names) <= cli.MAX_NAMED_LAYERS
    assert payload["meta"]["crs_axis_order"] == "latitude,longitude"
    assert "Datenlizenz Deutschland" in payload["meta"]["licence"]
    assert "Namensnennung" in payload["meta"]["licence"]
    assert "dl-de/by-2-0" in payload["meta"]["attribution"]
    passes.append(
        f"[PASS] live layers: {len(names)} named layers include geschwindigkeit_agw; "
        "fees state dl-de/by-2-0; EPSG:4326 axis is latitude then longitude"
    )

    code, payload, text = live_command(["velocity", "--lat", "52", "--lon", "10"])
    if network_failure(code, text):
        print(f"[SKIP] live velocity: network error: {text[:300]}")
        return 0
    if code != 0 or payload is None:
        print(f"[FAIL] live velocity: {text[:400]}")
        return 1
    record = payload["results"][0]
    assert record["query_layer"] == "geschwindigkeit_agw"
    assert record["state"] == "value"
    assert isinstance(record["geschwindigkeit"], (int, float))
    assert record["geschwindigkeit"] != -9999
    assert record["geschwindigkeit_text"]
    assert record["feature_type"]
    assert record["crs_axis_order"] == "latitude,longitude"
    assert record["bbox"]["min_latitude"] == 51.9995
    assert record["bbox"]["min_longitude"] == 9.9995
    assert record["width"] == 101 and record["height"] == 101
    passes.append(
        f"[PASS] live velocity: state=value geschwindigkeit={record['geschwindigkeit_text']} "
        f"feature_type={record['feature_type']}"
    )

    code, payload, text = live_command(["velocity", "--lat", "47.5", "--lon", "10"])
    if network_failure(code, text):
        print(f"[SKIP] live no-data: network error: {text[:300]}")
        return 0
    if code != 0 or payload is None:
        print(f"[FAIL] live no-data: {text[:400]}")
        return 1
    outside = payload["results"][0]
    assert outside["state"] == "no_data"
    assert outside["geschwindigkeit"] is None
    assert outside["no_data_reason"] == "no_feature"
    assert outside["geschwindigkeit"] != 0
    passes.append("[PASS] live no-data: outside the published extent Geschwindigkeit is absent, not zero")
    print("\n".join(passes))
    return 0


def main() -> int:
    try:
        check_fixtures()
    except AssertionError as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    try:
        return check_live()
    except AssertionError as exc:
        print(f"[FAIL] live {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
