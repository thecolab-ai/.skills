#!/usr/bin/env python3
"""Fixture assertions plus a bounded OpenTopography live probe."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "cli.py"
ROOT = Path(__file__).resolve().parents[3]
AUCKLAND_BBOX = "174.4,-37.3,175.1,-36.5"
AUCKLAND_ID = "OTLAS.042025.2193.1"
AUCKLAND_2013_ID = "OTLAS.062016.2193.1"
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
        timeout=25,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_checks() -> None:
    code, stdout, stderr = run(
        ["collections", "--bbox", "174.7,-36.9,174.8,-36.8", "--fixture", "catalog-ok", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 0 and stderr == "", stderr)
    require(payload["page"]["matched"] == 2, "catalogue fixture dropped a point-cloud row")
    require(payload["results"][1]["name"] == "Fixture Wānaka Ridge", "catalogue fixture left an HTML entity")
    require(all(record["file_format"] == "Point Cloud Data" for record in payload["results"]), "raster leaked")
    print("[PASS] fixture catalogue keeps point clouds and decodes names")

    code, stdout, _stderr = run(["collections", "--bbox", "10,10,12,12", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["error"]["type"] == "invalid_input", "bbox outside NZ was accepted")
    print("[PASS] fixture bounding box outside the NZ window is rejected")

    code, stdout, stderr = run(["files", "OTLAS.062016.2193.9", "--fixture", "files-not-provided", "--json"])
    payload = json.loads(stdout)
    rendered = json.dumps(payload)
    require(code == 7 and "Not-Provided" in payload["error"]["message"], payload)
    require("s3.sdsc.edu" not in rendered and "Traceback" not in stderr, rendered)
    print("[PASS] fixture unstated licence refuses file listing")

    code, stdout, _stderr = run(["files", "OTLAS.042025.2193.9", "--fixture", "files-off-host", "--json"])
    payload = json.loads(stdout)
    require(code == 7 and payload["error"]["type"] == "unsupported_operation", "off-host listing was followed")
    require(payload["results"] == [], "off-host listing returned keys")
    print("[PASS] fixture off-host listing redirect is refused")

    code, stdout, _stderr = run(["files", "OTLAS.042025.2193.9", "--fixture", "files-doctype", "--json"])
    payload = json.loads(stdout)
    require(code == 6 and "Traceback" not in stdout, "doctype listing was parsed")
    print("[PASS] fixture listing doctype is a schema failure")

    code, stdout, _stderr = run(
        ["collections", "--bbox", "174.7,-36.9,174.8,-36.8", "--fixture", "transport-malformed", "--json"]
    )
    payload = json.loads(stdout)
    require(code == 6 and payload["error"]["type"] == "schema_failure", "malformed catalogue was accepted")
    print("[PASS] fixture malformed catalogue JSON is schema_failure")

    code, stdout, _stderr = run(["files", "not-an-id", "--limit", "999", "--json"])
    payload = json.loads(stdout)
    require(code == 2 and payload["results"] == [], "malformed id or huge limit was accepted")
    print("[PASS] fixture malformed id is rejected before a request")


def transport_failure(code: int, stdout: str, stderr: str) -> bool:
    if code not in {4, 5}:
        return False
    folded = f"{stderr}\n{stdout}".lower()
    return any(marker in folded for marker in NETWORK_MARKERS)


def live_checks() -> int:
    calls = (
        ("collections", ["collections", "--bbox", AUCKLAND_BBOX, "--limit", "5", "--json"]),
        ("info", ["info", AUCKLAND_ID, "--json"]),
        ("human", ["info", AUCKLAND_ID]),
        ("files", ["files", AUCKLAND_ID, "--limit", "5", "--json"]),
        ("refused", ["files", AUCKLAND_2013_ID, "--limit", "1", "--json"]),
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
        code, stdout, _stderr = outputs["collections"]
        payload = json.loads(stdout)
        require(code == 0 and payload["results"], stdout[:500])
        require(payload["meta"]["source_url"].startswith("https://portal.opentopography.org/API/otCatalog?"), payload["meta"])
        require("detail=true" not in payload["meta"]["source_url"], "live catalogue asked for detail geometry")
        require(any(record.get("alternate_name") == "NZ24_Auckland" for record in payload["results"]), payload["results"])
        require(all(str(record.get("opentopo_id", "")).startswith("OTLAS.") for record in payload["results"]), payload)
        print("[PASS] live catalogue returned Auckland Part 1 inside the bounding box")

        code, stdout, _stderr = outputs["info"]
        payload = json.loads(stdout)
        record = payload["results"][0]
        require(code == 0 and record["opentopo_id"] == AUCKLAND_ID, record.get("opentopo_id"))
        require("Auckland Part 1" in record["name"], record.get("name"))
        require(record["alternate_name"] == "NZ24_Auckland", record.get("alternate_name"))
        require(record["licence"] == "CC-BY-4.0" and record["reusable"] is True, record.get("licence"))
        require(record["bbox"][0] < record["bbox"][2] and record["bbox"][1] < record["bbox"][3], record.get("bbox"))
        require(str(record.get("temporal_coverage", "")).find("2024") >= 0, record.get("temporal_coverage"))
        require(payload["meta"]["latest_data"] and payload["meta"]["latest_data"] != payload["meta"]["retrieved_at"][:10], payload["meta"])
        print("[PASS] live Auckland Part 1 metadata states CC-BY-4.0 and a capture interval")

        code, stdout, stderr = outputs["human"]
        require(code == 0 and "Auckland Part 1" in stdout and "CC-BY-4.0" in stdout, stdout[:500])
        require("Traceback" not in stderr, stderr)
        print("[PASS] live human dataset summary states the licence")

        code, stdout, _stderr = outputs["files"]
        payload = json.loads(stdout)
        require(code == 0 and 1 <= len(payload["results"]) <= 5, payload.get("page"))
        require(any(record["key"].endswith(".laz") and record["size_bytes"] > 0 for record in payload["results"]), payload["results"])
        for record in payload["results"]:
            require(record["url"].startswith("https://opentopography.s3.sdsc.edu/pc-bulk/NZ24_Auckland/"), record["url"])
            require("?" not in record["url"] and "AWSAccessKeyId" not in record["url"], record["url"])
        require(payload["meta"]["licence"] == "CC-BY-4.0", payload["meta"])
        require(payload["page"]["truncated"] is True, "Auckland prefix was unexpectedly complete")
        print("[PASS] live file page returned bounded Auckland LAZ urls and sizes")

        code, stdout, stderr = outputs["refused"]
        payload = json.loads(stdout)
        rendered = json.dumps(payload)
        require(code == 7 and payload["error"]["type"] == "unsupported_operation", payload)
        require("Not-Provided" in payload["error"]["message"], payload["error"]["message"])
        require(".laz" not in rendered and "opentopography.s3.sdsc.edu" not in rendered, rendered)
        require("Traceback" not in stderr, stderr)
        print("[PASS] live Auckland 2013 file listing is refused because reuse terms are not stated")
    except (AssertionError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
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
