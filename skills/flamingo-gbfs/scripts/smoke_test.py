#!/usr/bin/env python3
"""Fixture assertions plus one bounded Flamingo GBFS live probe."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cli  # noqa: E402

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


def run(arguments: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_checks() -> None:
    code, stdout, stderr = run(["discovery", "--fixture", "discovery-ok", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr)
    require([item["name"] for item in payload["results"]] == ["system_information", "vehicle_status"], "fixture feeds changed")
    require(all("rideflamingo.com/gbfs/3/auckland/" in item["url"] for item in payload["results"]), "fixture kept an off-path feed")
    print("[PASS] fixture discovery keeps only Auckland GBFS feeds")

    code, stdout, _stderr = run(["discovery", "--fixture", "discovery-empty", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and payload["results"] == [], "empty feed list was not empty")
    print("[PASS] fixture empty feed list is an empty success")

    code, stdout, _stderr = run(["system", "--fixture", "system-no-licence", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", "missing licence passed")
    print("[PASS] fixture missing license_id is schema_failure")

    code, stdout, _stderr = run(["vehicles", "--fixture", "vehicles-ok", "--limit", "1", "--json"])
    payload = json.loads(stdout)
    record = payload["results"][0]
    require(code == 0 and record["vehicle_id"] == "scooter-a", "fixture vehicle changed")
    require("route" not in record and "rental_uris" not in record, "fixture emitted a trajectory")
    require(record["current_range_meters"] == 12000, "fixture range changed")
    print("[PASS] fixture vehicles keep one current position and drop routes")

    code, stdout, _stderr = run(["vehicles", "--fixture", "vehicles-empty", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and payload["results"] == [] and "error" not in payload, "empty vehicles failed")
    print("[PASS] fixture empty vehicle list is an empty success")

    code, stdout, stderr = run(["vehicles", "--fixture", "transport-malformed", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and "Traceback" not in stdout and "Traceback" not in stderr, "malformed JSON was not typed")
    print("[PASS] fixture malformed JSON is schema_failure")

    code, stdout, _stderr = run(["vehicles", "--fixture", "transport-rate-limit", "--json"])
    payload = json.loads(stdout)
    require(code == 4 and payload["error"]["retry_after"] == "30", "429 dropped Retry-After")
    print("[PASS] fixture HTTP 429 is blocked")

    code, stdout, _stderr = run(["vehicles", "--fixture", "transport-unavailable", "--json"])
    payload = json.loads(stdout)
    require(code == 5 and "503" in payload["error"]["message"], "503 was not an outage")
    print("[PASS] fixture HTTP 503 is upstream_unavailable")

    code, stdout, _stderr = run(["vehicles", "--limit", "101", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", "oversized limit was accepted")
    print("[PASS] fixture oversized vehicle limit is invalid_input")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def live_checks() -> int:
    calls = (
        ("discovery", ["discovery", "--json"]),
        ("system", ["system", "--json"]),
        ("vehicles", ["vehicles", "--limit", "1", "--json"]),
    )
    outputs: dict[str, tuple[int, str, str]] = {}
    for name, arguments in calls:
        try:
            code, stdout, stderr = run(arguments)
        except subprocess.TimeoutExpired:
            print("[FAIL] live probe network error: source request timed out")
            return 1
        if transport_failure(code, stdout, stderr):
            print("[FAIL] live probe network error: upstream unavailable or rate limited")
            return 1
        outputs[name] = (code, stdout, stderr)
    try:
        discovery_code, discovery_out, discovery_err = outputs["discovery"]
        system_code, system_out, system_err = outputs["system"]
        vehicle_code, vehicle_out, vehicle_err = outputs["vehicles"]
        discovery = json.loads(discovery_out)
        system = json.loads(system_out)
        vehicles = json.loads(vehicle_out)
        require(discovery_code == 0 and discovery_err == "", discovery_err)
        feeds = {item["name"]: item["url"] for item in discovery["results"]}
        require(feeds.get("system_information") == cli.SYSTEM_URL, feeds.get("system_information"))
        require(feeds.get("vehicle_status") == cli.VEHICLE_URL, feeds.get("vehicle_status"))
        require(all(url.startswith("https://data.rideflamingo.com/gbfs/3/auckland/") for url in feeds.values()), feeds)
        require(discovery["results"][0]["gbfs_version"] == "3.0", "live discovery version drifted")
        print("[PASS] live discovery listed the Auckland system and vehicle feeds")

        require(system_code == 0 and system_err == "", system_err)
        system_record = system["results"][0]
        require(system_record["license_id"] == "CC-BY-4.0", system_record.get("license_id"))
        require(system["meta"]["licence"] == "CC BY 4.0", system["meta"].get("licence"))
        require(system_record["name"] == "Flamingo", system_record.get("name"))
        require(system_record["system_id"] == "flamingo_auckland", system_record.get("system_id"))
        require(system_record["timezone"] == "Etc/UTC", system_record.get("timezone"))
        require(system["meta"]["source_url"] == cli.SYSTEM_URL, system["meta"].get("source_url"))
        print("[PASS] live system_information states CC-BY-4.0 and Etc/UTC")

        require(vehicle_code == 0 and vehicle_err == "", vehicle_err)
        require(len(vehicles["results"]) == 1, vehicles["results"])
        record = vehicles["results"][0]
        require("rental_uris" not in record and "route" not in record and "path" not in record, record.keys())
        lat = record["lat"]
        lon = record["lon"]
        require(isinstance(lat, (int, float)) and isinstance(lon, (int, float)), "live coordinates were not numbers")
        require(-48 <= lat <= -34 and 166 <= lon <= 179, (lat, lon))
        require(isinstance(record["ttl_seconds"], int) and 0 <= record["ttl_seconds"] <= 86400, record["ttl_seconds"])
        counts = [item for item in vehicles["warnings"] if item.startswith("source vehicle_count:")]
        require(counts and int(counts[0].rsplit(":", 1)[1]) >= 1, vehicles.get("warnings"))
        require(vehicles["meta"]["source_url"] == cli.VEHICLE_URL, vehicles["meta"].get("source_url"))
        require(vehicles["meta"]["latest_data"], "live vehicle file stated no last_updated")
        require("fixture" not in " ".join(vehicles.get("warnings", [])), "live vehicles were marked as a fixture")
        print("[PASS] live vehicle_status returned one current Auckland position")
    except (AssertionError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
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
