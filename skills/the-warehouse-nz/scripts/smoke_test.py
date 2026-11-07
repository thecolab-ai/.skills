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
    """CloakBrowser start-up denials (CloakBrowserLicenseError at launch or
    after the handshake) must be the machine-readable browser_unavailable state."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("warehouse_cli_launch_fixture", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    CloakBrowserLicenseError = type("CloakBrowserLicenseError", (RuntimeError,), {})

    def denied_launch(**kw):
        raise CloakBrowserLicenseError("CloakBrowser Pro: session limit reached for your plan.")

    def denied_goto(*a, **kw):
        raise CloakBrowserLicenseError("CloakBrowser Pro: session limit reached for your plan.")

    late_page = types.SimpleNamespace(goto=denied_goto)
    late_browser = types.SimpleNamespace(new_page=lambda: late_page, close=lambda: None)
    for launch in (denied_launch, lambda **kw: late_browser):
        out = io.StringIO()
        with patch.dict(sys.modules, {"cloakbrowser": types.SimpleNamespace(launch=launch)}), \
                contextlib.redirect_stdout(out):
            code = cli.main(["search", "toys", "--limit", "3", "--json", "--browser"])
        payload = json.loads(out.getvalue())
        assert code == 2, code
        assert payload["error"] == "browser_unavailable", payload
        assert "CloakBrowserLicenseError" in payload["message"], payload
    return True


results.append(test("fixture CloakBrowser launch denial is a clean browser_unavailable state", test_browser_launch_failure_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_search():
    result = run(with_browser(["search", "toys", "--limit", "3", "--json"]))
    if browser_unavailable_skip(result, "search"):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
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
    if browser_unavailable_skip(result, "stores"):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
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
    if browser_unavailable_skip(result, "specials"):
        return True
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
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
