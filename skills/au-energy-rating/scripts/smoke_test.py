#!/usr/bin/env python3
"""Deterministic fixture checks and one bounded live probe."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
ENTRY = Path(__file__).with_name("cli.py")
ACTIVE_ID = "0973a476-eb0c-45e6-9a18-054f74307843"
INACTIVE_ID = "4b512c09-7ae7-4f0b-8e5f-c6402afdac96"
PACKAGE_NAME = "energy-rating-for-household-appliances"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def refuse_network(url: str) -> dict:
    raise AssertionError(f"network call was not allowed: {url}")


def run_main(argv: list[str], fetch=refuse_network) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv, fetch=fetch)
    return code, stdout.getvalue(), stderr.getvalue()


def scripted_fetch(package: dict, preview: dict | None = None):
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        if "package_show" in url:
            return package
        if preview is not None and "datastore_search" in url:
            return preview
        raise AssertionError(url)

    return calls, fetch


def positive_record() -> None:
    payload = load("datastore-preview.json")
    records, total = cli.parse_preview(payload, limit=1)
    assert total == 2
    assert len(records) == 1
    record = records[0]
    assert record["Brand"] == "Example Brand"
    assert record["Model_No"] == "MODEL-1"
    assert record["c_star_mixed"] == "N/A"
    assert record["Family Name"] is None
    assert set(record) == {"_id", "Brand", "Model_No", "c_star_mixed", "Family Name"}
    package = cli.parse_package(load("package-show.json"))
    assert package["name"] == PACKAGE_NAME
    assert package["licence_title"] == "Creative Commons Attribution 3.0 Australia"
    assert package["licence_url"] == load("package-show.json")["result"]["license_url"]
    assert package["metadata_modified"] == "2026-10-11T08:03:44.379542"
    active = package["resources"][0]
    assert active["id"] == ACTIVE_ID
    assert active["name"] == "Air Conditioners -"
    assert active["datastore_active"] is True


def empty_result() -> None:
    records, total = cli.parse_preview(load("datastore-empty-success.json"), limit=1)
    assert records == [] and total == 0


def success_false_invents_nothing() -> None:
    try:
        cli.parse_preview(load("ckan-success-false.json"), limit=1)
    except cli.SkillError as exc:
        assert exc.code == 6
        assert "no rows were invented" in str(exc)
        return
    raise AssertionError("success false was treated as data")


def malformed_payload() -> None:
    body = (FIXTURES / "malformed-payload.txt").read_bytes()
    try:
        cli.decode_response(200, {}, body)
    except cli.SkillError as exc:
        assert exc.code == 6
        assert "non-JSON or truncated JSON" in str(exc)
        return
    raise AssertionError("malformed JSON was accepted")


def http_429() -> None:
    fixture = load("http-429.json")
    try:
        cli.decode_response(
            fixture["status"],
            {"Retry-After": fixture["retry_after"]},
            fixture["body_text"].encode("utf-8"),
        )
    except cli.SkillError as exc:
        assert exc.code == 4
        assert exc.retry_after == "30"
        assert "not-a-row" not in str(exc)
        return
    raise AssertionError("HTTP 429 body was accepted as rows")


def http_503() -> None:
    fixture = load("http-503.json")
    try:
        cli.decode_response(fixture["status"], {}, fixture["body_text"].encode("utf-8"))
    except cli.SkillError as exc:
        assert exc.code == 5
        assert "HTTP 503" in str(exc)
        assert "not-a-row" not in str(exc)
        return
    raise AssertionError("HTTP 503 body was accepted as rows")


def byte_cap() -> None:
    try:
        cli.decode_response(200, {}, b"{" * (cli.MAX_BYTES + 1))
    except cli.SkillError as exc:
        assert exc.code == 6
        assert "byte cap" in str(exc)
        return
    raise AssertionError("oversized body was parsed")


def reject_url_before_network() -> None:
    code, stdout, _stderr = run_main(
        ["preview", "https://example.com/resource", "--limit", "1", "--json"]
    )
    assert code == 2
    payload = json.loads(stdout)
    assert payload["results"] == []
    assert payload["error"]["code"] == 2
    assert payload["error"]["type"] == "invalid_input"
    assert "not a URL" in payload["error"]["message"]


def reject_limit_before_network() -> None:
    code, stdout, _stderr = run_main(
        ["preview", ACTIVE_ID, "--limit", "21", "--json"]
    )
    assert code == 2
    payload = json.loads(stdout)
    assert payload["results"] == []
    assert payload["error"]["type"] == "invalid_input"
    assert "1 to 20" in payload["error"]["message"]


def inactive_resource_does_not_search() -> None:
    calls, fetch = scripted_fetch(load("package-show.json"))
    code, stdout, _stderr = run_main(["preview", INACTIVE_ID, "--limit", "1", "--json"], fetch)
    assert code == 2
    assert json.loads(stdout)["results"] == []
    assert calls and all("datastore_search" not in url for url in calls)
    assert all(url.startswith("https://data.gov.au/data/api/3/action/") for url in calls)
    assert all(".csv" not in url for url in calls)


def preview_stays_on_action_api() -> None:
    calls, fetch = scripted_fetch(load("package-show.json"), load("datastore-preview.json"))
    code, stdout, _stderr = run_main(["preview", ACTIVE_ID, "--limit", "1", "--json"], fetch)
    assert code == 0
    payload = json.loads(stdout)
    assert payload["results"][0]["c_star_mixed"] == "N/A"
    assert payload["meta"]["total"] == 2
    assert payload["meta"]["limit"] == 1
    assert len(calls) == 2
    assert all(url.startswith("https://data.gov.au/data/api/3/action/") for url in calls)
    assert all(".csv" not in url and "://" in url for url in calls)
    assert "package_show" in calls[0] and "datastore_search" in calls[1]


def off_host_redirect() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "https://off-allowlist.invalid/nope")
            self.end_headers()

        def log_message(self, _format: str, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/start"
    try:
        try:
            cli._opener().open(url, timeout=2)
        except cli.SkillError as exc:
            assert exc.code == 7 and "allowlist" in str(exc)
            return
        except urllib.error.URLError as exc:
            reason = exc.reason
            assert isinstance(reason, cli.SkillError)
            assert reason.code == 7 and "allowlist" in str(reason)
            return
        raise AssertionError("off-host redirect was followed")
    finally:
        server.shutdown()
        server.server_close()


def reject_off_allowlist_before_connect() -> None:
    for url in ("https://example.com/data", "http://data.gov.au/data", "https://data.gov.au.invalid/data"):
        try:
            cli.fetch_json(url)
        except cli.SkillError as exc:
            assert exc.code == 7
            continue
        raise AssertionError(f"off-allowlist URL was fetched: {url}")


def run_live(args: list[str]) -> dict | None:
    try:
        completed = subprocess.run(
            [sys.executable, str(ENTRY), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[SKIP] live network error: source request timed out")
        return None
    if completed.returncode in (4, 5):
        detail = completed.stderr.strip() or completed.stdout.strip()
        print(f"[SKIP] live network error: {detail}")
        return None
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def live_probe() -> None:
    package = run_live(["package", "--json"])
    if package is None:
        return
    preview = run_live(["preview", ACTIVE_ID, "--limit", "1", "--json"])
    if preview is None:
        print("[SKIP] live network error: preview was not completed")
        return
    meta = package["meta"]
    result = package["results"][0]
    assert set(package) == {"meta", "results"}
    assert meta["publisher"] == result["organisation"]
    assert meta["publisher"] == cli.PUBLISHER
    assert meta["licence"] == "Creative Commons Attribution 3.0 Australia"
    assert meta["retrieved_at"].endswith("Z")
    assert meta["source_url"].startswith("https://data.gov.au/data/api/3/action/package_show?")
    assert result["name"] == PACKAGE_NAME
    assert result["package_id"] == cli.PACKAGE_ID
    assert "creativecommons.org/licenses/by/3.0/au/" in result["licence_url"]
    assert isinstance(meta["latest_data"], str) and meta["latest_data"]
    active = next(item for item in result["resources"] if item["id"] == ACTIVE_ID)
    assert active["datastore_active"] is True
    assert "Air Conditioners" in active["name"]
    assert " " * 8 not in active["name"]
    print("[PASS] live energy-rating package licence, organisation and datastore resource")

    record = preview["results"][0]
    assert preview["meta"]["resource_id"] == ACTIVE_ID
    assert preview["meta"]["limit"] == 1
    assert preview["meta"]["total"] > 1
    assert len(preview["results"]) == 1
    assert preview["meta"]["source_url"].startswith(
        "https://data.gov.au/data/api/3/action/datastore_search?"
    )
    assert "limit=1" in preview["meta"]["source_url"]
    assert ".csv" not in preview["meta"]["source_url"]
    assert isinstance(record["Brand"], str) and record["Brand"].strip()
    assert isinstance(record["Model_No"], str) and record["Model_No"].strip()
    assert "c_star_mixed" in record
    assert record["c_star_mixed"] is None or isinstance(record["c_star_mixed"], str)
    assert preview["meta"]["licence"] == meta["licence"]
    assert preview["meta"]["retrieved_at"].endswith("Z")
    print("[PASS] live air-conditioner preview keeps brand, model and star field")


def main() -> int:
    checks = (
        ("fixture", "positive record preserves null, N/A and collapsed resource name", positive_record),
        ("fixture", "empty datastore result stays empty", empty_result),
        ("fixture", "CKAN success false invents no rows", success_false_invents_nothing),
        ("fixture", "malformed payload is an error", malformed_payload),
        ("fixture", "HTTP 429 is blocked and keeps Retry-After", http_429),
        ("fixture", "HTTP 503 is upstream unavailable", http_503),
        ("fixture", "oversized body is not parsed", byte_cap),
        ("contract", "URL resource is rejected before any network call", reject_url_before_network),
        ("contract", "limit above 20 is rejected before any network call", reject_limit_before_network),
        ("contract", "inactive resource does not call datastore_search", inactive_resource_does_not_search),
        ("contract", "preview uses only data.gov.au CKAN action URLs", preview_stays_on_action_api),
        ("contract", "off-host redirect is rejected", off_host_redirect),
        ("contract", "off-allowlist URL is rejected before connect", reject_off_allowlist_before_connect),
    )
    failed = False
    for kind, name, fn in checks:
        try:
            fn()
        except Exception as exc:
            print(f"[FAIL] {kind} {name}: {exc}")
            failed = True
        else:
            print(f"[PASS] {kind} {name}")
    if failed:
        return 1
    try:
        live_probe()
    except Exception as exc:
        print(f"[FAIL] live energy-rating probe: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
