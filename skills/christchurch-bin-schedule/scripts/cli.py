#!/usr/bin/env python3
"""Check Christchurch City Council kerbside collection schedules."""
from __future__ import annotations

import argparse
import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from typing import Any

ADDRESS_SUGGEST_URL = "https://opendata.ccc.govt.nz/CCCSearch/rest/address/suggest"
COLLECTION_URL = "https://ccc.govt.nz/services/rubbish-and-recycling/collections/getProperty"
MAIN_PAGE = "https://ccc.govt.nz/services/rubbish-and-recycling/collections/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

BIN_LABELS = {
    "Garbage": "Rubbish (red bin)",
    "Recycle": "Recycling (yellow bin)",
    "Organic": "Organics (green bin)",
}


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    """Fetch JSON from a URL using the Python standard library."""
    ctx = ssl.create_default_context()
    try:
        return nzfetch.fetch_json(
            url,
            headers={"User-Agent": UA, **(headers or {})},
            timeout=timeout,
            context=ctx,
        )
    except nzfetch.Blocked as e:
        raise RuntimeError(
            "network error contacting CCC: endpoint blocked by bot protection "
            "(HTTP 403/challenge). This endpoint works from residential NZ IPs but "
            f"may block datacenter/VPN IPs. Try from a home connection. ({e})"
        ) from e
    except nzfetch.FetchError as e:
        raise RuntimeError(f"CCC endpoint error: {e}") from e


def find_rating_unit_id(address: str) -> dict[str, Any] | None:
    """Search for a Christchurch address and return its RatingUnitID + details."""
    qs = urllib.parse.urlencode({"q": address})
    url = f"{ADDRESS_SUGGEST_URL}?{qs}"
    results = fetch_json(url)

    if not results:
        return None

    first = results[0]
    return {
        "rating_unit_id": first["RatingUnitID"],
        "address": first["FullStreetAddress"],
        "street_address_id": first.get("StreetAddressID"),
    }


def get_collection(rating_unit_id: int) -> dict[str, Any]:
    """Fetch and parse CCC collection schedule for a property."""
    url = f"{COLLECTION_URL}?ID={rating_unit_id}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": MAIN_PAGE,
        "Origin": "https://ccc.govt.nz",
        "Accept-Language": "en-NZ,en;q=0.9",
    }

    data = fetch_json(url, headers=headers)

    bins = data.get("bins", {})

    # Routes tell us the regular schedule
    routes = bins.get("routes", [])

    # Collections are the actual planned dates
    collections = bins.get("collections", [])

    # Filter to current/future collections only
    today = date.today().isoformat()
    upcoming = [
        c for c in collections
        if c.get("out_of_date") == "False" and c.get("next_planned_date", "") >= today
    ]
    upcoming.sort(key=lambda c: c["next_planned_date"])

    return {
        "rating_unit_id": str(rating_unit_id),
        "address": data.get("address", ""),
        "routes": {r["material"]: r["day_of_week"] for r in routes},
        "collections": [
            {
                "material": c["material"],
                "date": c["next_planned_date"],
                "label": BIN_LABELS.get(c["material"], c["material"]),
            }
            for c in upcoming
        ],
        "source": "Christchurch City Council collection-day page",
        "url": f"{MAIN_PAGE}?address={urllib.parse.quote(data.get('address', ''))}",
    }


def print_human(result: dict[str, Any]) -> None:
    print(result["address"])
    print(f"Source: {result['url']}")

    if result.get("routes"):
        print("\nRegular schedule:")
        for material in ["Garbage", "Recycle", "Organic"]:
            if material in result["routes"]:
                label = BIN_LABELS.get(material, material)
                print(f"  {label}: {result['routes'][material]}")

    if result.get("collections"):
        print("\nUpcoming collections:")
        for c in result["collections"]:
            try:
                dt = datetime.strptime(c["date"], "%Y-%m-%d")
                friendly = dt.strftime("%A, %d %B %Y")
            except ValueError:
                friendly = c["date"]
            print(f"  {friendly} — {c['label']}")
    else:
        print("\nNo upcoming collections found.")

    print("\nNote: Christchurch uses a three-bin system — red (rubbish), yellow (recycling), green (organics).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check Christchurch City Council kerbside collection schedules."
    )
    ap.add_argument(
        "address", nargs="*",
        help="Christchurch street address, e.g. '53 Hereford Street'",
    )
    ap.add_argument(
        "--rating-unit-id", type=int,
        help="CCC RatingUnitID (found by searching on the CCC collection-day page)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    try:
        if args.rating_unit_id:
            result = get_collection(args.rating_unit_id)
        elif args.address:
            address = " ".join(args.address).strip()
            match = find_rating_unit_id(address)
            if not match:
                msg = f"No address match for '{address}'"
                if args.json:
                    print(json.dumps({"error": msg}, indent=2), file=sys.stderr)
                else:
                    print(f"christchurch-bin-schedule: {msg}", file=sys.stderr)
                return 1
            result = get_collection(match["rating_unit_id"])
            result["address"] = match["address"]
        else:
            ap.print_help()
            return 1

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_human(result)
        return 0

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        else:
            print(f"christchurch-bin-schedule: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
