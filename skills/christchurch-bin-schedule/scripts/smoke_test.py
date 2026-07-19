#!/usr/bin/env python3
"""Live read-only smoke tests for the Christchurch bin schedule skill.

The CCC getProperty endpoint is protected by Incapsula bot detection and can
return 403 from datacentre/VPN IPs. Per repo convention the schedule test SKIPs
(rather than hard-fails) on that or any transient network error.
"""
import json
import importlib.util
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

# A well-known central-Christchurch address that resolves reliably via the
# (unprotected) CCC address suggest endpoint.
ADDRESS = "53 Hereford Street"


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


def is_blocked(stderr: str) -> bool:
    """True for upstream bot-protection / network failures we should skip on."""
    blockers = ("403", "bot protection", "network error", "timed out", "timeout")
    low = stderr.lower()
    return any(b in low for b in blockers)


results = []


def test_fixture_response_parsing():
    spec = importlib.util.spec_from_file_location("christchurch_bins_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    responses = iter([
        [{"RatingUnitID": 42, "FullStreetAddress": "53 Hereford Street", "StreetAddressID": 7}],
        {"address": "53 Hereford Street", "bins": {
            "routes": [{"material": "yellow", "day_of_week": "Tuesday"}],
            "collections": [
                {"next_planned_date": "2999-01-01", "material": "yellow", "out_of_date": "False"},
                {"next_planned_date": "2000-01-01", "material": "red", "out_of_date": "True"},
            ],
        }},
    ])
    cli.fetch_json = lambda *_args, **_kwargs: next(responses)
    address = cli.find_rating_unit_id("53 Hereford Street")
    schedule = cli.get_collection(42)
    return address["rating_unit_id"] == 42 and len(schedule["collections"]) == 1


results.append(test("fixture CCC address and collection response parsing", test_fixture_response_parsing))


def test_help():
    result = run(["--help"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_schedule():
    result = run([ADDRESS, "--json"])
    if result.returncode != 0:
        if is_blocked(result.stderr):
            print(f"  [SKIP] upstream blocked/unavailable: {result.stderr.strip()[:160]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not data.get("rating_unit_id"):
        print(f"  stdout: {result.stdout[:200]}")
        print(f"  Expected schedule JSON to include rating_unit_id for {ADDRESS!r}")
        return False
    if not isinstance(data.get("routes"), dict) or not isinstance(data.get("collections"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected routes{} and collections[] in schedule JSON")
        return False
    return True


results.append(test(f"{ADDRESS!r} returns rating_unit_id + schedule", test_schedule))


def test_no_match():
    # Pure address-suggest path (no bot-protected endpoint); a junk address
    # should exit non-zero with a clean error and no traceback.
    result = run(["zzzznotarealstreet 99999", "--json"])
    if result.returncode == 0:
        print("  Expected non-zero exit for a non-existent address")
        return False
    if is_blocked(result.stderr):
        print(f"  [SKIP] address suggest unavailable: {result.stderr.strip()[:160]}")
        return True
    if "Traceback" in result.stderr:
        print(f"  stderr: {result.stderr[:200]}")
        print("  Expected a clean error message, not a stack trace")
        return False
    return True


results.append(test("non-existent address fails cleanly", test_no_match))

if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
