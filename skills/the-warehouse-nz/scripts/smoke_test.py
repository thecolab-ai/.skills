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
        timeout=30,
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


def print_cli_failure(result: subprocess.CompletedProcess) -> None:
    """Explain a failed CLI call. The CLI writes its JSON error payload to stdout, so a
    browser_launch_failed payload is echoed (one bounded line) next to stderr: the smoke
    runner treats that marker as a hard failure, even when another check hit a network block."""
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict) and payload.get("error") == "browser_launch_failed":
        message = " ".join(str(payload.get("message", "")).split())
        message = message.removeprefix("browser_launch_failed:").strip()[:300]
        print(f"  error: browser_launch_failed: {message}")
    print(f"  stderr: {result.stderr[:200]}")


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


def test_product_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("the_warehouse_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalize_tile_product(
        {
            "_gtm": {
                "id": "SYN-1",
                "name": "Synthetic Toy",
                "brand": "Example",
                "price": "19.99",
                "productThenPrice": "29.99",
                "productSecondaryNavigationCategory": "specials/toys",
                "promotionCallOutMessage": "Save $10",
            },
            "availability": "In stock",
            "source_url": "https://www.thewarehouse.co.nz/p/synthetic",
        }
    )
    assert record["sku"] == "SYN-1"
    assert record["price"] == 19.99 and record["then_price"] == 29.99
    assert record["is_special"] is True
    assert record["promotion"] == "Save $10"
    print("[PASS] fixture The Warehouse tile-product normalisation")
    return True


results.append(test("fixture product tile parser", test_product_fixture))


def test_browser_launch_failure_fixture():
    """Only CloakBrowser's exit-76 session limit is a SKIP state; every other start-up
    failure (other licence codes, API breaks) must exit 1 as browser_launch_failed."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("warehouse_cli_launch_fixture", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for label, launch, want_code, want_error in launch_failure_cases():
        out = io.StringIO()
        with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=launch)}), \
                contextlib.redirect_stdout(out):
            code = cli.main(["search", "toys", "--limit", "3", "--json", "--browser"])
        payload = json.loads(out.getvalue())
        assert (code, payload.get("error")) == (want_code, want_error), (label, code, payload)
        result = subprocess.CompletedProcess([], code, out.getvalue(), "")
        with patch(__name__ + ".USE_BROWSER", True), contextlib.redirect_stdout(io.StringIO()):
            assert browser_session_limit_skip(result, "fixture") is (want_error == "browser_session_limit"), label
    return True


results.append(test("fixture only the CloakBrowser exit-76 session limit skips; other launch failures fail", test_browser_launch_failure_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_search():
    result = run(with_browser(["search", "toys", "--limit", "3", "--json"]))
    if browser_session_limit_skip(result, "search"):
        return True
    if result.returncode != 0:
        print_cli_failure(result)
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list) or len(data["products"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] with at least one result")
        return False
    return True


results.append(test("search toys returns products[]", test_search))


def test_stores():
    result = run(with_browser(["stores", "--json"]))
    if browser_session_limit_skip(result, "stores"):
        return True
    if result.returncode != 0:
        print_cli_failure(result)
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stores"), list) or len(data["stores"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stores[] with at least one result")
        return False
    return True


results.append(test("stores returns stores[]", test_stores))


def test_specials():
    result = run(with_browser(["specials", "--limit", "3", "--json"]))
    if browser_session_limit_skip(result, "specials"):
        return True
    if result.returncode != 0:
        print_cli_failure(result)
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected products[] in specials response")
        return False
    return True


results.append(test("specials returns products[]", test_specials))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
