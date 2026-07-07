#!/usr/bin/env python3
"""Check Wellington City Council rubbish and recycling collection schedules."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

COLLECTION_URL = "https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling/components/collection-search-results"
MAIN_PAGE = "https://wellington.govt.nz/rubbish-recycling-and-waste/when-to-put-out-your-rubbish-and-recycling"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


def fetch_text(
    url: str, headers: dict[str, str] | None = None,
    data: bytes | None = None, timeout: int = 30
) -> str:
    return nzfetch.fetch_text(
        url,
        timeout=timeout,
        headers=headers or None,
        data=data,
        method="POST" if data is not None else None,
    )


def get_collection(street_id: str, street_name: str) -> dict[str, Any]:
    """Fetch and parse Wellington collection schedule for a street."""
    form_data = urllib.parse.urlencode({
        "streetId": street_id,
        "streetName": street_name,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml",
        "Origin": "https://wellington.govt.nz",
        "Referer": MAIN_PAGE,
    }

    html = fetch_text(COLLECTION_URL, headers=headers, data=form_data)

    # Extract street name from the response heading
    title_m = re.search(r"<h3[^>]*>\s*([^<]+)\s*</h3>", html)
    resolved_name = title_m.group(1).strip() if title_m else street_name

    # Extract collection date: "Friday, 29 May"
    date_m = re.search(
        r'class="collection-date[^"]*">\s*([A-Za-z]+),?\s*(\d+\s+[A-Za-z]+)',
        html,
    )
    collection_day = date_m.group(1) if date_m else None
    collection_date = f"{date_m.group(1)}, {date_m.group(2)}" if date_m else None

    # Extract "out before" time
    time_m = re.search(r"out before\s*<span[^>]*>([^<]+)</span>", html)
    put_out_time = f"before {time_m.group(1)}" if time_m else None

    # Check which items are collected
    has_rubbish = "recycling-icon-rubbish" in html
    has_glass = "recycling-icon-glass" in html  # Glass crate = recycling in Wellington

    if not collection_date:
        raise RuntimeError(
            "Could not parse collection date from WCC response — "
            "the page structure may have changed"
        )

    next_dates: dict[str, str] = {}
    if has_rubbish:
        next_dates["rubbish"] = collection_date
    if has_glass:
        next_dates["recycling"] = collection_date

    return {
        "street_id": street_id,
        "street_name": resolved_name,
        "next_dates": next_dates,
        "collection_day": collection_day,
        "put_out_time": put_out_time,
        "url": f"{MAIN_PAGE}?streetId={street_id}",
        "source": "Wellington City Council collection-day page",
    }


def print_human(result: dict[str, Any]) -> None:
    print(result["street_name"])
    print(f"Source: {result['url']}")
    if result.get("put_out_time"):
        print(f"  Put out: {result['put_out_time']}")
    print("  Next collection:")
    dates = result.get("next_dates", {})
    date_str = dates.get("rubbish") or dates.get("recycling") or "—"
    print(f"    {date_str}")
    print("  Items:")
    for svc in ["rubbish", "recycling"]:
        if svc in result.get("next_dates", {}):
            label = "Rubbish" if svc == "rubbish" else "Recycling (glass crate)"
            print(f"    {label}: collected")
    print("  Note: Wellington combines rubbish and recycling on the same collection day.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check Wellington City Council rubbish and recycling collection schedules."
    )
    ap.add_argument(
        "street_name", nargs="*",
        help="Wellington street name (for display/lookup reference)",
    )
    ap.add_argument(
        "--street-id", required=True,
        help="Wellington City Council street ID (find yours by searching on the WCC collection-day page)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    street_name = " ".join(args.street_name).strip() or f"Street {args.street_id}"

    try:
        result = get_collection(args.street_id, street_name)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_human(result)
        return 0
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        else:
            print(f"wellington-bin-schedule: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
