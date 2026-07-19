#!/usr/bin/env python3
"""Query New Zealand Parliament's official current-MP directory."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402
from parliament_members import parse_members, parse_profile  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

SOURCE = "https://www3.parliament.nz/en/mps-and-electorates/members-of-parliament/"
HOSTS = {"www3.parliament.nz"}
WARNINGS = ["Only official public-office contact channels are returned.", "Directory roles can change; use the retrieval timestamp."]


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("list"); child.add_argument("--limit", type=int, default=100); child.add_argument("--json", action="store_true")
    for command, positional in (("mp", "name"), ("electorate", "name"), ("party", "name"), ("portfolio", "query"), ("committee", "name")):
        child = commands.add_parser(command); child.add_argument(positional); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 100:
        print(json.dumps({"error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr); return 2
    at = utc_now()
    try:
        rows = parse_members(nzfetch.fetch_text(SOURCE, timeout=25, allowed_hosts=HOSTS), SOURCE, at)
        if args.command == "list": data = rows[:args.limit]
        elif args.command == "party": data = [row for row in rows if args.name.casefold() in row["party"].casefold()][:args.limit]
        elif args.command == "electorate": data = [row for row in rows if args.name.casefold() in row["electorate"].casefold()][:args.limit]
        elif args.command == "mp":
            matches = [row for row in rows if args.name.casefold() in row["name"].casefold()][:args.limit]
            data = []
            for row in matches:
                profile = parse_profile(nzfetch.fetch_text(row["source_url"], timeout=25, allowed_hosts=HOSTS), row["source_url"], at)
                data.append({**row, **profile})
        else:
            needle = args.query.casefold() if args.command == "portfolio" else args.name.casefold()
            wanted_kind = "portfolio" if args.command == "portfolio" else "select committee"
            data = []
            for row in rows:
                profile = parse_profile(nzfetch.fetch_text(row["source_url"], timeout=25, allowed_hosts=HOSTS), row["source_url"], at)
                roles = [
                    role for role in profile["current_roles"]
                    if wanted_kind in str(role["kind"]).casefold() and needle in f"{role['subject']} {role['role']}".casefold()
                ]
                if roles:
                    data.append({**row, "matching_current_roles": roles})
                if len(data) >= args.limit:
                    break
        warnings = list(WARNINGS) + ["This source is the current-MP directory; absence is not evidence that a person was never an MP."]
        envelope = result_envelope(ok=True, source_name="New Zealand Parliament member directory", source_url=SOURCE, retrieved_at=at, freshness="current at retrieval", query=vars(args), data=data, warnings=warnings, blocked=False)
        print(json.dumps(envelope if args.json else data, indent=2, ensure_ascii=False)); return 0
    except nzfetch.RateLimited as exc: print(json.dumps({"error":"rate_limited","message":str(exc),"retry_after":exc.retry_after}),file=sys.stderr); return 4
    except nzfetch.Blocked as exc: print(json.dumps({"error":"blocked","message":str(exc)}),file=sys.stderr); return 4
    except nzfetch.FetchError as exc: print(json.dumps({"error":"source_unavailable","message":str(exc)}),file=sys.stderr); return 5
    except ValueError as exc: print(json.dumps({"error":"source_schema_failure","message":str(exc)}),file=sys.stderr); return 6


if __name__ == "__main__": raise SystemExit(main())
