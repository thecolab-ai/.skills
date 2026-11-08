#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
USE_BROWSER = os.environ.get("COLAB_SMOKE_USE_BROWSER") == "1"


def with_browser(args: list) -> list:
    return args + (["--browser"] if USE_BROWSER else [])


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=90,
    )


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


def browser_session_limit_skip(result: subprocess.CompletedProcess, what: str) -> bool:
    """True (after printing a SKIP) only for CloakBrowser's concurrent-session limit:
    exit 76 plus the CLI's machine-readable browser_session_limit payload. Every other
    browser start-up failure (browser_launch_failed, exit 1) stays a FAIL."""
    if not USE_BROWSER or result.returncode != SESSION_LIMIT_EXIT:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict) or payload.get("error") != "browser_session_limit":
        return False
    print(f"[SKIP] {what}: CloakBrowser concurrent-session limit reached (CloakBrowserLicenseError, exit 76); browser path not exercised")
    return True


def test(name: str, fn):
    try:
        ok = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_browser_launch_failure_fixture():
    """Only CloakBrowser's exit-76 session limit is a SKIP state; every other start-up
    failure (other licence codes, API breaks) must exit 1 as browser_launch_failed."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("nz_council_cli_launch_fixture", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for label, launch, want_code, want_error in launch_failure_cases():
        out = io.StringIO()
        with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=launch)}), \
                patch.object(cli, "fetch_text_result", return_value=("", "https://example.invalid/pools", 403, "HTTP 403")), \
                patch.object(sys, "argv", ["cli.py", "pools", "--council", "hutt", "--limit", "3", "--json", "--browser"]), \
                contextlib.redirect_stdout(out):
            try:
                cli.main()
            except SystemExit as exc:
                code = exc.code
            else:
                code = 0
        payload = json.loads(out.getvalue())
        assert (code, payload.get("error")) == (want_code, want_error), (label, code, payload)
        assert "Traceback" not in out.getvalue(), label
        result = subprocess.CompletedProcess([], code, out.getvalue(), "")
        with patch(__name__ + ".USE_BROWSER", True), contextlib.redirect_stdout(io.StringIO()):
            assert browser_session_limit_skip(result, "fixture") is (want_error == "browser_session_limit"), label
    return True


results.append(test("fixture only the CloakBrowser exit-76 session limit skips; other launch failures fail", test_browser_launch_failure_fixture))


def test_hours_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_council_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    hours = module.parse_ham_hours_table(
        """
        <table><tr><th>Facility</th><th>Monday</th><th>Tuesday</th></tr>
        <tr><td>Main pool</td><td>6am - 8pm</td><td>6am - 8pm</td></tr></table>
        """
    )
    assert hours == [{"label": "Main pool", "text": "Monday: 6am - 8pm; Tuesday: 6am - 8pm"}]
    print("[PASS] fixture council facility-hours parser")
    return True


results.append(test("fixture facility hours parser", test_hours_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_events():
    result = run(["events", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("events"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected events[] in response")
        return False
    return True


results.append(test("events returns events[]", test_events))


def test_pools():
    args = ["pools", "--council", "hutt" if USE_BROWSER else "akl", "--limit", "3", "--json"]
    result = run(with_browser(args))
    if browser_session_limit_skip(result, "pools"):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("pools"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected pools[] in response")
        return False
    return True


results.append(test("pools returns pools[]", test_pools))


def test_facilities():
    result = run(["facilities", "--council", "akl", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("facilities"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected facilities[] in response")
        return False
    return True


results.append(test("facilities akl returns facilities[]", test_facilities))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
