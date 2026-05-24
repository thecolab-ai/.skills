#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=60,
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


results: list[bool] = []

# Current public Trade Me vehicle listing 5805102051 exposed this plate in
# listing details on 2026-05-24. Use a real listed vehicle rather than a
# vanity/example plate, because CarJam's public fields can disappear for
# non-current or placeholder plates.
SMOKE_PLATE = "PSP532"
SMOKE_MAKE = "TOYOTA"
SMOKE_MODEL = "HIACE"
SMOKE_YEAR = "2019"


def test_help() -> bool:
    result = run(["--help"])
    if result.returncode != 0:
        print(result.stderr[:300])
    return result.returncode == 0 and "CarJam NZ" in result.stdout


results.append(test("--help exits 0", test_help))


def test_lookup_json() -> bool:
    result = run(["lookup", SMOKE_PLATE, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    summary = payload.get("summary") or {}
    checks = [
        payload.get("vehicle"),
        summary.get("make") == SMOKE_MAKE,
        summary.get("model") == SMOKE_MODEL,
        summary.get("year_of_manufacture") == SMOKE_YEAR,
        summary.get("plate") == SMOKE_PLATE,
        payload.get("source_url", "").startswith("https://www.carjam.co.nz/car/?plate="),
    ]
    if not all(checks):
        print(f"  stdout: {result.stdout[:500]}")
        return False
    return True


results.append(test(f"lookup {SMOKE_PLATE} returns public vehicle summary", test_lookup_json))


def test_lookup_human() -> bool:
    result = run(["lookup", SMOKE_PLATE])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    return SMOKE_MAKE in result.stdout and SMOKE_MODEL in result.stdout and "Source: https://www.carjam.co.nz" in result.stdout


results.append(test(f"lookup {SMOKE_PLATE} human output includes vehicle/source", test_lookup_human))


def test_batch_json() -> bool:
    result = run(["batch", SMOKE_PLATE, SMOKE_PLATE, "--sleep", "0", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    vehicles = payload.get("vehicles")
    if not isinstance(vehicles, list) or len(vehicles) != 2:
        print(f"  stdout: {result.stdout[:500]}")
        return False
    return all(row.get("vehicle") for row in vehicles)


results.append(test("batch returns two compact vehicle rows", test_batch_json))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
