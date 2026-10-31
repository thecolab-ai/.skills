#!/usr/bin/env python3
"""Read a user's Genesis electricity usage and associated usage costs."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from genesis import Client, GenesisError, DATA
from provenance import error_envelope, provenance, result_envelope
from usage import NZ, coverage, date_range, fetch_usage, records


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can echo arbitrary user input, including a secret
        # accidentally passed on the command line. Keep public errors static.
        raise GenesisError(2, "Invalid arguments; use --help for supported commands and options")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("usage", "summary"):
        child = sub.add_parser(command, help="read electricity intervals" if command == "usage" else "summarise supplied intervals")
        child.add_argument("--start", required=True, help="first inclusive NZ date YYYY-MM-DD")
        child.add_argument("--end", required=True, help="last inclusive NZ date; maximum range 31 days")
        child.add_argument("--json", action="store_true", help="emit a provenance JSON envelope")
        if command == "summary":
            child.add_argument("--group", choices=("day", "range"), default="day")
    meta = provenance(DATA, "Genesis Energy")
    try:
        args = parser.parse_args(argv)
        now = datetime.now(timezone.utc)
        start, end = date_range(args.start, args.end, now.astimezone(NZ).date())
        # Read credentials only after validating the requested operation. Never
        # read existing app config, browser profiles, keyrings, .env files or CLI secrets.
        email = os.environ.get("GENESIS_EMAIL")
        password = os.environ.get("GENESIS_PASSWORD")
        if not email or not password:
            raise GenesisError(3, "Set GENESIS_EMAIL and GENESIS_PASSWORD privately in the environment")
        client = Client()
        client.authenticate(email, password)
        rows = fetch_usage(client, start, end, now, time.sleep)
        meta = provenance(DATA, "Genesis Energy")
        meta.update(coverage(rows, start, end))
        meta["cost_basis"] = "provider costNZD for supplied intervals; not a tariff quote or complete bill"
        meta["unit_basis"] = "provider kw interpreted as interval kWh; confirm against My Account before relying on totals"
        if rows:
            meta["latest_data"] = meta["latest_interval_start"]
        result = result_envelope(records(rows, start, end, args.command, getattr(args, "group", "day")), meta)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Genesis electricity: {meta['coverage']}; {meta['received_intervals']}/{meta['expected_intervals']} requested hours supplied")
            print("NZD figures are provider-reported usage costs; missing hours are not zero.")
            for record in result["results"]:
                print(json.dumps(record, ensure_ascii=False))
        return 0
    except GenesisError as exc:
        result = error_envelope(exc.code, str(exc), meta, retry_after=exc.retry_after)
        if "--json" in argv:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"genesis-energy-nz: {exc}", file=sys.stderr)
        return exc.code
    except Exception:
        # Never dump transport exception strings, request objects or tracebacks
        # into a shared agent/runner log. No partial results on an aborted range.
        result = error_envelope(6, "Genesis operation failed; no partial data returned", meta)
        if "--json" in argv:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("genesis-energy-nz: Genesis operation failed; no partial data returned", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
