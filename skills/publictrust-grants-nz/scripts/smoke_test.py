#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CLI = SKILL_DIR / "scripts" / "cli.py"
NETWORK_ERRORS = ("network error", "HTTP 403", "HTTP 429", "HTTP 5", "timed out", "search key or index may have changed")


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI)] + args,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        timeout=45,
    )


def flaky(result: subprocess.CompletedProcess) -> bool:
    text = (result.stderr + result.stdout).lower()
    return any(marker.lower() in text for marker in NETWORK_ERRORS)


def test(name: str, fn):
    try:
        status, detail = fn()
        print(f"[{status}] {name}")
        if detail:
            print(f"  {detail}")
        return status in {"PASS", "SKIP"}
    except Exception as e:
        print(f"[FAIL] {name}")
        print(f"  error: {e}")
        return False


results = []


def test_help():
    result = run(["--help"])
    return ("PASS", "") if result.returncode == 0 and "list-open" in result.stdout else ("FAIL", result.stderr[:300])


results.append(test("--help exits 0", test_help))


def test_empty_search_edge():
    result = run(["search", "", "--json"])
    if result.returncode != 0 and "requires a non-empty query" in result.stderr:
        return "PASS", "empty query rejected with clear message"
    return "FAIL", f"rc={result.returncode} stderr={result.stderr[:300]}"


results.append(test("empty search query edge case", test_empty_search_edge))


def test_search():
    result = run(["search", "youth", "--limit", "3", "--json"])
    if result.returncode != 0:
        if flaky(result):
            return "SKIP", result.stderr[:300]
        return "FAIL", result.stderr[:300]
    data = json.loads(result.stdout)
    needed = ["source_url", "index_name", "fetched_at", "grants"]
    if not all(k in data for k in needed):
        return "FAIL", f"missing keys in {data.keys()}"
    if not isinstance(data["grants"], list) or not data["grants"]:
        return "FAIL", "expected at least one grant for youth"
    grant = data["grants"][0]
    for key in ["id", "slug", "title", "url", "grant_type", "regions", "sectors", "applications_open_now"]:
        if key not in grant:
            return "FAIL", f"grant missing {key}: {grant}"
    return "PASS", f"returned {len(data['grants'])} grants"


results.append(test("search youth returns normalised grants", test_search))


def test_list_open_and_detail():
    result = run(["list-open", "--limit", "3", "--json"])
    if result.returncode != 0:
        if flaky(result):
            return "SKIP", result.stderr[:300]
        return "FAIL", result.stderr[:300]
    data = json.loads(result.stdout)
    grants = data.get("grants") or []
    if not grants:
        return "SKIP", "Public Trust currently reports no open grants"
    first = grants[0]
    if first.get("applications_open_now") is not True:
        return "FAIL", "list-open returned a grant not flagged open"
    ident = first.get("slug") or first.get("id")
    detail = run(["detail", ident, "--json"])
    if detail.returncode != 0:
        if flaky(detail):
            return "SKIP", detail.stderr[:300]
        return "FAIL", detail.stderr[:300]
    detail_data = json.loads(detail.stdout)
    if not detail_data.get("grant", {}).get("title"):
        return "FAIL", "detail response missing grant title"
    return "PASS", f"detail found {detail_data['grant']['title']}"


results.append(test("list-open plus detail", test_list_open_and_detail))

if all(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print(f"{results.count(False)} test(s) failed.")
    sys.exit(1)
