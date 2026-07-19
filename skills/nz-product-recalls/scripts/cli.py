#!/usr/bin/env python3
"""Query official Product Safety New Zealand recall notices."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from product_recalls import matches_filter, parse_detail, parse_list  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

BASE = "https://www.productsafety.govt.nz/recalls"
HOSTS = {"www.productsafety.govt.nz"}
WARNINGS = ["Do not infer coverage beyond official identifiers/batches.", "Keep remedy language faithful to the notice."]


def _detail(row: dict[str, object], retrieved_at: str) -> dict[str, object]:
    url = str(row["source_url"])
    return {**row, **parse_detail(nzfetch.fetch_text(url, timeout=20, allowed_hosts=HOSTS), url, retrieved_at)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("latest", "active"):
        child = commands.add_parser(command); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    for command, argument in (("search", "query"), ("supplier", "name"), ("category", "name"), ("hazard", "query"), ("recall", "id")):
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
            ident = args.id.strip("/")
            if not ident or "/" in ident:
                raise LookupError("invalid product recall identifier")
            url = BASE + "/" + urllib.parse.quote(ident)
            data = [parse_detail(nzfetch.fetch_text(url, timeout=20, allowed_hosts=HOSTS), url, retrieved_at)]
        else:
            rows = parse_list(nzfetch.fetch_text(BASE, timeout=20, allowed_hosts=HOSTS), BASE, retrieved_at)
            scan_limit = args.limit if args.command == "latest" else min(100, max(20, args.limit * 4))
            scan_limit = min(len(rows), scan_limit)
            if args.command != "latest":
                query["coverage"] = {"listed": len(rows), "detail_scanned": scan_limit, "complete": scan_limit == len(rows)}
                if scan_limit < len(rows):
                    warnings.append(f"Filtered detail scan inspected the newest {scan_limit} of {len(rows)} listed notices; an empty result is not exhaustive.")
            detailed = [_detail(row, retrieved_at) for row in rows[:scan_limit]]
            term = getattr(args, "query", None) or getattr(args, "name", None)
            if args.command == "active":
                if detailed and all(row.get("active") is None for row in detailed):
                    raise RuntimeError("Product Safety notices do not publish a reliable active/closed status; use latest or search")
                detailed = [row for row in detailed if row.get("active") is True]
            elif term:
                detailed = [row for row in detailed if matches_filter(row, args.command, term)]
            data = detailed[: args.limit]
        envelope = result_envelope(ok=True, source_name="Product Safety New Zealand recalls", source_url=BASE, retrieved_at=retrieved_at, freshness="source-managed", query=query, data=data, warnings=warnings, blocked=False)
        print(json.dumps(envelope if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr); return 2
    except RuntimeError as exc:
        print(json.dumps({"error": "unsupported_source_surface", "message": str(exc)}), file=sys.stderr); return 7
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
