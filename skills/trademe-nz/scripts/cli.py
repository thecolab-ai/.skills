#!/usr/bin/env python3
"""Trade Me NZ lightweight public-search CLI.

Self-contained stdlib wrapper around Trade Me's public read-only web API endpoints.
No login, OAuth app credentials, watchlist, bidding, or listing mutation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_WEB = "https://www.trademe.co.nz"
BASE_API = "https://api.trademe.co.nz/v1"
UA = os.environ.get(
    "TRADEME_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

SEARCH_ENDPOINTS = {
    "marketplace": "/search/general",
    "property-sale": "/search/property/residential",
    "property-rent": "/search/property/rental",
    "motors": "/search/motors/used",
    "motors-new": "/search/motors/new",
    "jobs": "/search/jobs",
    "flatmates": "/search/flatmates",
    "commercial-sale": "/search/property/commercialsale",
    "commercial-lease": "/search/property/commerciallease",
    "rural": "/search/property/rural",
    "retirement": "/search/property/retirement",
}

REGION_ALIASES = {
    "northland": 9,
    "auckland": 1,
    "waikato": 2,
    "bay of plenty": 3,
    "gisborne": 4,
    "hawkes bay": 5,
    "hawke's bay": 5,
    "taranaki": 6,
    "manawatu": 7,
    "manawatu / whanganui": 7,
    "wellington": 8,
    "nelson": 10,
    "marlborough": 11,
    "tasman": 12,
    "west coast": 13,
    "canterbury": 14,
    "otago": 15,
    "southland": 16,
}


def die(message: str, code: int = 1) -> None:
    print(f"trademe-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    url = BASE_API + path
    if params:
        clean = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in params.items() if v not in (None, "")}
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
        "User-Agent": UA,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("ErrorDescription") or payload.get("Message") or payload.get("message") or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def parse_tm_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    m = re.search(r"/Date\((\d+)", value)
    if not m:
        return value
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return value


def region_value(region: str | None) -> str | None:
    if not region:
        return None
    if str(region).isdigit():
        return str(region)
    return str(REGION_ALIASES.get(region.strip().lower(), region))


def pick_attrs(item: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    attrs = item.get("Attributes") or []
    if isinstance(attrs, list):
        for attr in attrs[:30]:
            if not isinstance(attr, dict):
                continue
            key = attr.get("DisplayName") or attr.get("Name")
            val = attr.get("DisplayValue") or attr.get("Value")
            if key and val is not None:
                out[str(key)] = str(val)
    return out


def listing_url(listing_id: Any, title: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return f"{BASE_WEB}/a/marketplace/listing/{listing_id}" + (f"/{slug}" if slug else "")


def parse_listing(item: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    lid = item.get("ListingId")
    title = item.get("Title") or ""
    return {
        "listing_id": lid,
        "title": title,
        "subtitle": item.get("Subtitle"),
        "category": item.get("Category"),
        "category_path": item.get("CategoryPath"),
        "region": item.get("Region"),
        "district": item.get("District"),
        "suburb": item.get("Suburb"),
        "price_display": item.get("PriceDisplay"),
        "start_price": item.get("StartPrice"),
        "buy_now_price": item.get("BuyNowPrice"),
        "has_buy_now": item.get("HasBuyNow"),
        "is_classified": item.get("IsClassified"),
        "is_buy_now_only": item.get("IsBuyNowOnly"),
        "photo": item.get("PictureHref") or item.get("PhotoHref"),
        "photos": item.get("PhotoUrls"),
        "start_date": parse_tm_date(item.get("StartDate")),
        "end_date": parse_tm_date(item.get("EndDate")),
        "as_at": parse_tm_date(item.get("AsAt")),
        "member_id": item.get("MemberId"),
        "company": item.get("Company"),
        "job_type": item.get("JobType"),
        "pay_benefits": item.get("PayBenefits"),
        "bedrooms": item.get("Bedrooms"),
        "bathrooms": item.get("Bathrooms"),
        "property_type": item.get("PropertyType"),
        "geographic_location": item.get("GeographicLocation"),
        "attributes": pick_attrs(item) if detail else None,
        "url": listing_url(lid, title) if lid else None,
    }


def search(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = SEARCH_ENDPOINTS[args.type]
    params: dict[str, Any] = {
        "search_string": args.query,
        "rows": min(max(1, args.limit), 100),
        "page": max(1, args.page),
        "region": region_value(args.region),
        "price_min": args.price_min,
        "price_max": args.price_max,
        "sort_order": args.sort,
    }
    if args.category:
        params["category"] = args.category
    if args.type.startswith("property") or args.type in {"flatmates", "rural", "retirement"}:
        params.update({"bedrooms_min": args.bedrooms_min, "bedrooms_max": args.bedrooms_max})
    started = time.perf_counter()
    payload = request_json(endpoint, params)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    listings = [parse_listing(x) for x in (payload or {}).get("List", []) if isinstance(x, dict)]
    return {
        "type": args.type,
        "query": args.query,
        "total_count": (payload or {}).get("TotalCount"),
        "page": (payload or {}).get("Page"),
        "page_size": (payload or {}).get("PageSize"),
        "elapsed_ms": elapsed_ms,
        "listings": listings,
    }


def cmd_search(args: argparse.Namespace) -> None:
    emit(search(args), args.json)


def cmd_listing(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    payload = request_json(f"/listings/{urllib.parse.quote(str(args.listing_id))}")
    data = {
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "listing": parse_listing(payload or {}, detail=True),
        "raw": payload if args.raw else None,
    }
    emit(data, args.json)


def cmd_regions(args: argparse.Namespace) -> None:
    data = request_json("/localities/regions")
    regions = []
    for r in data or []:
        if not isinstance(r, dict):
            continue
        regions.append({"id": r.get("LocalityId"), "name": r.get("Name"), "district_count": len(r.get("Districts") or [])})
    emit({"count": len(regions), "regions": regions}, args.json)


def walk_categories(node: dict[str, Any], depth: int = 0, max_depth: int = 2) -> list[dict[str, Any]]:
    out = [{"name": node.get("Name"), "number": node.get("Number"), "path": node.get("Path"), "depth": depth, "is_leaf": node.get("IsLeaf")}]
    if depth < max_depth:
        for child in node.get("Subcategories") or []:
            if isinstance(child, dict):
                out.extend(walk_categories(child, depth + 1, max_depth))
    return out


def cmd_categories(args: argparse.Namespace) -> None:
    data = request_json("/categories")
    rows = walk_categories(data or {}, max_depth=args.depth)
    if args.query:
        q = args.query.lower()
        rows = [r for r in rows if q in (str(r.get("name") or "") + " " + str(r.get("path") or "")).lower()]
    emit({"count": len(rows), "categories": rows[: args.limit]}, args.json)


def print_search(data: dict[str, Any]) -> None:
    print(f"Trade Me {data.get('type')}: {data.get('total_count')} total, showing {len(data.get('listings') or [])} ({data.get('elapsed_ms')} ms)")
    print()
    for item in data.get("listings") or []:
        loc = ", ".join(x for x in [item.get("suburb"), item.get("district"), item.get("region")] if x)
        price = item.get("price_display") or ""
        print(f"{item.get('listing_id')}  {item.get('title')}")
        bits = [price, loc, item.get("category_path")]
        print("  " + " | ".join(str(x) for x in bits if x))
        if item.get("subtitle"):
            print(f"  {item.get('subtitle')}")
        if item.get("url"):
            print(f"  {item.get('url')}")
        print()


def print_generic(data: dict[str, Any]) -> None:
    if "listing" in data:
        print_search({"type": "listing", "total_count": 1, "elapsed_ms": data.get("elapsed_ms"), "listings": [data["listing"]]})
    elif "regions" in data:
        for r in data["regions"]:
            print(f"{r['id']:>3}  {r['name']} ({r['district_count']} districts)")
    elif "categories" in data:
        for c in data["categories"]:
            indent = "  " * int(c.get("depth") or 0)
            print(f"{indent}{c.get('number') or '-'}  {c.get('name')}  {c.get('path') or ''}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        cleaned = {k: v for k, v in data.items() if v is not None}
        print(json.dumps(cleaned, indent=2, ensure_ascii=False))
    elif "listings" in data:
        print_search(data)
    else:
        print_generic(data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lightweight Trade Me NZ public read-only search CLI.")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search Trade Me public listing endpoints")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--type", choices=sorted(SEARCH_ENDPOINTS), default="marketplace")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--region", help="region name or numeric id, e.g. auckland or 1")
    sp.add_argument("--category", help="Trade Me category number/path fragment when known")
    sp.add_argument("--price-min", type=float)
    sp.add_argument("--price-max", type=float)
    sp.add_argument("--bedrooms-min", type=int)
    sp.add_argument("--bedrooms-max", type=int)
    sp.add_argument("--sort", help="Trade Me sort_order value when known")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("listing", help="fetch public listing details")
    sp.add_argument("listing_id")
    sp.add_argument("--raw", action="store_true", help="include raw API payload in JSON output")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_listing)

    sp = sub.add_parser("regions", help="list Trade Me region ids")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_regions)

    sp = sub.add_parser("categories", help="list/search Trade Me categories")
    sp.add_argument("--query", help="filter category names/paths")
    sp.add_argument("--depth", type=int, default=2)
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
