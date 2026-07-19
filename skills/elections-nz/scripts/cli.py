#!/usr/bin/env python3
"""Query official New Zealand election results and finance publications."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from election_results import (  # noqa: E402
    candidate_matches,
    parse_document_links,
    parse_overall_results,
    parse_turnout,
    parse_winning_candidates,
)
from result_contract import result_envelope, utc_now  # noqa: E402

ALLOWED = {"elections.nz", "www.elections.nz", "electionresults.govt.nz", "www.electionresults.govt.nz"}
WARNINGS = ["Only Electoral Commission results are authoritative.", "Finance records retain their reporting-period and disclosure-threshold context.", "Do not derive voter-level profiles or political persuasion."]


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("results", "party-vote", "turnout"):
        child = commands.add_parser(name); child.add_argument("--year", type=int, required=True); child.add_argument("--limit", type=int, default=100); child.add_argument("--json", action="store_true")
    for name, pos in (("electorate", "name"), ("candidate", "name")):
        child = commands.add_parser(name); child.add_argument(pos); child.add_argument("--year", type=int, required=True); child.add_argument("--limit", type=int, default=100); child.add_argument("--json", action="store_true")
    donations = commands.add_parser("donations"); donations.add_argument("--party", required=True); donations.add_argument("--limit", type=int, default=100); donations.add_argument("--json", action="store_true")
    expenses = commands.add_parser("expenses"); expenses.add_argument("--candidate", required=True); expenses.add_argument("--limit", type=int, default=100); expenses.add_argument("--json", action="store_true")
    return root


def main() -> int:
    args = build_parser().parse_args(); retrieved_at = utc_now()
    try:
        if not 1 <= args.limit <= 100: raise ValueError("--limit must be between 1 and 100")
        if hasattr(args, "year"):
            if args.year not in {2005, 2008, 2011, 2014, 2017, 2020, 2023}: raise ValueError("unsupported general-election year")
            base = f"https://electionresults.govt.nz/electionresults_{args.year}/statistics/csv"
            filename = "overall-results-summary.csv" if args.command in {"results", "party-vote"} else "party-votes-and-turnout-by-electorate.csv"
            if args.command == "candidate": filename = "winning-electorate-candidates.csv"
            source_url = f"{base}/{filename}"
            text = nzfetch.fetch_text(source_url, timeout=30, allowed_hosts=ALLOWED)
            if args.command in {"results", "party-vote"}:
                rows = parse_overall_results(text, source_url, retrieved_at)
            elif args.command in {"turnout", "electorate"}:
                rows = parse_turnout(text, source_url, retrieved_at)
            else:
                rows = parse_winning_candidates(text, source_url, retrieved_at)
            if args.command == "electorate":
                rows = [row for row in rows if args.name.casefold() in str(row["electorate"]).casefold()]
                winner_url = f"{base}/winning-electorate-candidates.csv"
                winners = parse_winning_candidates(nzfetch.fetch_text(winner_url, timeout=30, allowed_hosts=ALLOWED), winner_url, retrieved_at)
                data = [
                    {"electorate": row["electorate"], "turnout": row, "winning_candidate": next((winner for winner in winners if winner["electorate"] == row["electorate"]), None)}
                    for row in rows
                ][:args.limit]
            elif args.command == "candidate":
                rows = [row for row in rows if candidate_matches(str(row["candidate"]), args.name)]
                data = rows[:args.limit]
            elif args.command == "party-vote":
                data = [{key: row[key] for key in ("party", "category", "party_votes", "party_vote_percentage", "list_seats", "electorate_seats", "total_seats", "source_url", "retrieved_at", "result_status")} for row in rows[:args.limit]]
            else:
                data = rows[:args.limit]
            freshness = f"official final {args.year} general-election publication"
        else:
            if args.command == "expenses":
                source_url = "https://elections.nz/democracy-in-nz/historical-events/2023-general-election/candidate-expenses-donations-and-loans"
                query = args.candidate
            else:
                source_url = "https://elections.nz/democracy-in-nz/political-parties-in-new-zealand/donations-exceeding-20000"
                query = args.party
            html = nzfetch.fetch_text(source_url, timeout=30, allowed_hosts=ALLOWED)
            data = parse_document_links(html, source_url, retrieved_at, query)[:args.limit]
            freshness = "official finance publication; reporting period varies by document"
        envelope = result_envelope(ok=True, source_name="New Zealand Electoral Commission", source_url=source_url, retrieved_at=retrieved_at, freshness=freshness, query=vars(args), data=data, warnings=WARNINGS, blocked=False)
        if args.json: print(json.dumps(envelope, ensure_ascii=False, indent=2))
        else:
            for row in data: print(" | ".join(str(value) for key, value in row.items() if key not in {"retrieved_at", "context"})[:1000])
            if not data: print("No matching records in this official publication.")
        return 0
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error":"rate_limited","retry_after":exc.retry_after,"message":str(exc)}), file=sys.stderr); return 4
    except ValueError as exc:
        print(json.dumps({"error":"invalid_input_or_source_schema","message":str(exc)}), file=sys.stderr); return 2 if str(exc).startswith(("--", "unsupported")) else 6
    except nzfetch.Blocked as exc: print(json.dumps({"error":"blocked","message":str(exc)}), file=sys.stderr); return 4
    except nzfetch.FetchError as exc: print(json.dumps({"error":"source_unavailable","message":str(exc)}), file=sys.stderr); return 5


if __name__ == "__main__": raise SystemExit(main())
