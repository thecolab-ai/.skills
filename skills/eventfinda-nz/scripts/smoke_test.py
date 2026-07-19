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


def test_event_card_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("eventfinda_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = """
    <div class="card h-event">
      <h2 class="p-summary"><a href="/2026/synthetic-concert/auckland">Synthetic Concert</a></h2>
      <script>_efC(1, 98765)</script>
      <p class="meta-location">Example Theatre, Auckland</p>
      <span class="value-title" title="2026-07-19T19:30:00+12:00">Sun 19 Jul</span>
      <span class="category">Music</span>
      <span class="badge">Free</span>
    </div>
    """
    records = module.event_cards(source, 5)
    assert len(records) == 1
    assert records[0]["id"] == "98765"
    assert records[0]["title"] == "Synthetic Concert"
    assert records[0]["category"] == "Music"
    assert records[0]["url"].startswith("https://www.eventfinda.co.nz/")
    print("[PASS] fixture Eventfinda event-card parser")
    return True


results.append(test("fixture event card parser", test_event_card_fixture))


def test_help():
    result = run(["--help"])
    return result.returncode == 0


results.append(test("--help exits 0", test_help))

_first_event_url = None


def test_upcoming():
    global _first_event_url
    result = run(["upcoming", "--location", "auckland", "--limit", "3", "--json"])
    if result.returncode != 0:
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
    print("[PASS] live smoke assertions completed")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
