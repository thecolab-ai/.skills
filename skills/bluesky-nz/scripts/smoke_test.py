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
        assert cli.clean_handle("@MetService.com") == "metservice.com"
        for bad in ("nodots", "", "@"):
            try:
                cli.clean_handle(bad)
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError(f"handle {bad!r} must be rejected")

    def fixture_leading_reposts_do_not_hide_authored_posts():
        page = json.loads((FIXTURES / "author-feed-leading-reposts.json").read_text(encoding="utf-8"))
        # The old client sent --limit straight to the API. A page whose first
        # two rows are reposts then returned no authored posts for --limit 2.
        authored, excluded, scanned = cli.select_authored_feed(page["feed"], 2)
        assert excluded == 2 and scanned == 4
        posts = [cli.normalise_post(item.get("post") or {}) for item in authored]
        assert [p["text"] for p in posts] == ["Pinned status", "Original update"]
        assert all(p["author_handle"] == "agency.example" for p in posts)
        pin_only, pin_excluded, pin_scanned = cli.select_authored_feed(page["feed"], 1)
        assert pin_excluded == 2 and pin_scanned == 3
        assert cli.normalise_post(pin_only[0]["post"])["text"] == "Pinned status"
        params = cli.author_feed_params("bsky.app")
        assert params == {"actor": "bsky.app", "limit": 100, "filter": "posts_no_replies"}
        assert params["limit"] != 2

    def fixture_feed_shape_and_junk_rows():
        try:
            cli.authored_posts_from_page({"feed": {"not": "a list"}}, 2)
        except cli.FeedShapeError:
            pass
        else:
            raise AssertionError("object feed must be rejected")
        try:
            cli.authored_posts_from_page({}, 2)
        except cli.FeedShapeError:
            pass
        else:
            raise AssertionError("missing feed must be rejected")
        empty, excluded, scanned = cli.authored_posts_from_page({"feed": []}, 2)
        assert empty == [] and excluded == 0 and scanned == 0
        reposts_only, reposts_excluded, reposts_scanned = cli.select_authored_feed(
            [
                None,
                "nope",
                {"reason": {"$type": "app.bsky.feed.defs#reasonRepost"}, "post": {"author": {"handle": "x.example"}}},
            ],
            2,
        )
        assert reposts_only == [] and reposts_excluded == 1 and reposts_scanned == 3

    def fixture_verified_help_example():
        completed = subprocess.run(
            [sys.executable, str(CLI), "feed", "--help"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0
        assert "metservice.com" in completed.stdout
        assert "metservice.bsky.social" not in completed.stdout

    results.append(check("fixture post normalisation", fixture_posts))
    results.append(check("fixture web URLs and handle validation", fixture_urls_and_handles))
    results.append(check("fixture leading reposts keep authored posts", fixture_leading_reposts_do_not_hide_authored_posts))
    results.append(check("fixture malformed author feed", fixture_feed_shape_and_junk_rows))
    results.append(check("fixture domain-verified help example", fixture_verified_help_example))

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
                lambda d: (
                    d.get("handle") == "bsky.app"
                    and isinstance(d.get("posts"), list)
                    and 1 <= len(d["posts"]) <= 2
                    and d.get("count") == len(d["posts"])
                    and str(d.get("source_url", "")).startswith(
                        "https://api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?"
                    )
                    and "limit=100" in str(d.get("source_url"))
                    and "filter=posts_no_replies" in str(d.get("source_url"))
                    and all(
                        p.get("author_handle") == "bsky.app" and p.get("created_at")
                        for p in d["posts"]
                    )
                ),
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
