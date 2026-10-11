#!/usr/bin/env python3
"""Live read-only smoke tests for the nz-ministers skill.

`latest` is keyless and always exercised. `minister`/`articles` sit behind
Incapsula bot protection: when CloakBrowser is available (or COLAB_SMOKE_USE_BROWSER=1)
the test clears the challenge with --browser and asserts real data; otherwise it
asserts the clean machine-readable `clearance_required` blocked state. Network /
upstream challenges are treated as SKIP, not failures.
"""
import importlib.util
import json
import os
import subprocess
import types
from unittest.mock import patch
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
MINISTER = "hon-simeon-brown"


def run(args, timeout=45):
    result = subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=timeout, check=False,
    )
    if '--browser' not in args and result.returncode != 0 and is_transient(result.stderr):
        result = subprocess.run([sys.executable, str(CLI)] + args,
            capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=timeout, check=False)
    return result



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
    except Exception:  # noqa: BLE001 - optional dependency may fail during import
        return False


def is_transient(stderr):
    low = stderr.lower()
    return any(s in low for s in ("network error", "http 5", "timeout", "timed out",
                                  "browser_blocked", "temporarily blocked"))


def transient_skip_line(stderr, *, browser=False):
    _ = stderr  # keep the call site explicit, but never echo raw details
    reason = "browser/upstream blocked" if browser else "upstream unavailable"
    return f"  [SKIP] {reason}"


def test_transient_skip_line_is_sanitised():
    raw = "Traceback (most recent call last):\n  File \"x\", line 1, in <module>\nSyntaxError: invalid syntax"
    line = transient_skip_line(raw, browser=True)
    return line == "  [SKIP] browser/upstream blocked" and "Traceback" not in line and "SyntaxError" not in line and "\n" not in line


results = []
WANT_BROWSER = browser_available()
PROTECTED_UNAVAILABLE = False


def test_fixture_rss_parser():
    spec = importlib.util.spec_from_file_location("nz_ministers_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = cli
    spec.loader.exec_module(cli)
    rows = cli.parse_rss_items("""<rss><channel><item><title>Example release</title><link>https://www.beehive.govt.nz/release/example</link><pubDate>Sun, 19 Jul 2026 00:00:00 GMT</pubDate></item></channel></rss>""")
    return len(rows) == 1 and rows[0]["type"] == "release" and rows[0]["slug"] == "example"


def test_bounded_retries():
    transient = subprocess.CompletedProcess([], 1, '', 'network error: timed out')
    schema = subprocess.CompletedProcess([], 1, '', 'could not parse beehive RSS')
    with patch.object(subprocess, 'run', return_value=transient) as probe:
        assert run(['latest', '--json']).returncode == 1 and probe.call_count == 2
    with patch.object(subprocess, 'run', return_value=schema) as probe:
        assert run(['latest', '--json']).returncode == 1 and probe.call_count == 1
    spec = importlib.util.spec_from_file_location('ministers_budget_cli', CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    calls = []
    page = types.SimpleNamespace(
        goto=lambda *a, **kw: calls.append(('goto', kw)),
        wait_for_timeout=lambda value: calls.append(('wait', value)),
        content=lambda: '<html>incapsula synthetic blocked page</html>')
    browser = types.SimpleNamespace(new_page=lambda: page, close=lambda: None)
    with patch.dict(sys.modules, {'cloakbrowser': types.SimpleNamespace(launch=lambda **kw: browser)}):
        try:
            cli._browser_fetch('https://www.beehive.govt.nz/minister/synthetic')
        except cli.ClearanceUnavailable as exc:
            assert str(exc).startswith('browser_blocked:')
        else:
            raise AssertionError('blocked browser page must fail explicitly')
    assert {'source_url', 'publisher', 'retrieved_at'} <= cli.with_provenance({'source': cli.RSS_URL})['meta'].keys()
    assert calls[0][1]['timeout'] == 10000
    assert [value for kind, value in calls if kind == 'wait'] == [1000] * 4
    return True

results.append(test('fixture bounded transient retries, schema failures and browser deadline', test_bounded_retries))

results.append(test("fixture Beehive RSS parsing", test_fixture_rss_parser))
results.append(test("transient skip line is sanitised", test_transient_skip_line_is_sanitised))


def test_help():
    return run(["--help"]).returncode == 0


results.append(test("--help exits 0", test_help))


def test_latest():
    r = run(["latest", "--limit", "5", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(transient_skip_line(r.stderr))
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


results.append(test("live latest returns government releases (keyless)", test_latest))


def test_minister():
    global PROTECTED_UNAVAILABLE
    args = ["minister", MINISTER, "--json"]
    if WANT_BROWSER:
        args.append("--browser")
    r = run(args)
    if r.returncode != 0 and is_transient(r.stderr):
        PROTECTED_UNAVAILABLE = True
        print(transient_skip_line(r.stderr, browser=WANT_BROWSER))
        return True
    if WANT_BROWSER:
        if r.returncode != 0:
            if is_transient(r.stderr):
                print(transient_skip_line(r.stderr, browser=True))
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


results.append(test(f"{'live' if WANT_BROWSER else 'contract'} minister {MINISTER} ({'browser' if WANT_BROWSER else 'blocked-state'})", test_minister))


def test_articles():
    if not WANT_BROWSER or PROTECTED_UNAVAILABLE:
        print("  [SKIP] articles needs browser clearance; not available on this host")
        return True
    r = run(["articles", MINISTER, "--limit", "5", "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(transient_skip_line(r.stderr, browser=True))
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


results.append(test(f"live articles {MINISTER}", test_articles))


def test_roles():
    if not WANT_BROWSER or PROTECTED_UNAVAILABLE:
        print("  [SKIP] roles needs browser clearance; not available on this host")
        return True
    r = run(["roles", MINISTER, "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(transient_skip_line(r.stderr, browser=True))
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


results.append(test(f"live roles {MINISTER}", test_roles))


def test_diary():
    if not WANT_BROWSER or PROTECTED_UNAVAILABLE:
        print("  [SKIP] diary needs browser clearance; not available on this host")
        return True
    r = run(["diary", MINISTER, "--browser", "--json"])
    if r.returncode != 0:
        if is_transient(r.stderr):
            print(transient_skip_line(r.stderr, browser=True))
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


results.append(test(f"live diary {MINISTER}", test_diary))

if all(results):
    print("All tests passed.")
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
