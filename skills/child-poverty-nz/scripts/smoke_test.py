#!/usr/bin/env python3
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=120,
    )


def test(name: str, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_release_zip_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("child_poverty_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("child-poverty-national.csv", "Measure,Year,Estimate\nMEASA,2025,12.5\n")
        archive.writestr("child-poverty-reg-eth-dis.csv", "Measure,Group,Estimate\nMEASA,Auckland,11.0\n")
    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
        national = module.national_rows(archive)
        breakdown = module.dem_rows(archive)
    assert national == [{"Measure": "MEASA", "Year": "2025", "Estimate": "12.5"}]
    assert breakdown[0]["Group"] == "Auckland"
    print("[PASS] fixture Stats NZ child-poverty release ZIP parser")
    return True


results.append(test("fixture release ZIP parser", test_release_zip_fixture))


def test_help():
    return run(["--help"]).returncode == 0


results.append(test("--help exits 0", test_help))


def test_measures():
    result = run(["measures", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if data.get("count") != 9:
        print(f"  expected 9 measures, got {data.get('count')}")
        return False
    return True


results.append(test("measures lists 9 CPRA codes", test_measures))


def test_latest():
    result = run(["latest", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("year"), int):
        print("  expected integer year")
        return False
    primary = next((m for m in data.get("measures", []) if m["code"] == "MEASA"), None)
    if not primary or primary.get("proportion_percent") is None:
        print("  expected MEASA proportion_percent to be set")
        return False
    return True


results.append(test("latest returns headline measures", test_latest))


def test_national():
    result = run(["national", "--measure", "MEASA", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    latest = data.get("latest")
    if not isinstance(latest, dict) or latest.get("proportion_percent") is None:
        print(f"  stdout: {result.stdout[:200]}")
        return False
    return True


results.append(test("national returns latest.proportion_percent", test_national))


def test_breakdown():
    result = run(["breakdown", "--measure", "MEASA", "--by", "region", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("breakdown"):
        print("  expected non-empty breakdown")
        return False
    return True


results.append(test("breakdown by region returns rows", test_breakdown))


def test_releases():
    result = run(["releases", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("releases"):
        print("  expected at least one release")
        return False
    return True


results.append(test("releases discovers a CSV release", test_releases))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
