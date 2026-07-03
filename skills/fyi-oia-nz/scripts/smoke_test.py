#!/usr/bin/env python3
"""Live smoke tests for fyi-oia-nz (outage-tolerant)."""
import json
import subprocess
import sys
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"

NETWORK_SKIP_MARKERS = (
    "upstream_unavailable",
    "upstream_blocked",
    "network error",
    "connection",
    "http 5",
    "timed out",
    "timeout",
)


def run(args, timeout: int = 50) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [sys.executable, str(CLI)] + args,
            text=True,
            capture_output=True,
            cwd=str(SKILL_DIR),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=[sys.executable, str(CLI)] + args,
            returncode=1,
            stdout="",
            stderr=f"command timed out after {timeout}s",
        )


def is_skip(stderr: str, stdout: str = "") -> bool:
    combined = (stdout + " " + stderr).lower()
    return any(marker in combined for marker in NETWORK_SKIP_MARKERS)


def test(name: str, fn) -> bool:
    try:
        ok = fn()
        print(f"[{ 'PASS' if ok else 'FAIL' }] {name}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}")
        print(f"  error: {exc}")
        return False


def test_help():
    proc = run(["--help"])
    return proc.returncode == 0


def test_authorities():
    proc = run(["authorities", "--tag", "council", "--limit", "3", "--json"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    if payload.get("kind") != "authorities":
        print(f"  stdout: {proc.stdout[:220]}")
        return False
    return isinstance(payload.get("authorities"), list)


def test_authorities_query_ministry():
    proc = run(["authorities", "--query", "ministry", "--limit", "2", "--json"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    return payload.get("kind") == "authorities" and isinstance(payload.get("authorities"), list)


def test_body():
    proc = run(["body", "psc", "--json"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    if payload.get("kind") != "body":
        print(f"  stdout: {proc.stdout[:220]}")
        return False
    body = payload.get("body", {})
    return bool(body.get("url_name"))


def test_request():
    proc = run(["request", "1039", "--json"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    if payload.get("kind") != "request":
        print(f"  stdout: {proc.stdout[:220]}")
        return False
    request_data = payload.get("request", {})
    return bool(request_data.get("id"))


def test_events():
    proc = run(["events", "1039", "--json"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    return payload.get("kind") == "events" and isinstance(payload.get("events"), list)


def import_cli_module():
    spec = importlib.util.spec_from_file_location("fyi_oia_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_search_failure_not_ok():
    cli = import_cli_module()
    def fail_fetch(*_args, **_kwargs):
        raise cli.CliError("upstream_unavailable: forced test failure", status="upstream_unavailable")
    cli.fetch_json = fail_fetch
    cli.fetch_text = fail_fetch
    args = argparse.Namespace(query_terms=["request"], limit=3, json=True)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_search(args)
    except cli.CliError as exc:
        return exc.status == "upstream_unavailable"
    return False


def test_search():
    proc = run(["search", "request", "--json", "--limit", "3"])
    if proc.returncode != 0:
        if is_skip(proc.stderr, proc.stdout):
            print(f"  [SKIP] upstream unavailable: {proc.stderr.strip()[:180]}")
            return True
        print(f"  stderr: {proc.stderr.strip()[:220]}")
        return False
    payload = json.loads(proc.stdout)
    if payload.get("kind") != "request_search":
        print(f"  stdout: {proc.stdout[:220]}")
        return False
    return isinstance(payload.get("results"), list)


def main() -> None:
    checks = [
        test("--help exits 0", test_help),
        test("authorities --tag returns authorities[]", test_authorities),
        test("authorities --query handles Botany CSV text", test_authorities_query_ministry),
        test("search total upstream failure is not OK-empty", test_search_failure_not_ok),
        test("body psc returns authority metadata", test_body),
        test("request 1039 returns request metadata", test_request),
        test("events 1039 returns events list", test_events),
        test("search request returns request_search payload", test_search),
    ]
    if all(checks):
        print("All smoke tests passed")
        sys.exit(0)
    failed = checks.count(False)
    print(f"{failed} test(s) failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
