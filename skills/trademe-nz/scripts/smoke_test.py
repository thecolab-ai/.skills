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


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_listing_id = None


def test_search_marketplace():
    global _listing_id
    result = run(["search", "iphone", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    marketplace = json.loads(result.stdout)
    if not isinstance(marketplace.get("listings"), list) or len(marketplace["listings"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Trade Me marketplace search JSON to include listings[]")
        return False
    _listing_id = str(marketplace["listings"][0].get("listing_id", ""))
    return True


results.append(test("search iphone returns listings[]", test_search_marketplace))


def test_listing():
    if not _listing_id:
        print("  No listing_id captured from search")
        return False
    result = run(["listing", _listing_id, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    listing = json.loads(result.stdout)
    if not listing.get("listing", {}).get("listing_id"):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Trade Me listing JSON to include listing.listing_id")
        return False
    return True


results.append(test("listing <id> returns listing.listing_id", test_listing))


def test_search_property_rent():
    result = run([
        "search", "auckland",
        "--type", "property-rent",
        "--region", "auckland",
        "--bedrooms-min", "2",
        "--price-max", "800",
        "--limit", "3",
        "--json",
    ])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    property_data = json.loads(result.stdout)
    if not isinstance(property_data.get("listings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Trade Me property-rent search JSON to include listings[]")
        return False
    return True


results.append(test("search property-rent auckland returns listings[]", test_search_property_rent))


def test_search_motors():
    result = run([
        "search", "aqua",
        "--type", "motors",
        "--region", "auckland",
        "--price-max", "15000",
        "--limit", "3",
        "--json",
    ])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    motors = json.loads(result.stdout)
    if not isinstance(motors.get("listings"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Trade Me motors search JSON to include listings[]")
        return False
    return True


results.append(test("search motors auckland returns listings[]", test_search_motors))


def test_regions():
    result = run(["regions", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    regions = json.loads(result.stdout)
    if not isinstance(regions.get("regions"), list) or len(regions["regions"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected Trade Me regions JSON to include regions[]")
        return False
    return True


results.append(test("regions returns regions[]", test_regions))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
