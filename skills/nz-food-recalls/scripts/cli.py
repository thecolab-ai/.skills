#!/usr/bin/env python3
"""Query official MPI food-recall notices."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import nzfetch  # noqa: E402
from mpi_food_recalls import parse_detail, parse_list  # noqa: E402
from result_contract import result_envelope, utc_now  # noqa: E402

BASE = "https://www.mpi.govt.nz/food-safety-home/food-recalls-and-complaints/recalled-food-products"
HOSTS = {"www.mpi.govt.nz"}
WARNINGS = ["Do not infer coverage outside the listed batch/date scope.", "Preserve exact allergen names and official consumer actions."]
DETAIL_TIMEOUT_SECONDS = 2
DETAIL_WORKERS = 8
DETAIL_SCAN_CAP = 24
LIST_TIMEOUT_SECONDS = 8
DETAIL_THREAD_STACK_BYTES = 1024 * 1024


def _detail(row: dict[str, object], retrieved_at: str) -> dict[str, object]:
    url = str(row["source_url"])
    return {
        **row,
        **parse_detail(
            nzfetch.fetch_text(url, timeout=DETAIL_TIMEOUT_SECONDS, allowed_hosts=HOSTS),
            url,
            retrieved_at,
        ),
    }


def _details(
    rows: list[dict[str, object]],
    retrieved_at: str,
) -> tuple[list[dict[str, object]], int]:
    """Fetch notice details concurrently while preserving list order.

    MPI's list is useful even when one detail page is temporarily unavailable.
    Partial failures therefore retain the list row and are surfaced as a warning;
    an across-the-board failure remains an explicit upstream error.
    """
    if not rows:
        return [], 0
    worker_options = list(
        dict.fromkeys(
            (
                min(DETAIL_WORKERS, len(rows)),
                min(4, len(rows)),
            )
        )
    )
    previous_stack_size = threading.stack_size()
    results: list[dict[str, object] | None] = []
    failures: list[BaseException] = []
    try:
        threading.stack_size(DETAIL_THREAD_STACK_BYTES)
        for workers in worker_options:
            results = [None] * len(rows)
            failures = []
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                    pending = {
                        pool.submit(_detail, row, retrieved_at): index
                        for index, row in enumerate(rows)
                    }
                    for future in concurrent.futures.as_completed(pending):
                        index = pending[future]
                        try:
                            results[index] = future.result()
                        except (nzfetch.FetchError, ValueError) as exc:
                            failures.append(exc)
                            results[index] = {
                                **rows[index],
                                "detail_available": False,
                            }
                break
            except RuntimeError as exc:
                if "can't start new thread" not in str(exc) or workers == worker_options[-1]:
                    raise
    finally:
        threading.stack_size(previous_stack_size)
    if failures and len(failures) == len(rows):
        first = failures[0]
        if isinstance(first, nzfetch.FetchError):
            raise first
        raise ValueError(f"all {len(rows)} MPI recall detail pages failed schema parsing") from first
    return [row for row in results if row is not None], len(failures)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("active", "latest"):
        child = commands.add_parser(command); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    for command, argument in (("search", "query"), ("allergen", "name"), ("brand", "name"), ("recall", "id")):
        child = commands.add_parser(command); child.add_argument(argument); child.add_argument("--limit", type=int, default=20); child.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    # MPI pages are large enough to need a realistic read timeout, but repeating
    # that timeout across the shared proxy's default three retries recreates the
    # old minute-long stall. One bounded proxy retry keeps the complete command
    # below the MCP runtime while still trying a second route after direct access.
    os.environ["PROXY_RETRIES"] = "1"
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
                raise LookupError("invalid MPI recall identifier")
            url = BASE + "/" + urllib.parse.quote(ident)
            data = [
                parse_detail(
                    nzfetch.fetch_text(
                        url,
                        timeout=DETAIL_TIMEOUT_SECONDS,
                        allowed_hosts=HOSTS,
                    ),
                    url,
                    retrieved_at,
                )
            ]
        else:
            rows = parse_list(
                nzfetch.fetch_text(
                    BASE,
                    timeout=LIST_TIMEOUT_SECONDS,
                    allowed_hosts=HOSTS,
                ),
                BASE,
                retrieved_at,
            )
            term = getattr(args, "query", None) or getattr(args, "name", None)
            if args.command == "active" and rows and all(row.get("active") is None for row in rows):
                raise RuntimeError("MPI does not publish an active/closed status on these notices; use latest or search")
            if term:
                needle = term.casefold()
                candidates = [
                    row
                    for row in rows
                    if needle in json.dumps(row, ensure_ascii=False).casefold()
                ]
                requested_scan = min(
                    DETAIL_SCAN_CAP,
                    args.limit + 2,
                    len(candidates),
                )
                scan_rows = candidates[:requested_scan]
                if not scan_rows:
                    # Preserve a small detail-only fallback for terms that do not
                    # appear in the list title, without serially crawling MPI.
                    scan_rows = rows[: min(4, len(rows))]
                query["coverage"] = {
                    "listed": len(rows),
                    "list_candidates": len(candidates),
                    "detail_scanned": len(scan_rows),
                    "complete": len(scan_rows) == len(rows),
                }
                if len(scan_rows) < len(rows):
                    warnings.append(
                        f"Filtered detail scan inspected {len(scan_rows)} prioritised notices "
                        f"from {len(rows)} listed notices; an empty result is not exhaustive."
                    )
            else:
                requested_scan = args.limit
                scan_rows = rows[: min(requested_scan, DETAIL_SCAN_CAP)]
            scan_limit = len(scan_rows)
            detailed, detail_failures = _details(scan_rows, retrieved_at)
            if detail_failures:
                warnings.append(
                    f"{detail_failures} of {scan_limit} MPI detail pages were temporarily unavailable; "
                    "their list entries are retained with detail_available=false."
                )
            if args.command == "latest" and requested_scan > scan_limit:
                list_only = [
                    {**row, "detail_available": False}
                    for row in rows[scan_limit : min(len(rows), requested_scan)]
                ]
                detailed.extend(list_only)
                warnings.append(
                    f"Detailed the newest {scan_limit} notices; {len(list_only)} additional "
                    "list entries are returned with detail_available=false."
                )
            if term:
                key = "allergen_or_hazard" if args.command == "allergen" else None
                detailed = [row for row in detailed if term.casefold() in str(row.get(key) if key else json.dumps(row, ensure_ascii=False)).casefold()]
            data = detailed[: args.limit]
        envelope = result_envelope(ok=True, source_name="MPI recalled food products", source_url=BASE, retrieved_at=retrieved_at, freshness="source-managed", query=query, data=data, warnings=warnings, blocked=False)
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
