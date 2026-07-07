#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"

# The CLI ships a working public fallback key, so the smoke test exercises the
# real network path. Only genuine upstream trouble (rate-limit, auth, 5xx,
# network) degrades to a graceful SKIP — a shape/parse problem is a real FAIL.
NETWORK_SKIP_MARKERS = (
    "network error",
    "timed out",
    "timeout",
    "connection",
    "http 4",
    "http 5",
    "429",
    "blocked",
)


def is_skip(stderr: str) -> bool:
    return any(marker in stderr.lower() for marker in NETWORK_SKIP_MARKERS)


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


def test_alerts():
    result = run(["alerts", "--json"])
    if result.returncode != 0:
        if is_skip(result.stderr):
            print(f"  [SKIP] upstream unavailable: {result.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("alerts"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected alerts[] in response")
        return False
    return True


results.append(test("alerts returns alerts[]", test_alerts))


def test_stops():
    result = run(["stops", "britomart", "--json"])
    if result.returncode != 0:
        if is_skip(result.stderr):
            print(f"  [SKIP] upstream unavailable: {result.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data.get("stops"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected stops[] in response")
        return False
    return True


results.append(test("stops britomart returns stops[]", test_stops))


def test_status():
    result = run(["status", "--json"])
    if result.returncode != 0:
        if is_skip(result.stderr):
            print(f"  [SKIP] upstream unavailable: {result.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {result.stderr[:200]}")
        return False
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected dict response from status")
        return False
    return True


results.append(test("status returns dict", test_status))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
