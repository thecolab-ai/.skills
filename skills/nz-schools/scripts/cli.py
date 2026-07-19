#!/usr/bin/env python3
"""Query the official nightly Ministry of Education Schools Directory API."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import nzfetch  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402
from schools_directory import DATA_URL, RESOURCE_URL, nearest, normalize, opened_since  # noqa: E402

HOSTS = {"catalogue.data.govt.nz"}
WARNINGS = [
    "Directory fields, including the Equity Index, are not school rankings or quality claims.",
    "Indicative rolls are ENROL estimates rather than formal roll-return counts.",
    "Enrolment schemes and school details can change; confirm with the school or Ministry.",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, positional in (("search", "query"), ("school", "id"), ("region", "name")):
        child = commands.add_parser(command)
        child.add_argument(positional)
        child.add_argument("--limit", type=int, default=20)
        child.add_argument("--json", action="store_true")
    near = commands.add_parser("near")
    near.add_argument("--lat", type=float, required=True)
    near.add_argument("--lon", type=float, required=True)
    near.add_argument("--limit", type=int, default=20)
    near.add_argument("--json", action="store_true")
    zone = commands.add_parser("zone")
    zone.add_argument("--address", required=True)
    zone.add_argument("--limit", type=int, default=20)
    zone.add_argument("--json", action="store_true")
    changes = commands.add_parser("changes")
    changes.add_argument("--since", required=True)
    changes.add_argument("--limit", type=int, default=20)
    changes.add_argument("--json", action="store_true")
    return parser


def parse_input_date(value: str, option: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise LookupError(f"{option} must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise LookupError(f"{option} must be a valid YYYY-MM-DD date")
    return parsed


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 100:
        print(json.dumps({"error": "invalid_input", "message": "--limit must be between 1 and 100"}), file=sys.stderr)
        return 2
    if args.command == "zone":
        print(
            json.dumps(
                {
                    "error": "unsupported_operation",
                    "message": "Address-to-zone matching requires an authoritative geocoder and current enrolment-zone geometry; this connector does not guess either.",
                }
            ),
            file=sys.stderr,
        )
        return 7
    try:
        if args.command == "near" and (
            not math.isfinite(args.lat)
            or not math.isfinite(args.lon)
            or not -90 <= args.lat <= 90
            or not -180 <= args.lon <= 180
        ):
            raise LookupError("latitude must be between -90 and 90 and longitude between -180 and 180")
        since = parse_input_date(args.since, "--since") if args.command == "changes" else None
    except LookupError as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}), file=sys.stderr)
        return 2
    retrieved_at = utc_now()
    try:
        metadata = nzfetch.fetch_json(RESOURCE_URL, timeout=25, allowed_hosts=HOSTS)["result"]
        payload = nzfetch.fetch_json(DATA_URL, timeout=30, allowed_hosts=HOSTS)["result"]
        source_url = metadata.get("url") or DATA_URL
        records = [
            normalize(row, source_url=source_url, retrieved_at=retrieved_at, last_modified=metadata.get("last_modified"))
            for row in payload["records"]
        ]
        if args.command == "search":
            needle = args.query.casefold()
            fields = ("school_id", "name", "school_type", "authority", "address_text", "town_city", "territorial_authority", "regional_council", "education_region", "year_levels")
            data = [row for row in records if any(needle in str(row.get(field) or "").casefold() for field in fields)][: args.limit]
        elif args.command == "school":
            data = [row for row in records if row["school_id"] == str(args.id)][: args.limit]
        elif args.command == "region":
            needle = args.name.casefold()
            data = [
                row
                for row in records
                if any(needle in str(row.get(field) or "").casefold() for field in ("regional_council", "education_region", "territorial_authority"))
            ][: args.limit]
        elif args.command == "near":
            data = nearest(records, args.lat, args.lon, args.limit)
        else:
            data = opened_since(records, since, args.limit)
        warnings = list(WARNINGS)
        if args.command == "changes":
            warnings.append("Changes covers opening dates present in the current directory; it does not claim to enumerate closures, mergers or renames.")
        envelope = result_envelope(
            ok=True,
            source_name="Ministry of Education Schools Directory",
            source_url=source_url,
            retrieved_at=retrieved_at,
            freshness=f"nightly; resource last modified {metadata.get('last_modified')}",
            query=vars(args),
            data=data,
            warnings=warnings,
            blocked=False,
        )
        print(json.dumps(envelope if args.json else data, indent=2, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
        return 6
    except nzfetch.RateLimited as exc:
        print(json.dumps({"error": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}), file=sys.stderr)
        return 4
    except nzfetch.Blocked as exc:
        print(json.dumps({"error": "blocked", "message": str(exc)}), file=sys.stderr)
        return 4
    except nzfetch.FetchError as exc:
        print(json.dumps({"error": "source_unavailable", "message": str(exc)}), file=sys.stderr)
        return 5
    except (KeyError, TypeError) as exc:
        print(json.dumps({"error": "source_schema_failure", "message": str(exc)}), file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
