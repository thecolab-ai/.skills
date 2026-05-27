#!/usr/bin/env python3
"""Auckland Council property rates and capital value CLI.

Self-contained stdlib wrapper around the public council rate-assessment API.
No login, API key, or third-party dependencies.
Extracts a public bearer token from the council search page, same as auckland-bin-schedule.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

PROPERTY_API = "https://experience.aucklandcouncil.govt.nz/nextapi/property"
SEARCH_PAGE = "https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/rubbish-recycling-collections/rubbish-recycling-collection-days.html"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"


def die(message: str, code: int = 1) -> None:
    print(f"property-rates-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_int(value: Any) -> int | None:
    """Parse a raw string or number to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def fmt_dollar(value: int | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value/1_000:.0f}K"
    return f"${value}"


def fetch_text(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:300]
        die(f"HTTP {e.code} from {url}: {raw}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def current_public_token() -> str:
    """Extract the public JWT bearer token from the council search page."""
    html = fetch_text(SEARCH_PAGE)
    match: re.Match[str] | None = re.search(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", html)
    if not match:
        die("could not find Auckland Council public API bearer token in the search page")
    return match.group(0)


def api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.aucklandcouncil.govt.nz",
        "Referer": "https://www.aucklandcouncil.govt.nz/",
    }


def fetch_rates(property_id: str) -> Any:
    """Fetch the rate-assessment JSON for a given property ID using the public token."""
    token = current_public_token()
    url = f"{PROPERTY_API}/{property_id}/rate-assessment"
    try:
        raw = fetch_text(url, headers=api_headers(token))
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_rates(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    raw = fetch_rates(args.property_id)

    # Parse the response into clean fields
    cv = parse_int(raw.get("capitalValue"))
    lv = parse_int(raw.get("landValue"))
    iv = parse_int(raw.get("valueOfImprovements"))
    rates = parse_int(raw.get("totalRates"))

    result = {
        "property_id": args.property_id,
        "capital_value": cv,
        "land_value": lv,
        "improvement_value": iv,
        "annual_rates": rates,
        "valuation_number": raw.get("valuationNumber"),
        "rate_account_key": raw.get("rateAccountKey") or args.property_id,
        "land_area_m2": parse_int(raw.get("area")),
        "total_floor_area_m2": parse_int(raw.get("totalFloorArea")),
        "building_site_coverage_m2": parse_int(raw.get("buildingSiteCoverage")),
        "land_use_description": raw.get("landUseDescription"),
        "local_board": raw.get("localBoard"),
        "property_category": raw.get("propertyCategory"),
        "legal_description": raw.get("legalDescription"),
        "rates_url": f"https://www.aucklandcouncil.govt.nz/en/property-rates-valuations/find-property-rates-valuation/{args.property_id}.html",
        "source": "Auckland Council",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }

    if args.json:
        print(json.dumps({"kind": "rates", "property": result}, indent=2, ensure_ascii=False))
    else:
        had_any = bool(cv or lv or iv or rates)
        print(f"Auckland Council — Property {args.property_id}")
        if not had_any:
            print("  ⚠ No valuation data returned — the property ID may be invalid or the API returned empty data.")
            return
        print(f"  Capital Value (CV):       {fmt_dollar(cv)}")
        print(f"  Land Value:               {fmt_dollar(lv)}")
        print(f"  Improvement Value:        {fmt_dollar(iv)}")
        if lv and cv and iv:
            print(f"  Land/Improvement split:   {lv/cv*100:.0f}% / {iv/cv*100:.0f}%")
        print(f"  Annual Rates:             {fmt_dollar(rates)}")
        if result["valuation_number"]:
            print(f"  Valuation Number:         {result['valuation_number']}")
        if result["land_area_m2"]:
            print(f"  Land Area:                {result['land_area_m2']} m²")
        if result["total_floor_area_m2"]:
            print(f"  Total Floor Area:         {result['total_floor_area_m2']} m²")
        if result["building_site_coverage_m2"]:
            print(f"  Building Site Coverage:   {result['building_site_coverage_m2']} m²")
        if result["land_use_description"]:
            print(f"  Land Use:                 {result['land_use_description']}")
        if result["local_board"]:
            print(f"  Local Board:              {result['local_board']}")
        if result["property_category"]:
            print(f"  Property Category:        {result['property_category']}")
        if result["legal_description"]:
            print(f"  Legal Description:        {result['legal_description']}")
        print(f"  Council page:             {result['rates_url']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Query Auckland Council property rates and valuations")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("rates", help="Fetch rates and CV data for a property")
    s.add_argument("property_id", help="Auckland Council property ID (ACRateAccountKey)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_rates)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
