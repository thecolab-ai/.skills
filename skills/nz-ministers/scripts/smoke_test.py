#!/usr/bin/env python3
"""Live read-only smoke tests for the nz-ministers skill.

`latest` is keyless and always exercised. `minister`/`articles` sit behind
Incapsula bot protection: when CloakBrowser is available (or COLAB_SMOKE_USE_BROWSER=1)
the test clears the challenge with --browser and asserts real data; otherwise it
asserts the clean machine-readable `clearance_required` blocked state. Network /
upstream challenges are treated as SKIP, not failures.
"""
import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
MINISTER = "hon-simeon-brown"


def run(args, timeout=120):
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=timeout,
    )


def test(name, fn):
    try:
        ok = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}\n  error: {e}")
        return False


def browser_available():
    if os.environ.get("COLAB_SMOKE_USE_BROWSER"):
        return True
    try:
        import cloakbrowser  # noqa: F401
        return True
    except Exception:
        return False


def is_transient(stderr):
    low = stderr.lower()
    return any(s in low for s in ("network error", "http 5", "timeout", "timed out",
                                  "browser_blocked", "temporarily blocked"))


results = []
WANT_BROWSER = browser_available()


def test_fixture_rss_parser():
    spec = importlib.util.spec_from_file_location("nz_ministers_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    rows = cli.parse_rss_items("""<rss><channel><item><title>Example release</title><link>https://www.beehive.govt.nz/release/example</link><pubDate>Sun, 19 Jul 2026 00:00:00 GMT</pubDate></item></channel></rss>""")
    return len(rows) == 1 and rows[0]["type"] == "release" and rows[0]["slug"] == "example"


results.append(test("fixture Beehive RSS parsing", test_fixture_rss_parser))


def test_help():
    return run(["--help"]).returncode == 0


results.append(test("--help exits 0", test_help))


def test_latest():
    r = run(["latest", "--limit", "5", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(f"  [SKIP] upstream unavailable: {r.stderr.strip()[:140]}")
            return True
        print(f"  stderr: {r.stderr[:200]}")
        return False
    data = json.loads(r.stdout)
    items = data.get("results")
    if not isinstance(items, list) or not items:
        print(f"  stdout: {r.stdout[:200]}")
        print("  Expected non-empty results[] from the RSS feed")
        return False
    first = items[0]
    if not all(k in first for k in ("title", "url", "type", "published")):
        print(f"  Missing keys in item: {first}")
        return False
    return True


results.append(test("latest returns government releases (keyless)", test_latest))


def test_minister():
    args = ["minister", MINISTER, "--json"]
    if WANT_BROWSER:
        args.append("--browser")
    r = run(args)
    if WANT_BROWSER:
        if r.returncode != 0:
            if is_transient(r.stderr):
                print(f"  [SKIP] browser/upstream blocked: {r.stderr.strip()[:140]}")
                return True
            print(f"  stderr: {r.stderr[:200]}")
            return False
        data = json.loads(r.stdout)
        if not data.get("name") or not isinstance(data.get("roles"), list):
            print(f"  stdout: {r.stdout[:200]}")
            print("  Expected minister name + roles[]")
            return False
        return True
    # No browser: must return the clean clearance_required blocked state (exit 2).
    if r.returncode == 0:
        # A fresh clearance cache from a prior run is acceptable.
        data = json.loads(r.stdout)
        return bool(data.get("name"))
    if r.returncode != 2:
        print(f"  Expected exit 2 (clearance_required), got {r.returncode}")
        return False
    payload = json.loads(r.stderr)
    if payload.get("error") not in ("clearance_required", "clearance_expired"):
        print(f"  stderr: {r.stderr[:200]}")
        print("  Expected clearance_required error object")
        return False
    return True


results.append(test(f"minister {MINISTER} ({'browser' if WANT_BROWSER else 'blocked-state'})", test_minister))


def test_articles():
    if not WANT_BROWSER:
        print("  [SKIP] articles needs browser clearance; not available on this host")
        return True
    r = run(["articles", MINISTER, "--limit", "5", "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(f"  [SKIP] browser/upstream blocked: {r.stderr.strip()[:140]}")
            return True
        print(f"  stderr: {r.stderr[:200]}")
        return False
    data = json.loads(r.stdout)
    items = data.get("results")
    if not isinstance(items, list):
        print(f"  stdout: {r.stdout[:200]}")
        print("  Expected results[] of articles")
        return False
    if items and not all(k in items[0] for k in ("title", "url", "type")):
        print(f"  Missing keys in article: {items[0]}")
        return False
    return True


results.append(test(f"articles {MINISTER}", test_articles))


def test_roles():
    if not WANT_BROWSER:
        print("  [SKIP] roles needs browser clearance; not available on this host")
        return True
    r = run(["roles", MINISTER, "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(f"  [SKIP] browser/upstream blocked: {r.stderr.strip()[:140]}")
            return True
        print(f"  stderr: {r.stderr[:200]}")
        return False
    data = json.loads(r.stdout)
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        print(f"  stdout: {r.stdout[:200]}")
        print("  Expected non-empty roles[]")
        return False
    if not all(k in roles[0] for k in ("portfolio", "position", "url")):
        print(f"  Missing keys in role: {roles[0]}")
        return False
    return True


results.append(test(f"roles {MINISTER}", test_roles))


def test_diary():
    if not WANT_BROWSER:
        print("  [SKIP] diary needs browser clearance; not available on this host")
        return True
    r = run(["diary", MINISTER, "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(f"  [SKIP] browser/upstream blocked: {r.stderr.strip()[:140]}")
            return True
        print(f"  stderr: {r.stderr[:200]}")
        return False
    data = json.loads(r.stdout)
    # latest_diary may be null if the minister has none published, but the key
    # and the archive_url must be present and well-formed.
    if "latest_diary" not in data or "archive_url" not in data:
        print(f"  stdout: {r.stdout[:200]}")
        print("  Expected latest_diary + archive_url keys")
        return False
    diary = data["latest_diary"]
    if diary is not None and not all(k in diary for k in ("title", "published", "pdf_url")):
        print(f"  Missing keys in diary: {diary}")
        return False
    return True


results.append(test(f"diary {MINISTER}", test_diary))

if all(results):
    print("All tests passed.")
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
