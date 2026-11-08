#!/usr/bin/env python3
"""Smoke tests for the CarJam access restriction.

Live /car/ retrieval is not attempted. Fixture checks cover the offline parser,
including the hard failure for a CarJam shell with no public fields. Contract
checks require the typed blocked result. The historical live failure is recorded
as a skip and is not turned into a successful vehicle lookup.
"""
from __future__ import annotations

import importlib.util
import io
import json
import contextlib
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURES = SKILL_DIR / "tests" / "fixtures"
RUNNER = REPO / "scripts" / "run_skill.py"

ORIGINAL_LIVE_FAILURE = "no public vehicle fields found for plate 'PSP532'"

spec = importlib.util.spec_from_file_location("carjam_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=15,
    )


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return bool(ok)
    except Exception as exc:
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def _die_message(page: str, identifier: str = "PSP532") -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        try:
            fixture_cli.parse_vehicle(
                page,
                source_url="https://www.carjam.co.nz",
                identifier=identifier,
                lookup_type="plate",
            )
        except SystemExit:
            pass
    return buffer.getvalue()


def blocked_payload(proc: subprocess.CompletedProcess[str]) -> dict:
    if proc.returncode != 4:
        raise AssertionError(f"exit {proc.returncode}, stderr={proc.stderr[:300]!r}")
    payload = json.loads(proc.stdout)
    error = payload.get("error") or {}
    if error.get("code") != 4 or error.get("type") != "blocked":
        raise AssertionError(payload)
    message = str(error.get("message") or "")
    lowered = message.lower()
    if "access restricted" not in lowered:
        raise AssertionError(message)
    if "permitted api or provider agreement" not in lowered:
        raise AssertionError(message)
    if "not a dependable keyless connector" not in lowered:
        raise AssertionError(message)
    if payload.get("results") != []:
        raise AssertionError(payload)
    if "temporary failure" in lowered:
        raise AssertionError("restriction was reclassified as an outage")
    blob = proc.stdout + proc.stderr
    for invented in ("HIACE", '"vehicle"', '"summary"'):
        if invented in blob:
            raise AssertionError(f"output invented vehicle data: {invented}")
    meta = payload.get("meta") or {}
    if meta.get("source_url") != "https://www.carjam.co.nz":
        raise AssertionError(meta)
    if meta.get("publisher") != "CarJam":
        raise AssertionError(meta)
    if not str(meta.get("retrieved_at", "")).endswith("Z"):
        raise AssertionError(meta)
    return payload


results: list[bool] = []


def test_fixture_vehicle_parser() -> bool:
    page = (FIXTURES / "public-vehicle.html").read_text(encoding="utf-8")
    parsed = fixture_cli.parse_vehicle(
        page,
        source_url="https://www.carjam.co.nz",
        identifier="FIX123",
        lookup_type="plate",
    )
    return (
        parsed["vehicle"] == "2018 Toyota Corolla"
        and parsed["plate"] == "FIX123"
        and parsed["summary"]["make"] == "Toyota"
    )


results.append(test("fixture public vehicle HTML parser", test_fixture_vehicle_parser))


def test_fixture_block_detection() -> bool:
    block_page = (FIXTURES / "block-page.html").read_text(encoding="utf-8")
    if not fixture_cli.looks_like_block(block_page):
        return False
    if fixture_cli.has_carjam_shell(block_page):
        return False
    message = _die_message(block_page, identifier="FIX123")
    return "temporary failure" in message and "no public vehicle fields found" not in message


results.append(test("fixture anti-bot block classified as transient outage", test_fixture_block_detection))


def test_fixture_shell_without_fields_stays_hard_failure() -> bool:
    page = (FIXTURES / "shell-no-fields.html").read_text(encoding="utf-8")
    if not fixture_cli.has_carjam_shell(page):
        return False
    if fixture_cli.looks_like_block(page):
        return False
    message = _die_message(page, identifier="PSP532")
    return ORIGINAL_LIVE_FAILURE in message and "temporary failure" not in message


results.append(
    test(
        "fixture CarJam shell without public fields stays a hard failure",
        test_fixture_shell_without_fields_stays_hard_failure,
    )
)


def test_contract_help() -> bool:
    proc = run(["--help"])
    text = proc.stdout.lower()
    return (
        proc.returncode == 0
        and "access restricted" in text
        and "not a dependable keyless connector" in text
        and "lookup" in text
        and "batch" in text
    )


