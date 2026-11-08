#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path
import contextlib
import io
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills/airnz-flights/scripts/cli.py"
spec = importlib.util.spec_from_file_location("airnz_fixture_cli", CLI)
assert spec and spec.loader
fixture_cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_cli
spec.loader.exec_module(fixture_cli)

fixture_rows = fixture_cli.extract_json_array('prefix fareRows [{"id":"fixture"}] suffix', "fareRows")
fixture_fare = fixture_cli.normalise_fare({"code": "seat", "adultPrice": "$123", "reveal": True})
assert fixture_rows == [{"id": "fixture"}]
assert fixture_fare["price"] == 123 and fixture_fare["available"] is True
print("[PASS] fixture fare array extraction and fare normalisation")

# A transient Chromium navigation abort must be classified as retryable (so the
# browser path falls back to the timetable feed instead of leaking a traceback),
# while a genuine coding error must not be swallowed.
assert fixture_cli._is_transient_browser_error(
    RuntimeError('Page.goto: net::ERR_ABORTED at https://flightbookings.airnewzealand.co.nz/...')
)
assert fixture_cli._is_transient_browser_error(RuntimeError("Timeout 90000ms exceeded"))
assert not fixture_cli._is_transient_browser_error(ValueError("unexpected key in payload"))
print("[PASS] fixture transient browser-navigation error classification")

# CloakBrowser 0.7 licence denials, as the wrapper raises them (cloakbrowser/license.py).
SESSION_LIMIT_EXIT = 76
LICENCE_76 = ("CloakBrowser Pro: session limit reached for your plan. Close another running session "
              "or upgrade your plan.")
LICENCE_77 = "CloakBrowser Pro: license key is invalid, expired, or missing."


def launch_failure_cases():
    """(label, fake cloakbrowser.launch, expected exit code, expected error) for the CLI.

    Only the exit-76 session limit is a SKIP state; every other start-up failure,
    including other licence codes and API breaks, must be browser_launch_failed (exit 1).
    """
    import types as _types

    licence_error = type("CloakBrowserLicenseError", (RuntimeError,), {})

    def raises(exc):
        def _launch(*a, **kw):
            raise exc
        return _launch

    def late(exc):
        def _goto(*a, **kw):
            raise exc
        page = _types.SimpleNamespace(goto=_goto, evaluate=_goto, content=_goto, wait_for_timeout=_goto)
        return lambda *a, **kw: _types.SimpleNamespace(new_page=lambda *a, **kw: page, close=lambda: None)

    return [
        ("session limit at launch", raises(licence_error(LICENCE_76)), SESSION_LIMIT_EXIT, "browser_session_limit"),
        ("session limit after handshake", late(licence_error(LICENCE_76)), SESSION_LIMIT_EXIT, "browser_session_limit"),
        ("invalid licence key (exit 77)", raises(licence_error(LICENCE_77)), 1, "browser_launch_failed"),
        ("invalid licence key after handshake", late(licence_error(LICENCE_77)), 1, "browser_launch_failed"),
        ("launch() API break", raises(TypeError("launch() got an unexpected keyword argument 'timezone'")), 1, "browser_launch_failed"),
        ("browser without new_page", lambda *a, **kw: _types.SimpleNamespace(close=lambda: None), 1, "browser_launch_failed"),
        ("session-limit text from a non-licence error", raises(RuntimeError(LICENCE_76)), 1, "browser_launch_failed"),
    ]


def browser_error(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload.get("error") if isinstance(payload, dict) else None


def browser_session_limit(returncode: int, stdout: str) -> bool:
    """True only for CloakBrowser's concurrent-session limit: exit 76 plus the CLI's
    machine-readable browser_session_limit payload. Any other browser start-up failure
    (browser_launch_failed, exit 1) stays a FAIL."""
    return returncode == SESSION_LIMIT_EXIT and browser_error(stdout) == "browser_session_limit"


# Only the exit-76 session limit is a SKIP state; every other start-up failure
# (other licence codes, API breaks) must exit 1 as browser_launch_failed.
for label, launch, want_code, want_error in launch_failure_cases():
    out = io.StringIO()
    with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=launch)}), contextlib.redirect_stdout(out):
        code = fixture_cli.main(["AKL", "WLG", "2026-12-01", "--json", "--browser"])
    assert (code, browser_error(out.getvalue())) == (want_code, want_error), (label, code, out.getvalue()[:300])
    assert browser_session_limit(code, out.getvalue()) is (want_error == "browser_session_limit"), label
print("[PASS] fixture only the CloakBrowser exit-76 session limit skips; other launch failures fail")

DATE = (date.today() + timedelta(days=7)).isoformat()
browser_required = os.getenv("COLAB_SMOKE_USE_BROWSER") == "1"
use_browser = browser_required or find_spec("cloakbrowser") is not None
cmd = [sys.executable, str(CLI), "AKL", "WLG", DATE, "--limit", "3", "--json"]
if use_browser:
    cmd.append("--browser")
proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
if use_browser and browser_session_limit(proc.returncode, proc.stdout):
    print("[SKIP] airnz-flights browser fare search: CloakBrowser concurrent-session limit reached "
          "(CloakBrowserLicenseError, exit 76); browser path not exercised")
    raise SystemExit(0)
if proc.returncode != 0:
    if use_browser and not browser_required:
        try:
            error_payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            error_payload = {}
        if error_payload.get("error") == "cloakbrowser_not_installed":
            fallback_cmd = [
                sys.executable,
                str(CLI),
                "AKL",
                "WLG",
                DATE,
                "--limit",
                "3",
                "--json",
            ]
            proc = subprocess.run(fallback_cmd, text=True, capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)
payload = json.loads(proc.stdout)
flights = payload.get("flights") or []
assert flights, "expected at least one Air NZ flight row"
first = flights[0]
segments = first.get("flights") or []
assert segments, first
assert segments[0].get("flight_number"), first
if payload.get("fare_search_blocked"):
    assert first.get("lowest_fare") is None, first
else:
    assert first.get("lowest_fare", {}).get("price") is not None, first
assert "booking_search_url" in payload, payload
price = first.get("lowest_fare", {}).get("adult_price") if first.get("lowest_fare") else "fare-blocked"
print(
    f"[PASS] live airnz-flights ({payload.get('source')}): {len(flights)} flights, "
    f"first={segments[0].get('flight_number')} {first.get('departure')}->{first.get('arrival')} price={price}"
)
