#!/usr/bin/env python3
"""Smoke test for the dataforseo skill.

Offline checks always run (no credit spent). Live checks run only when
DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are set — each spends a small amount
of DataForSEO credit.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
HAVE_CREDS = bool(
    (os.environ.get("DATAFORSEO_LOGIN") or os.environ.get("DATAFORSEO_USERNAME"))
    and os.environ.get("DATAFORSEO_PASSWORD")
)


def run(args, env=None):
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=90,
        env=env,
    )


def test(name, fn):
    try:
        ok = fn()
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {name}\n  error: {e}")
        return False
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


results = []


def t_help():
    return run(["--help"]).returncode == 0


def t_subcommand_help():
    # every subcommand should render help without credentials
    for cmd in ["serp", "volume", "suggestions", "ranked", "competitors", "domain", "backlinks",
                "refdomains", "ideas", "related", "intent", "appsearch", "appreviews", "validate"]:
        if run([cmd, "--help"]).returncode != 0:
            print(f"  {cmd} --help failed")
            return False
    return True


def t_missing_creds():
    # with creds stripped, a live command must fail cleanly (not traceback)
    stripped = ("DATAFORSEO_LOGIN", "DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD")
    env = {k: v for k, v in os.environ.items() if k not in stripped}
    r = run(["serp", "test"], env=env)
    if r.returncode == 0:
        print("  expected non-zero exit without credentials")
        return False
    if "missing DATAFORSEO_LOGIN" not in r.stderr:
        print(f"  stderr: {r.stderr[:200]}")
        return False
    if "Traceback" in r.stderr:
        print("  leaked a traceback instead of a clean error")
        return False
    return True


def t_bad_location():
    # unknown location alias should fail before hitting the network
    env = dict(os.environ, DATAFORSEO_LOGIN="x", DATAFORSEO_PASSWORD="y")
    r = run(["serp", "test", "--location", "atlantis"], env=env)
    return r.returncode != 0 and "unknown --location" in r.stderr


results.append(test("--help exits 0", t_help))
results.append(test("every subcommand --help exits 0 (no creds needed)", t_subcommand_help))
results.append(test("missing credentials fails cleanly", t_missing_creds))
results.append(test("unknown --location fails before network", t_bad_location))


def t_live_serp():
    if not HAVE_CREDS:
        print("  [SKIP] requires DATAFORSEO_LOGIN/PASSWORD")
        return True
    r = run(["serp", "garden planner", "--json", "--limit", "5"])
    if r.returncode != 0:
        print(f"  stderr: {r.stderr[:300]}")
        return False
    data = json.loads(r.stdout)
    if "items" not in data:
        print(f"  stdout: {r.stdout[:200]}")
        return False
    return True


def t_live_volume():
    if not HAVE_CREDS:
        print("  [SKIP] requires DATAFORSEO_LOGIN/PASSWORD")
        return True
    r = run(["volume", "garden planner", "--json"])
    if r.returncode != 0:
        print(f"  stderr: {r.stderr[:300]}")
        return False
    json.loads(r.stdout)
    return True


results.append(test("live: serp returns items[] (skips without creds)", t_live_serp))
results.append(test("live: volume returns JSON (skips without creds)", t_live_volume))

if all(results):
    print("All tests passed.")
    sys.exit(0)
print(f"{results.count(False)} test(s) failed.")
sys.exit(1)
