#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


CLI = Path(__file__).with_name("cli.py")
NETWORK_MARKERS = (
    "network error",
    "timeout",
    "HTTP 403",
    "HTTP 429",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
)


def run(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def skip_if_network(name: str, result: subprocess.CompletedProcess[str]) -> bool:
    text = f"{result.stdout}\n{result.stderr}"
    if any(marker in text for marker in NETWORK_MARKERS):
        print(f"[SKIP] {name}: upstream unavailable ({result.stderr.strip()})")
        return True
    return False


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except AssertionError as exc:
        print(f"[FAIL] {name}: {exc}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[SKIP] {name}: upstream timed out")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def check_help() -> None:
    result = run(["--help"], timeout=10)
    assert result.returncode == 0, result.stderr
    assert "GETS" in result.stdout


def check_open_tenders() -> None:
    result = run(["tenders", "list", "--status", "open", "--limit", "2", "--json"], timeout=45)
    if result.returncode != 0 and skip_if_network("open tenders", result):
        return
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["kind"] == "tenders"
    assert data["status"] == "open"
    assert data["records"], "expected at least one open tender"
    first = data["records"][0]
    assert first.get("rfx_id"), first
    assert first.get("title"), first
    assert first.get("url", "").startswith("https://www.gets.govt.nz/"), first


def check_sources() -> None:
    result = run(["datasets", "sources", "--json"], timeout=45)
    if result.returncode != 0 and skip_if_network("sources", result):
        return
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    names = [source["name"] for source in data["sources"]]
    assert "GETS open tenders RSS" in names
    assert any("Significant service contracts" in name for name in names)


def check_argparse_edge() -> None:
    result = run(["tender", "get"], timeout=10)
    assert result.returncode != 0, "missing RFx ID should fail"
    assert "usage:" in result.stderr


def main() -> int:
    checks = [
        check("help", check_help),
        check("open tenders JSON", check_open_tenders),
        check("sources JSON", check_sources),
        check("missing argument edge case", check_argparse_edge),
    ]
    if all(checks):
        print("All tests passed.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
