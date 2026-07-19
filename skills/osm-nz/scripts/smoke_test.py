#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

SAMPLE_OVERPASS = {
    "elements": [
        {
            "type": "node",
            "id": 1001,
            "lat": -36.84860,
            "lon": 174.76340,
            "tags": {"amenity": "cafe", "name": "Alpha Cafe", "addr:street": "Queen Street"},
        },
        {
            "type": "node",
            "id": 1002,
            "lat": -36.84980,
            "lon": 174.76500,
            "tags": {"amenity": "cafe", "name": "Alpha Cafe", "addr:street": "High Street"},
        },
        {
            "type": "way",
            "id": 2001,
            "center": {"lat": -36.85020, "lon": 174.76290},
            "tags": {"shop": "supermarket", "name": "Metro Grocery"},
        },
        {
            "type": "node",
            "id": 3001,
            "lat": -36.85100,
            "lon": 174.76450,
            "tags": {"highway": "bus_stop", "name": "Stop A"},
        },
        {
            "type": "node",
            "id": 4001,
            "lat": -36.84870,
            "lon": 174.76350,
            "tags": {"amenity": "cafe"},
        },
    ]
}

FOOD_OVERPASS = {"elements": SAMPLE_OVERPASS["elements"][:2]}


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


def load_cli() -> Any:
    spec = importlib.util.spec_from_file_location("osm_nz_cli", CLI)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load CLI module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI_MODULE = load_cli()


def run(args: list[str], payload: dict[str, Any] | None = None) -> Result:
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_argv = sys.argv[:]
    old_fetch = CLI_MODULE.fetch_overpass
    CLI_MODULE.fetch_overpass = lambda _query: payload if payload is not None else SAMPLE_OVERPASS
    sys.argv = [str(CLI), *args]
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                CLI_MODULE.main()
                code = 0
            except SystemExit as exc:
                if exc.code is None:
                    code = 0
                elif isinstance(exc.code, int):
                    code = exc.code
                else:
                    code = 1
    finally:
        sys.argv = old_argv
        CLI_MODULE.fetch_overpass = old_fetch
    return Result(code, stdout.getvalue(), stderr.getvalue())


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results: list[bool] = []

results.append(test("contract --help exits 0", lambda: run(["--help"]).returncode == 0))

results.append(test("contract categories lists filters", lambda: (
    (r := run(["categories"])).returncode == 0 and "food" in r.stdout
)))


def test_categories_json() -> bool:
    result = run(["categories", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    return data.get("kind") == "categories" and any(
        item.get("name") == "transport" for item in data.get("categories", [])
    )


results.append(test("contract categories --json emits structured filters", test_categories_json))


def test_nearby_json() -> bool:
    result = run(["nearby", "-36.8485", "174.7633", "--radius", "2000", "--limit", "5", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    rows = data.get("results")
    if not isinstance(rows, list) or len(rows) != 4:
        print(f"  stdout: {result.stdout[:300]}")
        print("  Expected four named POI results from fixture")
        return False
    if sum(1 for row in rows if row.get("name") == "Alpha Cafe") != 2:
        print("  Expected same-name POIs at different coordinates to be preserved")
        return False
    required = {"distance_m", "walking_min", "travel_mode", "osm_type", "osm_id", "osm_url"}
    return required.issubset(rows[0])


results.append(test("fixture nearby --json normalizes source results", test_nearby_json))


def test_food_filter() -> bool:
    result = run(
        ["nearby", "-36.8485", "174.7633", "--category", "food", "--limit", "5", "--json"],
        FOOD_OVERPASS,
    )
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    data = json.loads(result.stdout)
    rows = data.get("results")
    return data.get("category") == "food" and isinstance(rows, list) and len(rows) == 2


results.append(test("fixture nearby --category food returns source rows", test_food_filter))

results.append(test("contract nearby invalid category errors cleanly", lambda: (
    (r := run(["nearby", "-36.8485", "174.7633", "--category", "nonexistent"])).returncode != 0 and
    "unknown category" in r.stderr.lower() and "traceback" not in r.stderr.lower()
)))

results.append(test("contract nearby invalid coordinate errors cleanly", lambda: (
    (r := run(["nearby", "not-a-lat", "174.7633", "--json"])).returncode != 0 and
    "latitude must be a number" in r.stderr.lower() and "traceback" not in r.stderr.lower()
)))

results.append(test("contract nearby out-of-bounds coordinate errors cleanly", lambda: (
    (r := run(["nearby", "51.5007", "-0.1246", "--json"])).returncode != 0 and
    "within new zealand bounds" in r.stderr.lower() and "traceback" not in r.stderr.lower()
)))

results.append(test("contract nearby excessive radius errors cleanly", lambda: (
    (r := run(["nearby", "-36.8485", "174.7633", "--radius", "100000", "--json"])).returncode != 0 and
    "radius must be between" in r.stderr.lower() and "traceback" not in r.stderr.lower()
)))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
