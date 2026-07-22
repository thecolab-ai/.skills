#!/usr/bin/env python3
"""Search public Bluesky posts and read public account feeds (no login).

Uses the Bluesky AppView's unauthenticated XRPC endpoints. Tuned for NZ
situational awareness: keyword search with recency sort, author feeds for
official accounts, and machine-readable output. Public posts only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
from datetime import datetime
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE = "https://api.bsky.app/xrpc/"
SOURCE_NAME = "Bluesky public AppView"
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,252}$")
DID_RE = re.compile(r"^did:[a-z0-9]+:[A-Za-z0-9._%:-]+$")


def die(message: str, code: int = 1) -> None:
    print(f"bluesky-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def get(method: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    url = BASE + method + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        data = nzfetch.fetch_json(url, timeout=30)
    except nzfetch.RateLimited as exc:
        die(f"network error: rate_limited: retry_after={exc.retry_after}: {exc}", 4)
    except nzfetch.Blocked as exc:
        die(f"network error: {exc}", 4)
    except nzfetch.FetchError as exc:
        # XRPC signals bad input as HTTP 400 (e.g. unknown actor, empty query);
        # nzfetch surfaces that as FetchError before the JSON body is readable.
        if "HTTP 400" in str(exc) or "HTTP 404" in str(exc):
            die(f"request rejected by Bluesky ({exc}): check the handle or query", 2)
        die(f"upstream unavailable: {exc}", 5)
    return data, url


def post_web_url(uri: str | None, handle: str | None) -> str | None:
    if not uri or not uri.startswith("at://"):
        return None
    parts = uri.split("/")
    if len(parts) < 5 or not parts[-1]:
        return None
    actor = handle or parts[2]
    return f"https://bsky.app/profile/{actor}/post/{parts[-1]}"


def normalise_post(post: dict[str, Any]) -> dict[str, Any]:
    author = post.get("author") or {}
    record = post.get("record") or {}
    handle = author.get("handle")
    return {
        "author_handle": handle,
        "author_name": author.get("displayName"),
        "text": record.get("text"),
        "created_at": record.get("createdAt"),
        "langs": record.get("langs") or [],
        "replies": post.get("replyCount"),
        "reposts": post.get("repostCount"),
        "likes": post.get("likeCount"),
        "url": post_web_url(post.get("uri"), handle),
    }


def clean_handle(raw: str) -> str:
    actor = raw.strip().lstrip("@")
    if actor.startswith("did:"):
        if not DID_RE.match(actor):
            die(f"invalid DID {raw!r}: expected e.g. did:plc:abc123...", 2)
        return actor
    actor = actor.lower()
    if not HANDLE_RE.match(actor) or "." not in actor:
        die(f"invalid handle {raw!r}: expected e.g. some-account.bsky.social or a did:plc: identifier", 2)
    return actor


def emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def render_posts(posts: list[dict[str, Any]]) -> list[str]:
    lines = []
    for p in posts:
        text = " ".join((p.get("text") or "").split())
        if len(text) > 160:
            text = text[:157] + "..."
        lines.append(f"- {p['created_at']} @{p['author_handle']}: {text}")
        if p.get("url"):
            lines.append(f"    {p['url']} (♥{p.get('likes')} ↻{p.get('reposts')})")
    return lines


def cmd_search(args: argparse.Namespace) -> None:
    if not args.query.strip():
        die("search query must not be empty", 2)
    if args.since:
        try:
            datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            die(f"invalid --since {args.since!r}: expected ISO 8601, e.g. 2026-07-21 or 2026-07-21T00:00:00Z", 2)
    data, url = get(
        "app.bsky.feed.searchPosts",
        {"q": args.query, "limit": args.limit, "sort": args.sort, "since": args.since, "lang": args.lang},
    )
    posts = [normalise_post(p) for p in data.get("posts", [])]
    payload = {
        "kind": "search",
        "source": SOURCE_NAME,
        "source_url": url,
        "query": args.query,
        "sort": args.sort,
        "count": len(posts),
        "note": "public posts only; crowd content is unverified — corroborate before acting",
        "posts": posts,
    }
    emit(payload, args.json, [f"Bluesky posts matching {args.query!r} ({args.sort}): {len(posts)}"] + render_posts(posts))


def cmd_feed(args: argparse.Namespace) -> None:
    handle = clean_handle(args.handle)
    data, url = get("app.bsky.feed.getAuthorFeed", {"actor": handle, "limit": args.limit, "filter": "posts_no_replies"})
    # The API still returns the account's REPOSTS of other authors (marked by a
    # `reason`); drop them so every row is genuinely authored by the account.
    items = data.get("feed", [])
    own = [item for item in items if not item.get("reason")]
    posts = [normalise_post(item.get("post") or {}) for item in own]
    payload = {
        "kind": "feed",
        "source": SOURCE_NAME,
        "source_url": url,
        "handle": handle,
        "count": len(posts),
        "reposts_excluded": len(items) - len(own),
        "posts": posts,
    }
    emit(
        payload,
        args.json,
        [f"@{handle}: {len(posts)} recent posts ({payload['reposts_excluded']} reposts of other accounts excluded)"]
        + render_posts(posts),
    )


def cmd_profile(args: argparse.Namespace) -> None:
    handle = clean_handle(args.handle)
    data, url = get("app.bsky.actor.getProfile", {"actor": handle})
    payload = {
        "kind": "profile",
        "source": SOURCE_NAME,
        "source_url": url,
        "handle": data.get("handle"),
        "display_name": data.get("displayName"),
        "description": data.get("description"),
        "followers": data.get("followersCount"),
        "posts": data.get("postsCount"),
        "created_at": data.get("createdAt"),
        "url": f"https://bsky.app/profile/{data.get('handle')}",
    }
    emit(
        payload,
        args.json,
        [
            f"@{payload['handle']} — {payload['display_name']} ({payload['followers']} followers, {payload['posts']} posts)",
            " ".join((payload["description"] or "").split()),
            str(payload["url"]),
        ],
    )


def positive_int(maximum: int):
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{raw!r} is not an integer")
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return value

    return parse


def main() -> None:
    parser = argparse.ArgumentParser(description="Search public Bluesky posts and account feeds (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search public posts by keyword or phrase")
    s.add_argument("query", help='search terms, e.g. "wellington flooding" or "state of emergency"')
    s.add_argument("--sort", choices=("latest", "top"), default="latest", help="recency or engagement (default latest)")
    s.add_argument("--since", help="only posts after this ISO 8601 time")
    s.add_argument("--lang", help="BCP-47 language filter, e.g. en")
    s.add_argument("--limit", type=positive_int(100), default=25, help="maximum posts (default 25)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("feed", help="recent public posts from one account")
    s.add_argument("handle", help="account handle, e.g. metservice.bsky.social")
    s.add_argument("--limit", type=positive_int(100), default=20, help="maximum posts (default 20)")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_feed)

    s = sub.add_parser("profile", help="public profile summary for one account")
    s.add_argument("handle", help="account handle")
    s.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    s.set_defaults(func=cmd_profile)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
