#!/usr/bin/env python3
"""Fixture contracts plus one bounded live catalogue search and one layer read."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from test_contract import assert_deterministic_contracts  # noqa: E402

CLI = SCRIPT_DIR / "cli.py"
LIVE_LAYER_ID = "117733"


def live_command(args: list[str]) -> tuple[str, dict | None]:
    """Return ok, skip, or fail. Skip means the upstream could not be read."""
    try:
        completed = subprocess.run(
            [sys.executable, str(CLI), *args, "--json"],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[SKIP] live probe timed out")
        return "skip", None
    text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    try:
        payload = json.loads(completed.stdout) if completed.stdout else None
    except json.JSONDecodeError:
        payload = None
    if payload and isinstance(payload.get("error"), dict) and payload["error"].get("type") in {
        "blocked",
        "upstream_unavailable",
    }:
        print(f"[SKIP] live probe network error: {payload['error'].get('message')}")
        return "skip", None
    if completed.returncode in {4, 5}:
        print(f"[SKIP] live probe network error: {text.strip()[:300]}")
        return "skip", None
    if payload is None or completed.returncode != 0 or completed.stderr:
        print(f"[FAIL] live probe exit {completed.returncode}: {text.strip()[:400]}")
        return "fail", payload
    return "ok", payload


def _same_host_data_url(url: object) -> None:
    assert isinstance(url, str) and url
    parsed = urllib.parse.urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.hostname == "data.mfe.govt.nz"
    assert parsed.username is None and parsed.password is None
    assert parsed.path.rstrip("/") == "/services/api/v1/data"
    assert "/query" not in parsed.path


def assert_live_search(payload: dict) -> None:
    if payload.get("results") == []:
        raise AssertionError("live search returned no catalogue rows")
    assert payload["meta"]["source_url"].startswith("https://data.mfe.govt.nz/services/api/v1/data/")
    assert "page_size=1" in payload["meta"]["source_url"]
    assert "/query" not in payload["meta"]["source_url"]
    assert "licence" not in payload["meta"]
    row = payload["results"][0]
    assert type(row["id"]) is int and row["id"] > 0
    assert isinstance(row["title"], str) and row["title"].strip()
    assert isinstance(row["type"], str) and row["type"].strip()
    assert len(payload["results"]) == 1
    assert payload["truncated"] is True
    page = payload.get("page")
    assert isinstance(page, dict)
    _same_host_data_url(page.get("next"))
    _same_host_data_url(page.get("last"))
    assert page["next"] != page["last"]
    assert "page=" in urllib.parse.urlsplit(page["next"]).query


def assert_live_layer(payload: dict) -> None:
    assert payload["meta"]["source_url"] == f"https://data.mfe.govt.nz/services/api/v1/layers/{LIVE_LAYER_ID}/"
    assert payload["meta"]["publisher"] == "Ministry for the Environment"
    row = payload["results"][0]
    assert str(row["id"]) == LIVE_LAYER_ID
    assert "Land Use" in row["title"]
    assert row["license_type"] == "cc-by"
    assert "Attribution" in payload["meta"]["licence"]
    assert type(row["feature_count"]) is int and row["feature_count"] > 0
    assert row["field_names"][0] == "Shape"
    assert all(isinstance(name, str) and name for name in row["field_names"])


def main() -> int:
    try:
        labels = assert_deterministic_contracts()
    except (AssertionError, json.JSONDecodeError, OSError) as exc:
        print(f"[FAIL] fixture {exc}")
        return 1
    for label in labels:
        print(f"[PASS] {label}")

    status, payload = live_command(["search", "flood", "--limit", "1"])
    if status == "fail":
        return 1
    if status == "skip":
        return 0
    try:
        assert_live_search(payload or {})
    except AssertionError as exc:
        print(f"[FAIL] live search {exc}")
        return 1

    status, payload = live_command(["layer", LIVE_LAYER_ID])
    if status == "fail":
        return 1
    if status == "skip":
        return 0
    try:
        assert_live_layer(payload or {})
    except AssertionError as exc:
        print(f"[FAIL] live layer {exc}")
        return 1
    print("[PASS] live search flood page_size 1 reports truncated with one catalogue card")
    print("[PASS] live layer 117733 reports cc-by, field name Shape, and a positive feature count")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
