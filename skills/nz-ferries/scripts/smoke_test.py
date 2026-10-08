#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import types
from unittest.mock import patch
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
USE_BROWSER = os.environ.get("COLAB_SMOKE_USE_BROWSER") == "1"


def run(args: list) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )
    if result.returncode != 0 and is_transient(result.stderr):
        result = subprocess.run([sys.executable, str(CLI)] + args,
            capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=45)
    return result


def is_transient(stderr):
    return any(marker in stderr.lower() for marker in ('network error', 'timed out', 'http 5', 'http 429'))


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


def test_sealink_slot_fixture():
    import datetime
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_ferries_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalize_sealink_slot(
        "auckland-waiheke",
        {"name": "Auckland to Waiheke"},
        datetime.date(2026, 7, 19),
        {
            "departureTime": "11:30 PM",
            "arrivalTime": "12:15 AM",
            "departureLocation": "Auckland",
            "arrivalLocation": "Waiheke",
            "ferryName": "Synthetic Ferry",
            "fareTypes": [{"code": "ADULT", "price": 49.0}],
        },
    )
    assert record["departure_datetime"].startswith("2026-07-19T23:30")
    assert record["arrival_datetime"].startswith("2026-07-20T00:15")
    assert record["fare_summary"]["adult"] == 49.0
    print("[PASS] fixture SeaLink sailing normalisation")
    return True


def test_bounded_live_fixture():
    import importlib.util
    spec = importlib.util.spec_from_file_location('ferries_budget_cli', CLI)
    cli = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    transient = subprocess.CompletedProcess([], 1, '', 'network error: timed out')
    schema = subprocess.CompletedProcess([], 1, '', 'unexpected timetable schema')
    with patch.object(subprocess, 'run', return_value=transient) as probe:
        assert run(['cook-strait', '--json']).returncode == 1 and probe.call_count == 2
    with patch.object(subprocess, 'run', return_value=schema) as probe:
        assert run(['cook-strait', '--json']).returncode == 1 and probe.call_count == 1
    calls = []
    page = types.SimpleNamespace(goto=lambda *a, **kw: calls.append(kw),
                                 content=lambda: '<html><h1>Synthetic timetable</h1></html>')
    browser = types.SimpleNamespace(new_page=lambda: page, close=lambda: None)
    with patch.dict(sys.modules, {'cloakbrowser': types.SimpleNamespace(launch=lambda **kw: browser)}):
        import datetime
        result = cli.fetch_fullers_public_page_with_browser({'from': 'Example', 'to': 'Example Island'}, datetime.date(2026, 10, 8))
    assert result['status'] == 'loaded' and calls == [{'wait_until': 'domcontentloaded', 'timeout': 10000}]
    assert cli.looks_browser_blocked('<html>captcha</html>')
    return True

results.append(test('fixture bounded retries preserve schema failures and browser navigation deadline', test_bounded_live_fixture))

results.append(test("fixture SeaLink slot parser", test_sealink_slot_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_operators():
    result = run(["operators", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("operators"), list) or len(data["operators"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected operators[] with at least one result")
        return False
    return True


results.append(test("operators returns operators[]", test_operators))


def test_routes():
    result = run(["routes", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("routes"), list) or len(data["routes"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected routes[] with at least one result")
        return False
    return True


results.append(test("routes returns routes[]", test_routes))


def test_cook_strait():
    result = run(["cook-strait", "--json"])
    if result.returncode != 0:
        if is_transient(result.stderr):
            print('[SKIP] Cook Strait public timetable temporarily unavailable after two bounded attempts')
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    assert {'source_url', 'publisher', 'retrieved_at'} <= data['meta'].keys()
    if not isinstance(data.get("sailings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected sailings[] in cook-strait response")
        return False
    return True


results.append(test("live cook-strait returns sailings[]", test_cook_strait))


def test_fullers_browser_probe():
    if not USE_BROWSER:
        print('[SKIP] optional Fullers browser probe not enabled')
        return True
    result = run(["sailings", "auckland-devonport", "--json", "--browser"])
    if result.returncode != 0:
        if is_transient(result.stderr):
            print('[SKIP] Fullers/AT public schedule temporarily unavailable after two bounded attempts')
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    probe = data.get("browser_probe")
    if not isinstance(probe, dict) or probe.get("status") not in {"loaded", "blocked"}:
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected browser_probe with loaded/blocked status")
        return False
    if not isinstance(data.get("sailings"), list):
        print("  Expected AT GTFS fallback sailings[] alongside browser probe")
        return False
    return True


results.append(test("live fullers browser probe returns status", test_fullers_browser_probe))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
