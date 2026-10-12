#!/usr/bin/env python3
"""Fixture assertions plus a bounded Open Food Facts live probe."""
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

LIVE_BARCODE = "3017624010701"
ABSENT_BARCODE = "1234567890128"
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
    code, stdout, stderr = run(["product", "00012345678905", "--fixture", "product-found", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr)
    require(payload["results"][0]["code"] == "00012345678905", "fixture dropped leading zeros")
    require("nova_group" in payload["results"][0]["missing_fields"], "fixture invented nova_group")
    require(payload["meta"]["publisher"] == "Open Food Facts", "publisher changed")
    print("[PASS] fixture product parser keeps leading zeros and names missing fields")

    code, stdout, _stderr = run(["product", "12345670", "--fixture", "product-not-found", "--json"])
    payload = json.loads(stdout)
    require(code == 0 and payload["results"] == [], "fixture not-found was not empty")
    print("[PASS] fixture unknown product is an empty success")

    code, stdout, stderr = run(["product", "NOT-A-CODE", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", "malformed barcode was accepted")
    require("Traceback" not in stderr and "Traceback" not in stdout, "malformed barcode traced")
    print("[PASS] fixture malformed barcode is invalid_input")

    code, stdout, _stderr = run(["search", "--country", "new-zealand", "--limit", "999999", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", "huge limit was accepted")
    print("[PASS] fixture huge search limit is rejected")

    code, stdout, _stderr = run(["product", "00012345678905", "--fixture", "transport-malformed", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and "Traceback" not in stdout, "malformed JSON was not a typed schema failure")
    print("[PASS] fixture malformed JSON is schema_failure")

    code, stdout, _stderr = run(["product", "00012345678905", "--fixture", "transport-off-host", "--json"])
    payload = json.loads(stdout)
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host fixture was followed")
    print("[PASS] fixture off-host redirect is refused")

    url = cli.product_url("00012345678905")
    require("/00012345678905.json?" in url and url.startswith("https://world.openfoodfacts.org/"), url)
    print("[PASS] fixture barcode URL preserves leading zeros on the allowlisted host")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def live_checks() -> int:
    calls = (
        ("product", [LIVE_BARCODE, "--json"]),
        ("absent", [ABSENT_BARCODE, "--json"]),
        ("search", ["search", "--country", "new-zealand", "--category", "yogurts", "--limit", "1", "--json"]),
        ("human", [LIVE_BARCODE]),
    )
    outputs: dict[str, tuple[int, str, str]] = {}
    for name, arguments in calls:
        try:
            code, stdout, stderr = run(arguments if name == "search" else ["product", *arguments])
        except subprocess.TimeoutExpired:
            print("[SKIP] live probe skipped: network error: source request timed out")
            return 0
        if transport_failure(code, stdout, stderr):
            print("[SKIP] live probe skipped: upstream unavailable or rate limited")
            return 0
        outputs[name] = (code, stdout, stderr)
    found_code, found_out, found_err = outputs["product"]
    absent_code, absent_out, _absent_err = outputs["absent"]
    search_code, search_out, _search_err = outputs["search"]
    human_code, human_out, human_err = outputs["human"]
    try:
        found = json.loads(found_out)
        require(found_code == 0 and found["results"], found_out)
        record = found["results"][0]
        require(record["code"] == LIVE_BARCODE, record.get("code"))
        require(record.get("product_name") == "Nutella", record.get("product_name"))
        require(found["meta"]["source_url"].startswith("https://world.openfoodfacts.org/api/v3/product/"), "live URL drifted")
        require("fixture" not in found.get("warnings", [""])[0], "live lookup was marked as a fixture")
        print("[PASS] live product lookup returned Nutella for 3017624010701")

        require(human_code == 0 and "Nutella" in human_out and "Traceback" not in human_err, human_out)
        print("[PASS] live human product lookup returned Nutella")

        absent = json.loads(absent_out)
        require(absent_code == 0 and absent["results"] == [], absent_out[:500])
        require(any("product_not_found" in item for item in absent.get("warnings", [])), absent.get("warnings"))
        print("[PASS] live unknown barcode 1234567890128 is an empty not-found result")

        searched = json.loads(search_out)
        require(search_code == 0 and searched["results"], search_out[:500])
        require(len(searched["results"]) == 1, "search ignored the one-row limit")
        require(str(searched["results"][0].get("code", "")).isdigit(), "search code was not digits")
        require(searched["meta"]["source_url"].startswith("https://world.openfoodfacts.org/api/v2/search?"), "search URL drifted")
        print("[PASS] live v2 country and category search returned one first-page row")
    except (AssertionError, json.JSONDecodeError) as exc:
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
