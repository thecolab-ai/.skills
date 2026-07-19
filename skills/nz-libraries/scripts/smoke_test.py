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


def test_bibliocommons_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nz_libraries_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    record = module.normalize_bibliocommons_bib(
        "christchurch",
        "SYNTHETIC-1",
        {
            "briefInfo": {
                "title": "Synthetic Book",
                "authors": ["Example, Alice", "Example, Bob"],
                "publicationDate": "2026",
                "format": "Book",
                "isbns": ["9780000000000"],
            },
            "availability": {"status": "Available", "availableCopies": 2, "totalCopies": 3},
        },
    )
    assert record["title"] == "Synthetic Book"
    assert record["author"] == "Example, Alice, Example, Bob"
    assert record["isbn"] == "9780000000000"
    assert "2 available" in record["availability"]
    print("[PASS] fixture BiblioCommons record normalisation")
    return True


results.append(test("fixture catalogue record parser", test_bibliocommons_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_networks():
    result = run(["networks", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("networks"), list) or len(data["networks"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected networks[] with at least one result")
        return False
    return True


results.append(test("networks returns networks[]", test_networks))


def test_branches_wellington():
    result = run(["branches", "--network", "wellington", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("branches"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected branches[] in response")
        return False
    return True


results.append(test("branches --network wellington returns branches[]", test_branches_wellington))


def test_search():
    result = run(["search", "hobbit", "--network", "auckland", "--limit", "3", "--json"])
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        if "network error" in detail.lower() or "blocked after" in detail.lower():
            print("[SKIP] search live assertion: upstream unavailable")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("results"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected results[] in search response")
        return False
    return True


results.append(test("search hobbit --network auckland returns results[]", test_search))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
