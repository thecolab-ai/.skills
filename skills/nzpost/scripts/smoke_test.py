#!/usr/bin/env python3
"""Smoke tests for nzpost skill -- basic API and CLI checks."""
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

LIVE_TRACKING_NUMBER = "00794210392715622565"
UNKNOWN_TRACKING_NUMBER = "00000000000000000000"


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


def test_api_error_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("nzpost_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    message = module.extract_api_error(
        [
            {"errors": [{"code": "NOT_FOUND", "details": "No parcel found"}]},
            {"errors": [{"message": "Reference expired"}]},
        ]
    )
    assert message == "No parcel found; Reference expired"
    assert module.clean_text("<b>Safe &amp; clean</b>\x1b") == "Safe & clean"
    print("[PASS] fixture NZ Post API error normalisation")
    return True


results.append(test("fixture tracking response parser", test_api_error_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_track_subcommand_help():
    result = run(["track", "--help"])
    return result.returncode == 0 and "NUMBER" in result.stdout


results.append(test("track --help mentions NUMBER argument", test_track_subcommand_help))


def test_track_human_output():
    result = run(["track", LIVE_TRACKING_NUMBER])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    if "NZ Post Tracking" not in result.stdout:
        print(f"  Missing banner in output")
        return False
    if LIVE_TRACKING_NUMBER not in result.stdout:
        print(f"  Tracking number not echoed in output")
        return False
    return True


results.append(test("track returns human-readable output with banner", test_track_human_output))


def test_track_json_parses():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  stdout: {result.stdout[:200]}")
        return False
    parcels = data.get("parcels")
    if not isinstance(parcels, list) or len(parcels) == 0:
        print(f"  Missing parcels[] in JSON response, got: {list(data.keys())}")
        return False
    if not isinstance(parcels[0].get("events"), list):
        print(f"  Missing events[] in first parcel")
        return False
    return True


results.append(test("track --json output parses cleanly via json.loads", test_track_json_parses))


def test_json_no_banner():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    # JSON output must not contain the human banner
    if "NZ Post Tracking" in result.stdout:
        print(f"  Banner contamination in --json output")
        return False
    # Must parse as valid JSON (no leading text)
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  Output is not valid JSON")
        return False
    return True


results.append(test("--json output has no banner contamination", test_json_no_banner))


def test_json_shape():
    """Single-ref --json emits {\"parcels\": [{...}]} shape."""
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    # M5: single-ref JSON must be {"parcels": [...]}
    if "parcels" not in data:
        print(f"  Top-level key should be 'parcels', got: {list(data.keys())}")
        return False
    parcels = data["parcels"]
    if not isinstance(parcels, list) or len(parcels) == 0:
        print(f"  parcels[] is empty or not a list")
        return False
    parcel = parcels[0]
    required_keys = {"tracking_reference", "status", "last_updated", "event_count", "events"}
    missing = required_keys - set(parcel.keys())
    if missing:
        print(f"  Missing keys in parcel: {missing}")
        return False
    if not isinstance(parcel["events"], list) or len(parcel["events"]) == 0:
        print(f"  events[] is empty or not a list")
        return False
    event = parcel["events"][0]
    event_keys = {"date_time", "status", "description", "edifact_code"}
    missing_ev = event_keys - set(event.keys())
    if missing_ev:
        print(f"  Missing keys in first event: {missing_ev}")
        return False
    return True


results.append(test("JSON output has correct shape: parcels[0].events", test_json_shape))


def test_invalid_tracking_number():
    result = run(["track", "NOT_A_VALID_NUMBER_!!!"])
    # Should exit non-zero with a helpful message
    return result.returncode != 0 and "tracking" in result.stderr.lower()


results.append(test("invalid tracking number exits non-zero with message", test_invalid_tracking_number))


def test_too_long_tracking_number():
    result = run(["track", "1234567890123456789012345"])
    return result.returncode != 0 and "unrecognised tracking number format" in result.stderr


results.append(test("too-long numeric tracking number is rejected", test_too_long_tracking_number))


def test_unknown_tracking_number():
    result = run(["track", UNKNOWN_TRACKING_NUMBER, "--json"])
    if result.returncode == 0:
        print("  Expected non-zero exit for unknown tracking number")
        return False
    if result.stdout.strip():
        print(f"  Expected no stdout in --json error path, got: {result.stdout[:100]}")
        return False
    return "No data found" in result.stderr or "tracking lookup failed" in result.stderr


results.append(test("unknown valid-format tracking number exits non-zero", test_unknown_tracking_number))


def test_delivered_status():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    # M5: check inside parcels[0]
    parcels = data.get("parcels", [])
    if not parcels:
        print(f"  No parcels in response")
        return False
    status = parcels[0].get("status", "")
    if "Delivered" not in status:
        print(f"  Expected Delivered status, got: {status}")
        return False
    return True


results.append(test("known delivered parcel shows Delivered status", test_delivered_status))


def test_events_chronological():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    # M5: check inside parcels[0]
    parcels = data.get("parcels", [])
    if not parcels:
        return False
    events = parcels[0].get("events", [])
    if len(events) < 2:
        print("  Too few events to check order")
        return False
    dts = [ev.get("date_time", "") for ev in events if ev.get("date_time")]
    if dts != sorted(dts):
        print("  Events are not in chronological order")
        return False
    return True


results.append(test("events are returned in chronological order", test_events_chronological))


# ---------------------------------------------------------------------------
# Locations smoke tests
# ---------------------------------------------------------------------------

def test_locations_near_json():
    """locations --near 'Auckland CBD' --json parses as JSON with >=1 location."""
    result = run(["locations", "--near", "Auckland CBD", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    locs = data.get("locations", [])
    if len(locs) < 1:
        print(f"  Expected >=1 location, got {len(locs)}")
        return False
    return True


results.append(test("locations --near 'Auckland CBD' --json returns >=1 location", test_locations_near_json))


def test_locations_latlon_json():
    """locations --lat --lon --json returns >=1 location."""
    result = run(["locations", "--lat", "-36.8485", "--lon", "174.7633", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    locs = data.get("locations", [])
    if len(locs) < 1:
        print(f"  Expected >=1 location, got {len(locs)}")
        return False
    return True


results.append(test("locations --lat/-lon --json returns >=1 location", test_locations_latlon_json))


def test_locations_human_no_banner():
    """locations human output renders without banner contamination."""
    result = run(["locations", "--near", "Auckland CBD", "--limit", "3"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    # Human output should NOT start with NZ Post Tracking banner
    if result.stdout.startswith("NZ Post Tracking"):
        print("  Human output starts with tracking banner (contamination)")
        return False
    # Should have some output (location names)
    if not result.stdout.strip():
        print("  Empty output")
        return False
    return True


results.append(test("locations human output renders without banner contamination", test_locations_human_no_banner))


# ---------------------------------------------------------------------------
# Address smoke tests
# ---------------------------------------------------------------------------

def test_address_json():
    """address 'Papakura' --json parses as JSON with >=1 address."""
    result = run(["address", "Papakura", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    addrs = data.get("addresses", [])
    if len(addrs) < 1:
        print(f"  Expected >=1 address, got {len(addrs)}")
        return False
    return True


results.append(test("address 'Papakura' --json returns >=1 address", test_address_json))


# ---------------------------------------------------------------------------
# Multi-parcel track smoke tests
# ---------------------------------------------------------------------------

def test_track_multi_json():
    """track with two refs --json returns 2 results in parcels[]."""
    result = run(["track", LIVE_TRACKING_NUMBER, UNKNOWN_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    parcels = data.get("parcels", [])
    if len(parcels) != 2:
        print(f"  Expected 2 parcels, got {len(parcels)}")
        return False
    return True


results.append(test("track two refs --json returns 2 results", test_track_multi_json))


def test_track_single_regression():
    """Single track still works (regression)."""
    result = run(["track", LIVE_TRACKING_NUMBER])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:200]}")
        return False
    return "NZ Post Tracking" in result.stdout and LIVE_TRACKING_NUMBER in result.stdout


results.append(test("track single parcel still works (regression)", test_track_single_regression))


# ---------------------------------------------------------------------------
# L9: New smoke tests
# ---------------------------------------------------------------------------

def test_type_postshop():
    """--type postshop returns >=1 result near Auckland CBD."""
    result = run(["locations", "--near", "Auckland CBD", "--type", "postshop", "--limit", "5"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    if "No locations found" in result.stdout:
        print("  Got 'No locations found' for postshop near Auckland CBD")
        return False
    return bool(result.stdout.strip())


results.append(test("--type postshop returns >=1 result near Auckland CBD", test_type_postshop))


def test_type_postbox():
    """--type postbox returns >=1 result near Auckland CBD."""
    result = run(["locations", "--near", "Auckland CBD", "--type", "postbox", "--limit", "5"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    if "No locations found" in result.stdout:
        print("  Got 'No locations found' for postbox near Auckland CBD")
        return False
    return bool(result.stdout.strip())


results.append(test("--type postbox returns >=1 result near Auckland CBD", test_type_postbox))


def test_type_parcel_collect():
    """--type parcel-collect returns >=1 result near Auckland CBD."""
    result = run(["locations", "--near", "Auckland CBD", "--type", "parcel-collect", "--limit", "5"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    if "No locations found" in result.stdout:
        print("  Got 'No locations found' for parcel-collect near Auckland CBD")
        return False
    return bool(result.stdout.strip())


results.append(test("--type parcel-collect returns >=1 result near Auckland CBD", test_type_parcel_collect))


def test_type_all():
    """--type all returns >=1 result near Auckland CBD."""
    result = run(["locations", "--near", "Auckland CBD", "--type", "all", "--limit", "5"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    if "No locations found" in result.stdout:
        print("  Got 'No locations found' for all near Auckland CBD")
        return False
    return bool(result.stdout.strip())


results.append(test("--type all returns >=1 result near Auckland CBD", test_type_all))


def test_near_no_match_dies():
    """--near 'asdfjklqwerty_no_match' exits non-zero with helpful error."""
    result = run(["locations", "--near", "asdfjklqwerty_no_match"])
    if result.returncode == 0:
        print("  Expected non-zero exit for unresolvable location")
        return False
    return "geocode" in result.stderr.lower() or "could not" in result.stderr.lower()


results.append(test("--near 'asdfjklqwerty_no_match' exits non-zero with error", test_near_no_match_dies))


def test_near_clevedon_resolves_via_nzpost():
    """--near 'Clevedon' resolves via NZ Post KEYWORD API (coords ~-37.0, 175.0)."""
    result = run(["locations", "--near", "Clevedon", "--limit", "1", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    locs = data.get("locations", [])
    if not locs:
        print("  No locations returned near Clevedon")
        return False
    # The first location should be near Clevedon (~-37.0, 175.0), not Auckland CBD
    loc = locs[0]
    lat = loc.get("lat")
    if lat is None:
        print("  No lat field in location")
        return False
    # Clevedon is around -37.0 lat; Auckland CBD is -36.85
    # If geocoding is working via NZ Post KEYWORD, lat should be closer to -37.0
    if float(lat) > -36.9:
        print(f"  lat {lat} looks like Auckland CBD, not Clevedon -- geocoding may be falling back to OSM with wrong area")
        return False
    return True


results.append(test("--near 'Clevedon' resolves to Clevedon coords (not Auckland CBD)", test_near_clevedon_resolves_via_nzpost))


def test_multi_json_input_order():
    """Multi-ref --json preserves input order: first ref is parcels[0]."""
    # Use live ref as ref A and unknown as ref B
    ref_a = LIVE_TRACKING_NUMBER
    ref_b = UNKNOWN_TRACKING_NUMBER
    result = run(["track", ref_a, ref_b, "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    parcels = data.get("parcels", [])
    if len(parcels) < 2:
        print(f"  Expected >=2 parcels, got {len(parcels)}")
        return False
    if parcels[0].get("tracking_reference") != ref_a:
        print(f"  Expected parcels[0].tracking_reference={ref_a!r}, got {parcels[0].get('tracking_reference')!r}")
        return False
    if parcels[1].get("tracking_reference") != ref_b:
        print(f"  Expected parcels[1].tracking_reference={ref_b!r}, got {parcels[1].get('tracking_reference')!r}")
        return False
    return True


results.append(test("multi-ref --json preserves input order", test_multi_json_input_order))


def test_multi_json_dedup():
    """Passing same ref 3 times returns len(parcels)==1."""
    result = run(["track", LIVE_TRACKING_NUMBER, LIVE_TRACKING_NUMBER, LIVE_TRACKING_NUMBER, "--json"])
    # dedup note goes to stderr, but exit should succeed
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    parcels = data.get("parcels", [])
    if len(parcels) != 1:
        print(f"  Expected 1 parcel after dedup, got {len(parcels)}")
        return False
    return True


results.append(test("duplicate refs are deduped: 3x same ref -> 1 parcel", test_multi_json_dedup))


def test_address_limit():
    """address Papakura --limit 3 returns exactly 3 addresses."""
    result = run(["address", "Papakura", "--limit", "3", "--json"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return False
    addrs = data.get("addresses", [])
    if len(addrs) != 3:
        print(f"  Expected exactly 3 addresses, got {len(addrs)}")
        return False
    return True


results.append(test("address --limit 3 returns exactly 3 results (E1 guard)", test_address_limit))


def test_address_no_results_exits_zero():
    """address query returning zero results exits 0 with empty array."""
    result = run(["address", "xyznotarealplaceqqqq", "--json"])
    if result.returncode != 0:
        print(f"  Exited non-zero with returncode={result.returncode}, stderr={result.stderr[:200]}")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # May exit 0 with human "No addresses found." - also acceptable
        if "No addresses found" in result.stdout:
            return True
        print(f"  Could not parse stdout as JSON: {result.stdout[:100]}")
        return False
    addresses = data.get("addresses", [])
    if addresses:
        print(f"  Expected empty, got {len(addresses)} addresses")
        return False
    return True


results.append(test("address with no results exits 0 with empty list", test_address_no_results_exits_zero))


def test_locations_hours_not_always_unknown():
    """At least one location near Auckland CBD shows real hours (not 'hours unknown')."""
    result = run(["locations", "--near", "Auckland CBD", "--limit", "10"])
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return False
    lines = result.stdout.splitlines()
    today_lines = [l for l in lines if l.strip().startswith("Today:")]
    if not today_lines:
        print("  No 'Today:' lines found in output")
        return False
    non_unknown = [l for l in today_lines if "hours unknown" not in l]
    if not non_unknown:
        print(f"  All {len(today_lines)} locations show 'hours unknown' -- _today_hours is broken")
        return False
    return True


results.append(test("locations human output: at least one location shows real hours", test_locations_hours_not_always_unknown))


if all(results):
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    failed = results.count(False)
    print(f"{failed} test(s) failed.")
    sys.exit(1)
