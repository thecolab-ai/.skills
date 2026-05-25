#!/usr/bin/env python3
"""Smoke tests for nzpost-tracking skill -- basic API and CLI checks."""
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

LIVE_TRACKING_NUMBER = "00794210392715622565"


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


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))


def test_track_subcommand_help():
    result = run(["track", "--help"])
    return result.returncode == 0 and "number" in result.stdout


results.append(test("track --help mentions number argument", test_track_subcommand_help))


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
    if not isinstance(data.get("events"), list):
        print(f"  Missing events[] in JSON response")
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
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    required_keys = {"tracking_reference", "status", "last_updated", "event_count", "events"}
    missing = required_keys - set(data.keys())
    if missing:
        print(f"  Missing keys in JSON: {missing}")
        return False
    if not isinstance(data["events"], list) or len(data["events"]) == 0:
        print(f"  events[] is empty or not a list")
        return False
    event = data["events"][0]
    event_keys = {"date_time", "status", "description", "edifact_code"}
    missing_ev = event_keys - set(event.keys())
    if missing_ev:
        print(f"  Missing keys in first event: {missing_ev}")
        return False
    return True


results.append(test("JSON output has correct shape and event fields", test_json_shape))


def test_invalid_tracking_number():
    result = run(["track", "NOT_A_VALID_NUMBER_!!!"])
    # Should exit non-zero with a helpful message
    return result.returncode != 0 and "tracking" in result.stderr.lower()


results.append(test("invalid tracking number exits non-zero with message", test_invalid_tracking_number))


def test_delivered_status():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    # This specific parcel is known to be delivered
    if "Delivered" not in data.get("status", ""):
        print(f"  Expected Delivered status, got: {data.get('status')}")
        return False
    return True


results.append(test("known delivered parcel shows Delivered status", test_delivered_status))


def test_events_chronological():
    result = run(["track", LIVE_TRACKING_NUMBER, "--json"])
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    events = data.get("events", [])
    if len(events) < 2:
        print("  Too few events to check order")
        return False
    dts = [ev.get("date_time", "") for ev in events if ev.get("date_time")]
    if dts != sorted(dts):
        print("  Events are not in chronological order")
        return False
    return True


results.append(test("events are returned in chronological order", test_events_chronological))


if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    failed = results.count(False)
    print(f"{failed} test(s) failed.")
    sys.exit(1)
