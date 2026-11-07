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


def browser_unavailable_skip(result: subprocess.CompletedProcess, what: str) -> bool:
    """True (after printing a SKIP) only for the CLI's explicit browser_unavailable state."""
    if not USE_BROWSER or result.returncode != 2:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict) or payload.get("error") != "browser_unavailable":
        return False
    print(f"[SKIP] {what}: CloakBrowser installed but could not start a browser session (licence/session limit or host)")
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
    """CloakBrowser start-up denials (CloakBrowserLicenseError at launch or
    after the handshake) must be the machine-readable browser_unavailable state."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("nz_council_cli_launch_fixture", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    CloakBrowserLicenseError = type("CloakBrowserLicenseError", (RuntimeError,), {})

    def denied_launch(**kw):
        raise CloakBrowserLicenseError("CloakBrowser Pro: session limit reached for your plan.")

    def denied_goto(*a, **kw):
        raise CloakBrowserLicenseError("CloakBrowser Pro: session limit reached for your plan.")

    late_browser = types.SimpleNamespace(new_page=lambda: types.SimpleNamespace(goto=denied_goto), close=lambda: None)
    for launch in (denied_launch, lambda **kw: late_browser):
        with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=launch)}):
            try:
                cli.fetch_text_cloakbrowser("https://example.invalid/pools")
            except cli.BrowserUnavailableError as exc:
                assert str(exc).startswith("browser_unavailable:") and "CloakBrowserLicenseError" in str(exc), exc
            else:
                raise AssertionError("launch denial must raise BrowserUnavailableError")
    out = io.StringIO()
    with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=denied_launch)}), \
            patch.object(cli, "fetch_text_result", return_value=("", "https://example.invalid/pools", 403, "HTTP 403")), \
            patch.object(sys, "argv", ["cli.py", "pools", "--council", "hutt", "--limit", "3", "--json", "--browser"]), \
            contextlib.redirect_stdout(out):
        try:
            cli.main()
        except SystemExit as exc:
            assert exc.code == 2, exc.code
        else:
            raise AssertionError("browser_unavailable must exit 2")
    payload = json.loads(out.getvalue())
    assert payload["error"] == "browser_unavailable", payload
    return True


results.append(test("fixture CloakBrowser launch denial is a clean browser_unavailable state", test_browser_launch_failure_fixture))


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
    if browser_unavailable_skip(result, "pools"):
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
