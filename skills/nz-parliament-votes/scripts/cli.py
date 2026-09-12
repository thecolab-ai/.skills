#!/usr/bin/env python3
"""Query official NZ Parliament weekly Journals and recorded party divisions."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import nzfetch  # noqa: E402
from parliament_votes import UUID, parse_journal, parse_search  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

SOURCE_NAME = "New Zealand Parliament Journals"
SOURCE_URL = "https://journals.parliament.nz/"
SEARCH_URL = "https://journals.parliament.nz/api/data/search"
ALLOWED_HOSTS = {"journals.parliament.nz"}
WARNINGS = [
    "Weekly Journals are draft records; use authoritative Sessional Journals for formal historical citation.",
    "Vote participants include printed party counts; ambiguous singleton labels are preserved as unknown.",
    "The connector never infers an MP's vote from party membership or resolves printed labels to identities.",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="list and filter weekly Journal records")
    search.add_argument("query", nargs="?", default="", help="optional title text filter")
    search.add_argument("--page", type=int, default=1, help="API page number (default: 1)")
    search.add_argument("--limit", type=int, default=20, help="records per page, 1-50")
    search.add_argument("--json", action="store_true", help="emit the result envelope as JSON")
    votes = commands.add_parser("votes", help="extract recorded divisions from one weekly Journal")
    votes.add_argument("journal_id", help="Journal UUID from search")
    votes.add_argument("--json", action="store_true", help="emit the result envelope as JSON")
    return parser


def fetch_api(url: str, *, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    return nzfetch.fetch_json(
        url,
        timeout=10,
        allowed_hosts=ALLOWED_HOSTS,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data is not None else None,
        max_bytes=4 * 1024 * 1024,
    )


def execute(args: argparse.Namespace, fetcher: Callable[..., Any] = fetch_api) -> dict[str, Any]:
    retrieved_at = utc_now()
    if args.command == "search":
        if not 1 <= args.page <= 10000:
            raise ValueError("--page must be between 1 and 10000")
        if not 1 <= args.limit <= 50:
            raise ValueError("--limit must be between 1 and 50")
        parsed = parse_search(fetcher(SEARCH_URL, body={"page": args.page, "pageSize": args.limit}))
        needle = args.query.casefold().strip()
        if needle:
            parsed["results"] = [row for row in parsed["results"] if needle in row["title"].casefold()]
        source_url = SEARCH_URL
        data = parsed
    else:
        if not UUID.fullmatch(args.journal_id):
            raise ValueError("journal_id must be a UUID returned by search")
        source_url = f"https://journals.parliament.nz/api/data/Journal/{args.journal_id.lower()}"
        data = parse_journal(fetcher(source_url), source_url)
    return result_envelope(
        ok=True, source_name=SOURCE_NAME, source_url=source_url,
        retrieved_at=retrieved_at, freshness="live official weekly Journal API",
        query=vars(args), data=data, warnings=WARNINGS, blocked=False,
    )


def render_human(payload: dict[str, Any], command: str) -> None:
    if command == "search":
        rows = payload["data"]["results"]
        for row in rows:
            print(f"{row['publication_date'] or 'date unknown'} | {row['title']}")
            print(f"  {row['id']}")
        if not rows:
            print("No matching weekly Journals on this page.")
        return
    votes = payload["data"]["votes"]
    for vote in votes:
        totals = vote["totals"]
        print(f"{vote['event_date'] or 'date unresolved'} | Ayes {totals['ayes']} | Noes {totals['noes']} | Abstentions {totals['abstentions']}")
        print(f"  {vote['question_text']}")
    if not votes:
        print("No supported recorded party divisions found in this Journal.")


def failure(args: argparse.Namespace, code: int, error: str, message: str, *, blocked: bool = False) -> int:
    payload = result_envelope(
        ok=False, source_name=SOURCE_NAME, source_url=SOURCE_URL,
        query=vars(args), data=None, warnings=WARNINGS, blocked=blocked,
        error={"code": code, "type": error, "message": message},
    )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{error}: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None, fetcher: Callable[..., Any] = fetch_api) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = execute(args, fetcher)
    except ValueError as exc:
        text = str(exc)
        code = 2 if text.startswith(("--", "journal_id")) else 6
        return failure(args, code, "invalid_input" if code == 2 else "source_schema_failure", text)
    except nzfetch.RateLimited as exc:
        return failure(args, 4, "rate_limited", str(exc), blocked=True)
    except nzfetch.Blocked as exc:
        return failure(args, 4, "blocked", str(exc), blocked=True)
    except nzfetch.FetchError as exc:
        invalid_body = isinstance(
            exc, (nzfetch.InvalidCompressedBody, nzfetch.ResponseTooLarge)
        ) or str(exc).startswith("invalid JSON from ")
        if invalid_body:
            return failure(args, 6, "source_schema_failure", str(exc))
        return failure(args, 5, "source_unavailable", str(exc))
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        render_human(payload, args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
