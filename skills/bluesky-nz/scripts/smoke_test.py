#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("bluesky_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    cli = load_cli()
    results: list[bool] = []

    def fixture_posts():
        data = json.loads((FIXTURES / "searchposts-sample.json").read_text(encoding="utf-8"))
        posts = [cli.normalise_post(p) for p in data["posts"]]
        assert posts[0]["author_handle"] == "example.bsky.social"
        assert posts[0]["text"].startswith("Surface flooding")
        assert posts[0]["likes"] == 9 and posts[0]["langs"] == ["en"]
        assert posts[0]["url"] == "https://bsky.app/profile/example.bsky.social/post/3synthetic01"
        assert posts[1]["langs"] == [] and posts[1]["likes"] is None

    def fixture_urls_and_handles():
        assert cli.post_web_url("at://did:plc:x/app.bsky.feed.post/abc", None) == "https://bsky.app/profile/did:plc:x/post/abc"
        assert cli.post_web_url("not-an-at-uri", "h.example") is None
        assert cli.clean_handle("@MetService.bsky.social") == "metservice.bsky.social"
        for bad in ("nodots", "", "@"):
            try:
                cli.clean_handle(bad)
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError(f"handle {bad!r} must be rejected")

    results.append(check("fixture post normalisation", fixture_posts))
    results.append(check("fixture web URLs and handle validation", fixture_urls_and_handles))

    def live(name: str, args: list[str], assertion) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            if "network error" in stderr or "upstream unavailable" in stderr:
                print(f"[SKIP] live {name}: {stderr}")
                return
            raise AssertionError(f"exit {completed.returncode}: {stderr}")
        if not assertion(json.loads(completed.stdout)):
            raise AssertionError(f"live assertion for {name} evaluated false")
        print(f"[PASS] live {name}")

    def run_live() -> bool:
        try:
            live(
                "post search",
                ["search", "wellington", "--limit", "3", "--json"],
                lambda d: bool(d["posts"]) and all(p["author_handle"] and p["created_at"] for p in d["posts"]),
            )
            live(
                "author feed",
                ["feed", "bsky.app", "--limit", "2", "--json"],
                lambda d: bool(d["posts"]),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] live probe: {exc}")
            return False

    results.append(run_live())
    if all(results):
        print("[PASS] live smoke assertions completed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
