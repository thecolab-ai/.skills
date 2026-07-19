#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")


def run(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def check(name: str, fn) -> bool:
    try:
        fn()
        print("[PASS]", name)
        return True
    except Skip as exc:
        print("[SKIP]", name, exc)
        return True
    except Exception as exc:
        print("[FAIL]", name, exc)
        return False


class Skip(Exception):
    pass


def json_command(args: list[str]) -> dict:
    proc = run(args)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        if any(term in stderr.lower() for term in ("timed out", "failed to reach", "http 5", "blocked")):
            raise Skip(stderr[:300])
        raise AssertionError(stderr[:500])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON: {exc}; output={proc.stdout[:300]!r}")


def help_check() -> None:
    proc = run(["--help"])
    assert proc.returncode == 0, proc.stderr
    assert "biosecurity" in proc.stdout.lower()


def sources_check() -> None:
    data = json_command(["sources", "--json"])
    assert data["kind"] == "sources"
    if data.get("status") == "partial" and data.get("errors"):
        raise Skip("source catalogue blocked by Incapsula")
    assert any(pkg.get("name") == "the-official-new-zealand-pest-register" for pkg in data.get("packages", []))


def pest_search_check() -> None:
    data = json_command(["pest", "search", "--query", "fruit fly", "--limit", "2", "--json"])
    if data.get("status") == "blocked":
        raise Skip("ONZPR blocked by Incapsula")
    assert data["records"], data
    assert data["records"][0]["pest_id"] is not None


def pest_no_results_check() -> None:
    data = json_command(["pest", "search", "--query", "zzzzzzzz unlikely organism", "--limit", "1", "--json"])
    if data.get("status") == "blocked":
        raise Skip("ONZPR blocked by Incapsula")
    assert data["records_filtered"] == 0, data


def notifiable_check() -> None:
    data = json_command(["notifiable", "--limit", "2", "--json"])
    if data.get("status") == "blocked":
        raise Skip("ONZPR blocked by Incapsula")
    assert data["records"], data
    assert all(record["notifiable"] is True for record in data["records"])


def responses_blocked_or_ok_check() -> None:
    data = json_command(["responses", "--json"])
    assert data.get("status") in ("ok", "blocked")
    if data.get("status") == "ok":
        assert data.get("responses")


def import_requirements_check() -> None:
    data = json_command(["import-requirements", "--commodity", "Apple", "--limit", "1", "--json"])
    if data.get("status") == "blocked":
        raise Skip("PIER blocked by Incapsula")
    assert data["status"] == "ok", data
    assert data["type_choices"], data
    assert data["searches"], data


def import_requirements_no_results_check() -> None:
    data = json_command(
        [
            "import-requirements",
            "--commodity",
            "zzzzzzzz unlikely commodity",
            "--limit",
            "1",
            "--json",
        ]
    )
    if data.get("status") == "blocked":
        raise Skip("PIER blocked by Incapsula")
    assert data["status"] == "not_found", data
    assert data["type_choices"] == [], data


def main() -> None:
    checks = [
        ("contract help", help_check),
        ("sources", sources_check),
        ("pest search happy path", pest_search_check),
        ("pest search no results edge", pest_no_results_check),
        ("notifiable filter", notifiable_check),
        ("import requirements happy path", import_requirements_check),
        ("import requirements no results edge", import_requirements_no_results_check),
        ("responses ok or blocked", responses_blocked_or_ok_check),
    ]
    ok = [check(name, fn) for name, fn in checks]
    if all(ok):
        print("All smoke checks passed or were skipped for upstream availability.")
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
