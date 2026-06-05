#!/usr/bin/env python3
"""Check Christchurch City Council kerbside collection schedules."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any

import urllib.parse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

ADDRESS_SUGGEST_URL = "https://opendata.ccc.govt.nz/CCCSearch/rest/address/suggest"
COLLECTION_URL = "https://ccc.govt.nz/services/rubbish-and-recycling/collections/getProperty"
MAIN_PAGE = "https://ccc.govt.nz/services/rubbish-and-recycling/collections/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

BIN_LABELS = {
    "Garbage": "Rubbish (red bin)",
    "Recycle": "Recycling (yellow bin)",
    "Organic": "Organics (green bin)",
}


def _fetch_requests(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    """Fetch JSON using requests (preferred)."""
    resp = requests.get(
        url,
        headers={"User-Agent": UA, **(headers or {})},
        timeout=timeout,
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "CCC collection endpoint returned 403 (blocked by bot protection). "
            "This endpoint works from residential NZ IPs but may block datacenter/VPN IPs. "
            "Try from a home connection."
        )
    resp.raise_for_status()
    return resp.json()


def _fetch_urllib(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    """Fetch JSON using stdlib urllib (fallback)."""
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "CCC collection endpoint returned 403 (blocked by bot protection). "
                "This endpoint works from residential NZ IPs but may block datacenter/VPN IPs. "
                "Try from a home connection."
            ) from e
        raise


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    """Fetch JSON from a URL, using requests if available."""
    if HAS_REQUESTS:
        return _fetch_requests(url, headers, timeout)
    return _fetch_urllib(url, headers, timeout)


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
                print(f"christchurch-bin-schedule: No address match for '{address}'", file=sys.stderr)
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
