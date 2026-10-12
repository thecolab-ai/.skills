#!/usr/bin/env python3
"""Fixture contracts and one bounded live notes read."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
BBOX = "174.76,-36.86,174.78,-36.84"
LIVE_LIMIT = "2"
FORBIDDEN_KEYS = {"uid", "user", "user_url", "html", "comment_url", "close_url", "reopen_url", "url"}


def run_cli(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def keys_of(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        for item in value.values():
            found.update(keys_of(item))
    elif isinstance(value, list):
        for item in value:
            found.update(keys_of(item))
    return found


def check(kind: str, name: str, fn) -> bool:
    try:
        fn()
    except Exception as exc:
        print(f"[FAIL] {kind} {name}: {exc}")
        return False
    print(f"[PASS] {kind} {name}")
    return True


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    if completed.stderr:
        raise AssertionError(completed.stderr.strip())
    return json.loads(completed.stdout)


def notes(*extra: str, fixture: str | None = None, limit: str = "2") -> list[str]:
    arguments = ["notes", "--bbox", BBOX, "--limit", limit, *extra]
    if fixture:
        arguments.extend(("--fixture", fixture))
    arguments.append("--json")
    return arguments


def test_positive() -> None:
    payload = load_json(run_cli(notes(fixture="tests/fixtures/notes-positive.json")))
    assert [note["id"] for note in payload["results"]] == [102, 101]
    assert payload["meta"]["licence"] == "Open Database License (ODbL) 1.0"
    assert payload["meta"]["latest_data"] == "2026-02-04 05:06:07 UTC"
    assert payload["results"][0]["note_url"] == "https://www.openstreetmap.org/note/102"
    assert FORBIDDEN_KEYS.isdisjoint(keys_of(payload))
    assert "synthetic-account" not in json.dumps(payload)
    assert "/user/" not in json.dumps(payload)


def test_limit_cap() -> None:
    payload = load_json(run_cli(notes(fixture="tests/fixtures/notes-positive.json", limit="1")))
    assert [note["id"] for note in payload["results"]] == [102]


def test_empty() -> None:
    payload = load_json(run_cli(notes(fixture="tests/fixtures/notes-empty.json")))
    assert payload["results"] == []
    assert "latest_data" not in payload["meta"]
    assert "error" not in payload


def test_malformed() -> None:
    completed = run_cli(notes(fixture="tests/fixtures/notes-malformed.json"))
    payload = load_json(completed)
    assert completed.returncode == 6
    assert payload["results"] == []
    assert payload["error"]["type"] == "schema_failure"


def test_outside() -> None:
    completed = run_cli(notes(fixture="tests/fixtures/notes-outside.json"))
    payload = load_json(completed)
    assert completed.returncode == 6
    assert payload["error"]["type"] == "schema_failure"


def test_rate_limit() -> None:
    completed = run_cli(notes(fixture="tests/fixtures/notes-http-429.json"))
    payload = load_json(completed)
    assert completed.returncode == 4
    assert payload["error"]["type"] == "blocked"
    assert payload["error"]["retry_after"] == "30"
    assert "network error: HTTP 429" in payload["error"]["message"]


def test_unavailable() -> None:
    completed = run_cli(notes(fixture="tests/fixtures/notes-http-503.json"))
    payload = load_json(completed)
    assert completed.returncode == 5
    assert payload["error"]["type"] == "upstream_unavailable"
    assert "network error: HTTP 503" in payload["error"]["message"]


def test_bounds() -> None:
    wide = run_cli(
        [
            "notes",
            "--bbox",
            "174.70,-36.90,174.80,-36.80",
            "--limit",
            "2",
            "--fixture",
            "tests/fixtures/notes-positive.json",
            "--json",
        ]
    )
    assert wide.returncode == 2
    assert json.loads(wide.stdout)["error"]["type"] == "invalid_input"
    over_limit = run_cli(["notes", "--bbox", BBOX, "--limit", "21", "--json"])
    assert over_limit.returncode == 2
    history = run_cli(["notes", "--bbox", BBOX, "--closed-days", "-1", "--json"])
    assert history.returncode == 2
    escaped = run_cli(
        ["notes", "--bbox", BBOX, "--fixture", "/etc/passwd", "--json"]
    )
    assert escaped.returncode == 2


def test_truncation() -> None:
    sys.path.insert(0, str(CLI.parent))
    import cli as notes_cli

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [174.77, -36.85]},
                "properties": {
                    "id": 301,
                    "date_created": "2026-04-01 00:00:00 UTC",
                    "status": "open",
                    "comments": [
                        {
                            "date": "2026-04-01 00:00:01 UTC",
                            "action": "opened",
                            "text": "x" * 2005,
                        }
                    ],
                },
            }
        ],
    }
    notes, _latest = notes_cli.normalise_notes(payload, (174.76, -36.86, 174.78, -36.84), 1)
    assert notes[0]["comments"][0]["text_truncated"] is True
    assert len(notes[0]["comments"][0]["text"]) == 2000


def test_no_mutation_paths() -> None:
    source = CLI.read_text(encoding="utf-8")
    for forbidden in ("/comment.json", "/close.json", "/reopen.json", 'method="POST"', "method='POST'"):
        if forbidden in source:
            raise AssertionError(forbidden)


def test_help() -> None:
    completed = run_cli(["notes", "--help"])
    assert completed.returncode == 0
    assert "--json" in completed.stdout
    assert "--bbox" in completed.stdout
    assert "--closed-days" in completed.stdout


def test_live() -> None:
    completed = run_cli(
        ["notes", "--bbox", BBOX, "--limit", LIVE_LIMIT, "--closed-days", "0", "--json"],
        timeout=25,
    )
    text = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        lowered = text.lower()
        if (
            completed.returncode in {4, 5}
            or "network error" in lowered
            or "timed out" in lowered
            or "http 429" in lowered
            or "http 5" in lowered
        ):
            raise AssertionError(f"network error: exit {completed.returncode}: {text[:400]}")
        raise AssertionError(f"exit {completed.returncode}: {text[:400]}")
    payload = json.loads(completed.stdout)
    notes = payload["results"]
    if not isinstance(notes, list) or not notes:
        raise AssertionError("live notes returned no notes; an empty result is not a pass")
    if len(notes) > int(LIVE_LIMIT):
        raise AssertionError("live notes exceeded the requested limit")
    meta = payload["meta"]
    if "ODbL" not in str(meta.get("licence", "")):
        raise AssertionError("live notes response omitted the ODbL licence")
    if meta.get("publisher") != "OpenStreetMap contributors":
        raise AssertionError("live notes publisher mismatch")
    source_url = str(meta.get("source_url", ""))
    if not source_url.startswith("https://api.openstreetmap.org/api/0.6/notes.json?"):
        raise AssertionError("live source URL is not the notes collection")
    if "limit=2" not in source_url or "closed=0" not in source_url:
        raise AssertionError("live source URL dropped the bounded query")
    if not str(meta.get("retrieved_at", "")).endswith("Z"):
        raise AssertionError("live retrieved_at is not UTC")
    if FORBIDDEN_KEYS.intersection(keys_of(payload)):
        raise AssertionError("live notes leaked an account or mutation field")
    for note in notes:
        if note["status"] not in {"open", "closed", "hidden"}:
            raise AssertionError("live note status was not recognised")
        longitude = note["longitude"]
        latitude = note["latitude"]
        if not (174.76 <= longitude <= 174.78 and -36.86 <= latitude <= -36.84):
            raise AssertionError("live note fell outside the requested box")
        if not note["comments"] or not isinstance(note["comments"][0]["text"], str):
            raise AssertionError("live note omitted comment text")
    if not any(note["status"] == "open" for note in notes):
        raise AssertionError("closed=0 returned no open note")


def main() -> int:
    checks = [
        ("fixture", "positive notes omit account identifiers", test_positive),
        ("fixture", "limit keeps the newest returned note", test_limit_cap),
        ("fixture", "empty collection is a successful empty result", test_empty),
        ("fixture", "malformed feature is a schema failure", test_malformed),
        ("fixture", "point outside the box is a schema failure", test_outside),
        ("fixture", "HTTP 429 preserves Retry-After", test_rate_limit),
        ("fixture", "HTTP 503 is upstream unavailable", test_unavailable),
        ("fixture", "oversized box, limit, history, and fixture path are rejected", test_bounds),
        ("fixture", "long comment text is truncated", test_truncation),
        ("contract", "CLI source has no note mutation request", test_no_mutation_paths),
        ("contract", "notes help lists the read options", test_help),
        ("live", "central Auckland notes bbox returns bounded open notes", test_live),
    ]
    passed = [check(kind, name, fn) for kind, name, fn in checks]
    if not all(passed):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
