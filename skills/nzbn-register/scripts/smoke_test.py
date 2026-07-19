#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


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


def test_entity_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nzbn_register_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.simplify_entity(
        {
            "nzbn": "9429000000000",
            "entityName": "Synthetic Limited",
            "entityStatusDescription": "Registered",
            "tradingNames": [{"name": "Synthetic Trading"}, {"name": "No trading name"}],
            "addresses": {"addressList": [{"addressType": "REGISTERED", "address1": "1 Example Street", "postCode": "6011", "countryCode": "NZ"}]},
        },
        detail=True,
    )
    assert record["nzbn"] == "9429000000000"
    assert record["trading_names"] == ["Synthetic Trading"]
    assert record["addresses"][0]["address"] == "1 Example Street, 6011, NZ"
    assert record["url"].endswith("/9429000000000/")
    print("[PASS] fixture NZBN entity normalisation")
    return True


results.append(test("fixture entity parser", test_entity_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_nzbn = None


def test_search():
    global _nzbn
    result = run(["search", "the warehouse", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("entities"), list) or len(search["entities"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected NZBN search JSON to include entities[]")
        return False
    if not isinstance(search["entities"][0].get("nzbn"), str):
        print("  Expected first NZBN search result to include nzbn")
        return False
    _nzbn = str(search["entities"][0]["nzbn"])
    return True


results.append(test("search 'the warehouse' returns entities[].nzbn", test_search))


def test_lookup():
    if not _nzbn:
        print("  No NZBN captured from search")
        return False
    result = run(["lookup", _nzbn, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    lookup = json.loads(result.stdout)
    entity = lookup.get("entity") or {}
    if not entity.get("nzbn") or entity["nzbn"] != _nzbn:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected NZBN lookup JSON to include matching entity.nzbn")
        return False
    if not entity.get("entity_name"):
        print("  Expected NZBN lookup JSON to include entity.entity_name")
        return False
    return True


results.append(test("lookup <nzbn> returns matching entity", test_lookup))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
