#!/usr/bin/env python3
"""Query Pharmac's official monthly Pharmaceutical Schedule XML."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from pharmac_schedule import diff_records, parse_schedule  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

ARCHIVE = "https://schedule.pharmac.govt.nz/pub/schedule/archive/"
HOSTS = {"schedule.pharmac.govt.nz"}
WARNINGS = ["Funding data are not clinical advice.", "Clinical and eligibility decisions remain with authorised professionals."]


def fetch_version(version: str | None = None):
    if version is None:
        index = nzfetch.fetch_text(ARCHIVE, timeout=20, allowed_hosts=HOSTS)
        versions = sorted(set(re.findall(r"Schedule_(20\d{2}-\d{2})(?:-\d{2})?\.xml", index)))
        if not versions:
            raise ValueError("archive index contained no Schedule XML releases")
        version = versions[-1]
    url = f"{ARCHIVE}Schedule_{version}.xml"
    body, _content_type, final = nzfetch.fetch_bytes(url, timeout=30, allowed_hosts=HOSTS)
    retrieved = utc_now()
    metadata, records = parse_schedule(body, final, retrieved)
    return version, metadata, records


def emit(args, data, metadata, query):
    payload = result_envelope(ok=True, source_name="Pharmac Pharmaceutical Schedule XML", source_url=metadata["source_url"], retrieved_at=metadata["retrieved_at"], freshness="monthly", query=query, data=data, warnings=WARNINGS, blocked=False)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for row in data:
            print(row.get("chemical") or row.get("edition") or row.get("change"))
            print(json.dumps(row, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("search", "medicine", "device", "special-authority"):
        p = subs.add_parser(command)
        p.add_argument("query" if command in {"search", "special-authority"} else "id_or_name")
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--json", action="store_true")
    p = subs.add_parser("changes")
    p.add_argument("--from", dest="from_version", required=True)
    p.add_argument("--to", dest="to_version", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p = subs.add_parser("schedule-version")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 100:
            raise LookupError("--limit must be between 1 and 100")
        if args.command == "changes":
            for value in (args.from_version, args.to_version):
                if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", value):
                    raise LookupError("Schedule versions must use YYYY-MM")
            _, old_meta, old = fetch_version(args.from_version)
            _, new_meta, new = fetch_version(args.to_version)
            changes = diff_records(old_meta, old, new_meta, new, args.from_version, args.to_version)
            emit(args, changes[:args.limit], new_meta, vars(args)); return 0
        version, metadata, records = fetch_version()
        if args.command == "schedule-version":
            emit(args, [{**metadata, "version": version}], metadata, vars(args)); return 0
        term = getattr(args, "query", None) or getattr(args, "id_or_name", "")
        needle = term.lower()
        selected = [r for r in records if needle in json.dumps(r, ensure_ascii=False).lower()]
        if args.command in {"medicine", "device"}: selected = [r for r in selected if r["record_type"] == args.command]
        if args.command == "special-authority":
            selected = [r for r in selected if r["special_authorities"]]
        emit(args, selected[:args.limit], metadata, vars(args)); return 0
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr); return 2
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "retry_after": exc.retry_after}), file=sys.stderr); return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr); return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr); return 5
    except ValueError as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr); return 6


if __name__ == "__main__":
    raise SystemExit(main())
