#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
SKILL_NAME = "eventfinda-nz"

_ANTIBOT_SIGNALS = (
    "just a moment",
    "cloudflare",
    "attention required",
    "checking your browser",
    "status 403",
    "status 406",
    "http 403",
    "http 406",
    "403 forbidden",
)


def _is_antibot(result: subprocess.CompletedProcess) -> bool:
    combined = (result.stdout + result.stderr).lower()
    return any(sig in combined for sig in _ANTIBOT_SIGNALS)


def _skip_if_antibot(result: subprocess.CompletedProcess) -> None:
    if _is_antibot(result):
        print(f"[SKIP] {SKILL_NAME} — upstream anti-bot block")
        sys.exit(0)


def run(args: list) -> subprocess.CompletedProcess:
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


results = []


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_first_event_url = None


def test_upcoming():
    global _first_event_url
    result = run(["upcoming", "--location", "auckland", "--limit", "3", "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    upcoming = json.loads(result.stdout)
    if not isinstance(upcoming.get("events"), list) or len(upcoming["events"]) < 1:
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected upcoming JSON to include events[]")
        return False
    first = upcoming["events"][0]
    if not isinstance(first.get("title"), str) or not isinstance(first.get("url"), str):
        print("  Expected first upcoming event to include title and url")
        return False
    _first_event_url = str(first["url"])
    return True


results.append(test("upcoming auckland returns events[] with title and url", test_upcoming))


def test_search():
    result = run(["search", "music", "--limit", "3", "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    search = json.loads(result.stdout)
    if not isinstance(search.get("events"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected search JSON to include events[]")
        return False
    return True


results.append(test("search music returns events[]", test_search))


def test_event_detail():
    if not _first_event_url:
        print("  No event URL captured from upcoming")
        return False
    result = run(["event", _first_event_url, "--json"])
    if result.returncode != 0:
        _skip_if_antibot(result)
        print(f"  stderr: {result.stderr[:200]}")
        return False
    detail = json.loads(result.stdout)
    event = detail.get("event") or {}
    if not event.get("title") or not isinstance(event.get("sessions"), list):
        print(f"  stdout: {result.stdout[:200]}")
        print("  Expected event detail JSON to include title and sessions[]")
        return False
    return True


results.append(test("event <url> returns title and sessions[]", test_event_detail))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
