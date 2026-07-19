#!/usr/bin/env python3
"""Search Medsafe's official medicine and medical-device recall database."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from medsafe_recalls import parse_detail, parse_results  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

BASE = "https://www.medsafe.govt.nz/hot/Recalls/"
SEARCH = BASE + "RecallSearch.asp"
HOSTS = {"www.medsafe.govt.nz"}
WARNINGS = [
    "Recall retrieval is not medical advice; do not stop a medicine without professional guidance unless the official notice directs it.",
    "Preserve exact batch, lot, model and software-version scope.",
]


def fetch_search(kind: str = "All", term: str = "") -> str:
    data = urllib.parse.urlencode({"optType": kind, "txtName": term, "Ingredients": "", "txtDateFrom": "1 Jul 2012", "txtDateTo": "", "cmdSearch": "Search"}).encode()
    return nzfetch.fetch_text(SEARCH, timeout=30, data=data, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, allowed_hosts=HOSTS)


def _fetch_detail(row: dict[str, object], retrieved_at: str) -> dict[str, object]:
    source_url = str(row["source_url"])
    detail = parse_detail(nzfetch.fetch_text(source_url, timeout=20, allowed_hosts=HOSTS), source_url, retrieved_at)
    return {**row, **detail}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("latest"); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    for command, argument in (("search", "query"), ("medicine", "name"), ("device", "name"), ("recall", "id")):
        child = commands.add_parser(command); child.add_argument(argument); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if not 1 <= args.limit <= 100:
            raise LookupError("--limit must be between 1 and 100")
        retrieved_at = utc_now()
        warnings = list(WARNINGS)
        query = vars(args).copy()
        if args.command == "recall":
            ident = args.id.strip()
            if not ident or not ident.isdigit():
                raise LookupError("Medsafe recall ID must be numeric")
            url = BASE + "RecallDetail.asp?ID=" + urllib.parse.quote(ident)
            data = [parse_detail(nzfetch.fetch_text(url, timeout=20, allowed_hosts=HOSTS), url, retrieved_at)]
        else:
            kind = {"medicine": "Medicine", "device": "Device"}.get(args.command, "All")
            term = getattr(args, "query", None) or getattr(args, "name", "")
            rows = parse_results(fetch_search(kind, term), SEARCH, retrieved_at)
            # The portal only searches a subset of detail fields. Fall back to a
            # bounded first-party detail scan so product codes/batches remain searchable.
            if term and not rows:
                rows = parse_results(fetch_search(kind, ""), SEARCH, retrieved_at)
            if term:
                matches: list[dict[str, object]] = []
                scan_count = min(len(rows), min(100, max(20, args.limit * 4)))
                query["coverage"] = {"listed": len(rows), "detail_scanned": scan_count, "complete": scan_count == len(rows)}
                if scan_count < len(rows):
                    warnings.append(f"Detail-field search inspected the newest {scan_count} of {len(rows)} listed recalls; an empty result is not exhaustive.")
                for row in rows[:scan_count]:
                    detailed = _fetch_detail(row, retrieved_at)
                    if term.casefold() in json.dumps(detailed, ensure_ascii=False).casefold():
                        matches.append(detailed)
                    if len(matches) >= args.limit:
                        break
                data = matches
            else:
                data = rows[: args.limit]
        payload = result_envelope(ok=True, source_name="Medsafe Online Recalls Database", source_url=SEARCH, retrieved_at=retrieved_at, freshness="source-managed", query=query, data=data, warnings=warnings, blocked=False)
        print(json.dumps(payload if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr); return 2
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after, "message": str(exc)}), file=sys.stderr); return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr); return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr); return 5
    except ValueError as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr); return 6


if __name__ == "__main__":
    raise SystemExit(main())
