#!/usr/bin/env python3
"""Find official ERO institution reports with section provenance."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch
from ero_reports import (
    fetch_reports_index,
    parse_page,
    report_organisation_rows,
    report_sections,
    require_report,
    resolve_institution_url,
)
from result_contract import result_envelope, utc_now

WARN = [
    "Do not turn ERO reports into numeric rankings.",
    "Historical review frameworks and dates remain explicit.",
    "Extracted findings retain HTML section provenance.",
]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    c = p.add_subparsers(dest="command", required=True)
    for name, pos in (("search", "school"), ("latest", "school_id"), ("report", "id"), ("actions", "id"), ("history", "school_id")):
        sub = c.add_parser(name)
        sub.add_argument(pos)
        sub.add_argument("--limit", type=int, default=50)
        sub.add_argument("--json", action="store_true")
    return p


def main():
    args = parser().parse_args()
    stamp = utc_now()
    try:
        if not 1 <= args.limit <= 100:
            raise ValueError("--limit must be between 1 and 100")

        value = getattr(args, "school", None) or getattr(args, "school_id", None) or args.id
        ident = re.search(r"(?:/institution/)?(\d+)", value)
        ident = ident.group(1) if ident else None

        if args.command == "search":
            search_term = ident or value
            payload = fetch_reports_index(search_term, page_size=max(100, args.limit))
            data = report_organisation_rows(payload, stamp, value)[: args.limit]
            url = f"https://www.ero.govt.nz/api/ReportsApi/GetReports?searchTerm={quote_plus(search_term)}"
        else:
            if not ident:
                raise ValueError("report/latest/history/actions requires a numeric ERO institution ID or URL")
            url = resolve_institution_url(ident)
            page = parse_page(nzfetch.fetch_text(url, timeout=30, allowed_hosts={"ero.govt.nz", "www.ero.govt.nz"}), url, stamp)
            reports = report_sections(page)
            if args.command == "latest":
                data = reports[:1]
            elif args.command == "history":
                data = reports[: args.limit]
            elif args.command == "report":
                data = require_report(reports, args.id)
            else:
                keys = ("next step", "action", "improvement", "where to next", "priority", "expected outcome")
                sections = require_report(reports, args.id)["sections"]
                data = [section for section in sections if any(key in section["heading"].casefold() for key in keys)][: args.limit]

        env = result_envelope(ok=True, source_name="Education Review Office", source_url=url, retrieved_at=stamp, freshness="publication-specific", query=vars(args), data=data, warnings=WARN, blocked=False)
        if args.json:
            print(json.dumps(env, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input_or_source_schema", "message": str(exc)}), file=sys.stderr)
        return 2 if str(exc).startswith(("--", "report/latest", "requested report ID")) else 6
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
