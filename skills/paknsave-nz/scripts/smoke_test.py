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
        timeout=30,
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


def test_search_payload_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paknsave_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    payload = module.search_payload("bread", "PAK-001", 8, 3, False)
    params = payload["algoliaQuery"]
    assert params["query"] == "bread"
    assert params["hitsPerPage"] == 8
    assert params["page"] == 2
    assert "onPromotion:true" not in params["filters"]
    assert module.normalize_product_id("12345") == "12345-EA-000"
    print("[PASS] fixture PAK'nSAVE search payload normalisation")
    return True


results.append(test("fixture search payload builder", test_search_payload_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_stores():
    result = run(["stores", "--query", "papakura", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    stores = json.loads(result.stdout)
    if not isinstance(stores, list) or len(stores) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected at least one PAK'nSAVE store for Papakura")
        return False
    return True


results.append(test("stores --query papakura returns >= 1 result", test_stores))


def test_search():
    result = run(["search", "milk", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("products"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected PAK'nSAVE search JSON to include products[]")
        return False
    return True


results.append(test("search milk returns products[]", test_search))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
