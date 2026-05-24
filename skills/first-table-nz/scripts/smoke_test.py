#!/usr/bin/env python3
import datetime as dt
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
        timeout=90,
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
_search_id = 1142


def test_help() -> bool:
    result = run(["--help"])
    if result.returncode != 0:
        print(result.stderr[:300])
    return result.returncode == 0 and "First Table NZ" in result.stdout


results.append(test("--help exits 0", test_help))


def test_city() -> bool:
    result = run(["city", "auckland", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    if payload.get("title") != "Auckland" or not payload.get("id"):
        print(f"  stdout: {result.stdout[:300]}")
        return False
    return isinstance(payload.get("subcities"), list) and isinstance(payload.get("tags"), list)


results.append(test("city auckland returns metadata/subcities/tags", test_city))


def test_search() -> bool:
    global _search_id
    result = run(["search", "sushi", "--city", "auckland", "--limit", "3", "--fetch-limit", "80", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    restaurants = payload.get("restaurants")
    if not isinstance(restaurants, list) or len(restaurants) < 1:
        print(f"  stdout: {result.stdout[:300]}")
        return False
    first = restaurants[0]
    if not first.get("id") or not first.get("url"):
        print(f"  first: {first}")
        return False
    _search_id = int(first["id"])
    return True


results.append(test("search sushi returns restaurants[]", test_search))


def test_detail() -> bool:
    result = run(["detail", str(_search_id), "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    return bool(payload.get("id") == _search_id and payload.get("title") and payload.get("url"))


results.append(test("detail <id> returns restaurant fields", test_detail))


def test_availability() -> bool:
    date = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    result = run(["availability", str(_search_id), "--date", date, "--people", "2", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    payload = json.loads(result.stdout)
    rows = payload.get("results")
    return payload.get("date") == date and isinstance(rows, list)


results.append(test("availability <id> returns results[]", test_availability))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