results.append(test("contract help text states access restricted", test_contract_help))


def test_contract_lookup_json() -> bool:
    started = time.monotonic()
    proc = run(["lookup", "FIX123", "--json", "--raw"])
    if time.monotonic() - started > 2:
        raise AssertionError("lookup took long enough to be a network retry")
    payload = blocked_payload(proc)
    return "FIX123" in payload["error"]["message"] and proc.stderr == ""


results.append(test("contract lookup json is access restricted", test_contract_lookup_json))


def test_contract_lookup_human() -> bool:
    proc = run(["lookup", "FIX123"])
    if proc.returncode != 4:
        return False
    if proc.stdout.strip():
        return False
    text = proc.stderr.lower()
    return (
        text.startswith("error:")
        and "access restricted" in text
        and "permitted api or provider agreement" in text
        and "hiace" not in text
        and "source: https://www.carjam.co.nz/car/" not in text
    )


results.append(test("contract lookup human is access restricted", test_contract_lookup_human))


def test_contract_batch_json() -> bool:
    proc = run(["batch", "FIX123", "FIX456", "--sleep", "0", "--json"])
    payload = blocked_payload(proc)
    message = payload["error"]["message"]
    return "FIX123" in message and "FIX456" in message and "vehicles" not in proc.stdout


results.append(test("contract batch json is access restricted", test_contract_batch_json))


def test_contract_invalid_identifier() -> bool:
    proc = run(["lookup", "!!!", "--json"])
    if proc.returncode != 2:
        return False
    payload = json.loads(proc.stdout)
    error = payload.get("error") or {}
    return (
        error.get("code") == 2
        and error.get("type") == "invalid_input"
        and payload.get("results") == []
        and "access restricted" not in str(error.get("message", "")).lower()
    )


results.append(test("contract invalid identifier is invalid input", test_contract_invalid_identifier))


def test_contract_overlong_identifier() -> bool:
    proc = run(["lookup", "A" * 41, "--json"])
    if proc.returncode != 2:
        return False
    payload = json.loads(proc.stdout)
    error = payload.get("error") or {}
    return error.get("code") == 2 and error.get("type") == "invalid_input" and payload.get("results") == []


results.append(test("contract overlong identifier is invalid input", test_contract_overlong_identifier))


def test_contract_batch_does_not_partially_succeed() -> bool:
    proc = run(["batch", "FIX123", "!!!", "--json"])
    if proc.returncode != 2:
        return False
    return "vehicles" not in proc.stdout and '"results": []' in proc.stdout


results.append(
    test(
        "contract mixed batch stays a failure without vehicle rows",
        test_contract_batch_does_not_partially_succeed,
    )
)


def test_contract_vin_is_also_restricted() -> bool:
    proc = run(["lookup", "SYNTHETICVIN123456", "--type", "vin", "--json"])
    payload = blocked_payload(proc)
    return "vin" in payload["error"]["message"] and "SYNTHETICVIN123456" in payload["error"]["message"]


results.append(test("contract vin lookup is access restricted", test_contract_vin_is_also_restricted))


def test_contract_runner_envelope() -> bool:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "carjam-nz", "lookup", "FIX123", "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=20,
    )
    if time.monotonic() - started > 2:
        raise AssertionError("runner lookup took long enough to be a network retry")
    if proc.returncode != 4:
        raise AssertionError(proc.stderr[:400] or proc.stdout[:400])
    payload = json.loads(proc.stdout)
    error = payload.get("error") or {}
    return (
        payload.get("ok") is False
        and payload.get("blocked") is True
        and error.get("code") == 4
        and error.get("type") == "blocked"
        and "access restricted" in str(error.get("message", "")).lower()
        and payload.get("data") is None
    )


results.append(test("contract runner envelope is blocked", test_contract_runner_envelope))


def test_contract_cli_has_no_live_fetch() -> bool:
    source = CLI.read_text(encoding="utf-8")
    forbidden = ("urlopen", "urlretrieve", "urllib.request", "cf-mitigated")
    return not any(token in source for token in forbidden)


results.append(test("contract cli does not fetch live pages", test_contract_cli_has_no_live_fetch))

print(
    "[SKIP] live vehicle retrieval is access restricted pending a permitted "
    "CarJam API or provider agreement; original failure "
    f"\"{ORIGINAL_LIVE_FAILURE}\" is not a passing lookup"
)

if all(results):
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
