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


def test_quote_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nzx_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.simplify_quote(
        {
            "code": "SYN",
            "description": "Synthetic Issuer",
            "currency": "NZD",
            "priceAmount": "10.25",
            "priceChangeAmount": "0.25",
            "priceChangeRelative": "0.025",
            "totalVolume": "1000",
        }
    )
    assert record["code"] == "SYN"
    assert record["price"] == 10.25
    assert record["change_percent"] == 2.5
    assert record["volume"] == 1000
    print("[PASS] fixture NZX quote normalisation")
    return True


results.append(test("fixture quote parser", test_quote_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_index():
    result = run(["index", "--name", "nzx50", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("indices"), list) or len(data["indices"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected indices[] with at least one result")
        return False
    return True


results.append(test("index --name nzx50 returns indices[]", test_index))


def test_quote():
    result = run(["quote", "FPH", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("quotes"), list) or len(data["quotes"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected quotes[] with at least one result")
        return False
    if not data["quotes"][0].get("code"):
        print("  Expected quotes[0].code to be set")
        return False
    return True


results.append(test("quote FPH returns quotes[] with code", test_quote))


def test_search():
    result = run(["search", "fisher", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("results"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected results[] in search response")
        return False
    return True


results.append(test("search fisher returns results[]", test_search))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
