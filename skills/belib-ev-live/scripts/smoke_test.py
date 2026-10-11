#!/usr/bin/env python3
"""Fixture contracts and one bounded live Belib availability probe."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import cli

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CLI = Path(__file__).resolve().with_name("cli.py")
PARIS_LON = (2.24, 2.43)
PARIS_LAT = (48.80, 48.92)


def fail(kind: str, message: str) -> None:
    print(f"[FAIL] {kind} {message}")


def ok(kind: str, message: str) -> None:
    print(f"[PASS] {kind} {message}")


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def assert_error(arguments: list[str], code: int, error_type: str) -> None:
    completed = run_cli([*arguments, "--json"])
    if completed.returncode != code:
        raise AssertionError(f"exit {completed.returncode}, expected {code}: {completed.stdout} {completed.stderr}")
    if completed.stderr:
        raise AssertionError(completed.stderr)
    payload = json.loads(completed.stdout)
    if payload["results"] != [] or payload["error"]["code"] != code or payload["error"]["type"] != error_type:
        raise AssertionError(payload)
    if payload["meta"]["retrieved_at"].endswith("Z") is False:
        raise AssertionError(payload["meta"])


def fixture_checks() -> int:
    failures = 0

    def check(name: str, fn) -> None:
        nonlocal failures
        try:
            fn()
        except Exception as exc:
            failures += 1
            fail("fixture", f"{name}: {exc}")
            return
        ok("fixture", name)

    def positive() -> None:
        completed = run_cli([
            "availability", "--limit", "1", "--fixture", "tests/fixtures/records-positive.json", "--json",
        ])
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        record = payload["results"][0]
        if record["id_pdc"] != "FR*V75*E9012*06*3":
            raise AssertionError(record["id_pdc"])
        if record["statut_pdc"] != "Occupé (en charge)":
            raise AssertionError(record["statut_pdc"])
        if record["last_updated"] != "2026-10-11T18:12:05+00:00":
            raise AssertionError(record["last_updated"])
        if record["code_insee_commune"] != "75056":
            raise AssertionError(record["code_insee_commune"])
        if payload["meta"]["licence"] != cli.EXPECTED_LICENCE:
            raise AssertionError(payload["meta"])
        if "Ville de Paris" not in payload["meta"]["attribution"]:
            raise AssertionError(payload["meta"]["attribution"])
        if payload["meta"]["latest_data"] != record["last_updated"]:
            raise AssertionError(payload["meta"]["latest_data"])

    def empty() -> None:
        completed = run_cli([
            "availability", "--limit", "1", "--fixture", "tests/fixtures/records-empty.json", "--json",
        ])
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        if payload["results"] != [] or payload["meta"].get("total_count") != 0:
            raise AssertionError(payload)
        if "latest_data" in payload["meta"] or "error" in payload:
            raise AssertionError(payload["meta"])

    def malformed() -> None:
        assert_error(
            ["availability", "--limit", "1", "--fixture", "tests/fixtures/records-malformed.json"],
            6,
            "schema_failure",
        )

    def truncated() -> None:
        try:
            cli.decode_json_object((FIXTURES / "records-truncated.txt").read_bytes())
        except cli.SkillError as exc:
            if exc.code != 6 or "truncated JSON" not in str(exc):
                raise AssertionError(exc) from exc
            return
        raise AssertionError("truncated JSON was accepted")

    def null_insee() -> None:
        payload = json.loads((FIXTURES / "records-null-insee.json").read_text(encoding="utf-8"))
        records, total = cli.parse_records_payload(payload, 1, cli.datetime.now(cli.timezone.utc))
        if total != 1 or records[0]["code_insee_commune"] is not None:
            raise AssertionError(records)
        if records[0]["statut_pdc"] != "Inconnu" or records[0]["adresse_station"] is not None:
            raise AssertionError(records[0])

    def bad_commune() -> None:
        assert_error(
            ["availability", "--limit", "1", "--fixture", "tests/fixtures/records-bad-commune.json"],
            6,
            "schema_failure",
        )

    def http_429() -> None:
        payload = json.loads((FIXTURES / "http-429.json").read_text(encoding="utf-8"))
        error = cli.http_status_error(payload["status"], payload["retry_after"], payload["body"].encode())
        if error is None or error.code != 4 or error.retry_after != "30" or "429" not in str(error):
            raise AssertionError(error)

    def http_503() -> None:
        payload = json.loads((FIXTURES / "http-503.json").read_text(encoding="utf-8"))
        error = cli.http_status_error(payload["status"], payload["retry_after"], payload["body"].encode())
        if error is None or error.code != 5 or "503" not in str(error):
            raise AssertionError(error)

    def licence_gate() -> None:
        accepted = json.loads((FIXTURES / "metadata-odbl.json").read_text(encoding="utf-8"))
        licence, publisher, licence_url = cli.parse_licence(accepted)
        if licence != cli.EXPECTED_LICENCE or "Ville de Paris" not in publisher or not licence_url:
            raise AssertionError((licence, publisher, licence_url))
        rejected = json.loads((FIXTURES / "metadata-other-licence.json").read_text(encoding="utf-8"))
        try:
            cli.parse_licence(rejected)
        except cli.SkillError as exc:
            if exc.code != 7 or "ODbL" not in str(exc):
                raise AssertionError(exc) from exc
        else:
            raise AssertionError("non-ODbL licence was accepted")

    def no_network_on_bad_input() -> None:
        called = {"count": 0}

        def boom(*_args, **_kwargs):
            called["count"] += 1
            raise AssertionError("network was called")

        original = cli.fetch_json
        cli.fetch_json = boom
        try:
            cases = (
                ["availability", "--limit", "0", "--json"],
                ["availability", "--limit", "21", "--json"],
                ["availability", "--limit", "1", "--id", "https://evil.example/point", "--json"],
                ["availability", "--limit", "1", "--bbox", "174,-37,175", "--json"],
                ["availability", "--limit", "1", "--url", "https://evil.example/records", "--json"],
            )
            for arguments in cases:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main(arguments)
                if code != 2 or called["count"]:
                    raise AssertionError(arguments)
        finally:
            cli.fetch_json = original

    def redirect_rejected() -> None:
        handler = cli.AllowlistRedirectHandler()
        request = urllib.request.Request("https://parisdata.opendatasoft.com/api")
        try:
            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/away")
        except cli.SkillError as exc:
            if exc.code != 7:
                raise AssertionError(exc) from exc
        else:
            raise AssertionError("off-host redirect was accepted")
        try:
            cli.enforce_https_allowlist("http://parisdata.opendatasoft.com/api")
        except cli.SkillError as exc:
            if exc.code != 7:
                raise AssertionError(exc) from exc
        else:
            raise AssertionError("HTTP downgrade was accepted")

    def paris_bbox_and_new_zealand_box() -> None:
        matched = run_cli([
            "availability", "--limit", "1", "--fixture", "tests/fixtures/records-positive.json",
            "--bbox=2.40,48.84,2.42,48.85", "--json",
        ])
        missed = run_cli([
            "availability", "--limit", "1", "--fixture", "tests/fixtures/records-positive.json",
            "--bbox=174.0,-37.0,175.0,-36.0", "--json",
        ])
        if matched.returncode != 0 or json.loads(matched.stdout)["results"][0]["id_pdc"] != "FR*V75*E9012*06*3":
            raise AssertionError(matched.stdout)
        missed_payload = json.loads(missed.stdout)
        if missed.returncode != 0 or missed_payload["results"] != []:
            raise AssertionError(missed.stdout)

    def geojson_order() -> None:
        completed = run_cli([
            "availability", "--limit", "1", "--fixture", "tests/fixtures/records-positive.json",
            "--format", "geojson",
        ])
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        coordinates = payload["features"][0]["geometry"]["coordinates"]
        if payload["type"] != "FeatureCollection" or coordinates != [2.411238, 48.845264]:
            raise AssertionError(coordinates)
        if payload["meta"]["licence"] != cli.EXPECTED_LICENCE:
            raise AssertionError(payload["meta"])

    def query_stays_on_host() -> None:
        url = cli.build_records_url(1, "FR*V75*E9012*06*3", (2.25, 48.82, 2.42, 48.90))
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != cli.ALLOWED_HOST:
            raise AssertionError(url)
        if "order_by=last_updated%20desc" not in url or "limit=1" not in url:
            raise AssertionError(url)
        if "donnees-statiques" in url:
            raise AssertionError(url)

    check("positive Paris record keeps source status and ODbL attribution", positive)
    check("empty result is an empty array", empty)
    check("malformed payload is schema_failure", malformed)
    check("truncated JSON is schema_failure", truncated)
    check("null INSEE stays null and Inconnu is kept", null_insee)
    check("non-Paris commune code is schema_failure", bad_commune)
    check("HTTP 429 is blocked and keeps Retry-After", http_429)
    check("HTTP 503 is upstream_unavailable", http_503)
    check("ODbL metadata is required and another licence is refused", licence_gate)
    check("malformed arguments are rejected before any network call", no_network_on_bad_input)
    check("redirect off the official host is rejected", redirect_rejected)
    check("Paris bbox matches and a New Zealand bbox does not", paris_bbox_and_new_zealand_box)
    check("GeoJSON uses longitude then latitude", geojson_order)
    check("records query stays on the official host and does not call the static dataset", query_stays_on_host)
    return failures


def contract_check() -> int:
    completed = run_cli([
        "availability", "--limit", "1", "--fixture", "tests/fixtures/records-positive.json", "--json",
    ])
    try:
        payload = json.loads(completed.stdout)
        if completed.returncode != 0 or completed.stderr:
            raise AssertionError(completed.stderr)
        if not payload["meta"]["source_url"].startswith("https://parisdata.opendatasoft.com/"):
            raise AssertionError(payload["meta"]["source_url"])
        if payload["results"][0]["longitude"] > 10:
            raise AssertionError(payload["results"][0])
    except Exception as exc:
        fail("contract", f"offline availability envelope: {exc}")
        return 1
    ok("contract", "offline availability envelope")
    return 0


def live_check() -> int:
    try:
        completed = subprocess.run(
            [sys.executable, str(CLI), "availability", "--limit", "1", "--require-current", "--json"],
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        fail("live", f"network error: source request timed out: {exc}")
        return 1
    text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        lowered = text.lower()
        if any(marker in lowered for marker in ("network error", "timed out", "http 429", "http 503", "http 5")):
            fail("live", f"network error: {text[:400]}")
        else:
            fail("live", text[:400])
        return 1
    try:
        payload = json.loads(completed.stdout)
        meta = payload["meta"]
        record = payload["results"][0]
        if meta["licence"] != cli.EXPECTED_LICENCE or "Ville de Paris" not in meta["publisher"]:
            raise AssertionError(meta)
        if "ODbL" not in meta["attribution"] or "Ville de Paris" not in meta["attribution"]:
            raise AssertionError(meta["attribution"])
        if not meta["source_url"].startswith(f"https://{cli.ALLOWED_HOST}/") or cli.DATASET_ID not in meta["source_url"]:
            raise AssertionError(meta["source_url"])
        licence_url = str(meta.get("licence_url") or "")
        if "odbl" not in licence_url.lower():
            raise AssertionError(licence_url)
        if len(payload["results"]) != 1 or not cli.POINT_ID_PATTERN.fullmatch(record["id_pdc"]):
            raise AssertionError(record)
        if not record["statut_pdc"].strip():
            raise AssertionError(record)
        if not (PARIS_LON[0] <= record["longitude"] <= PARIS_LON[1] and PARIS_LAT[0] <= record["latitude"] <= PARIS_LAT[1]):
            raise AssertionError((record["longitude"], record["latitude"]))
        if record["code_insee_commune"] not in (None, "75056"):
            raise AssertionError(record["code_insee_commune"])
        if meta.get("current") is not True or meta.get("latest_data") != record["last_updated"]:
            raise AssertionError(meta)
        age = record["update_age_seconds"]
        if not (-cli.FUTURE_SKEW_SECONDS <= age <= cli.CURRENT_MAX_AGE_SECONDS):
            raise AssertionError(age)
        static_url = record.get("static_description_url")
        if static_url and urllib.parse.urlparse(static_url).hostname != cli.ALLOWED_HOST:
            raise AssertionError(static_url)
    except Exception as exc:
        fail("live", f"availability response was not current Paris ODbL data: {exc}")
        return 1
    ok("live", "ODbL attribution, Paris coordinates, and a current availability timestamp")
    return 0


def main() -> int:
    failures = fixture_checks() + contract_check()
    if failures:
        return 1
    return live_check()


if __name__ == "__main__":
    raise SystemExit(main())
