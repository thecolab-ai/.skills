#!/usr/bin/env python3
"""Trade Me NZ public-search CLI and browser seller-workflow planner.

Public commands call keyless public endpoints. Seller commands emit deterministic
plans for the skill's browser automation; they never handle passwords, cookies,
browser storage, session tokens, or developer credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

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
    "jobs": "/search/jobs",
    "flatmates": "/search/flatmates",
    "commercial-sale": "/search/property/commercialsale",
    "commercial-lease": "/search/property/commerciallease",
    "rural": "/search/property/rural",
    "retirement": "/search/property/retirement",
}

SELLER_ROUTES = {
    "summary": "/a/my-trade-me/sell",
    "selling": "/a/my-trade-me/sell/selling",
    "sold": "/a/my-trade-me/sell/sold",
    "unsold": "/a/my-trade-me/sell/unsold",
    "create": "/a/list",
}

# Region IDs sourced from the live /regions endpoint. Keep in sync with that
# response rather than hand-numbering, because Trade Me's regional ids are not
# alphabetical and have caught us out before.
REGION_ALIASES = {
    "northland": 9,
    "auckland": 1,
    "waikato": 14,
    "bay of plenty": 2,
    "gisborne": 4,
    "hawkes bay": 5,
    "hawke's bay": 5,
    "taranaki": 12,
    "manawatu": 6,
    "manawatu / whanganui": 6,
    "whanganui": 6,
    "wellington": 15,
    "nelson": 8,
    "nelson / tasman": 8,
    "tasman": 8,
    "marlborough": 7,
    "west coast": 16,
    "canterbury": 3,
    "otago": 10,
    "southland": 11,
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
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
    }
    try:
        body, _ct, _final = nzfetch.fetch_bytes(
            url, timeout=timeout, headers=headers, accept="application/json, text/plain, */*"
        )
        raw = body.decode("utf-8", "replace")
        return json.loads(raw) if raw else None
    except nzfetch.Blocked as e:
        die(f"network error: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    except json.JSONDecodeError as e:
        die(f"invalid JSON from {url}: {e}")


def parse_tm_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    m = re.search(r"/Date\((\d+)", value)
    if not m:
        return value
    try:
        raw = int(m.group(1))
        seconds = raw / 1000 if raw >= 100_000_000_000 else raw
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
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


def read_json_object(path_value: str) -> dict[str, Any]:
    path = pathlib.Path(path_value).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        die(f"cannot read JSON file {path}: {exc}", 2)
    except json.JSONDecodeError as exc:
        die(f"invalid JSON file {path}: {exc}", 2)
    if not isinstance(payload, dict):
        die(f"JSON file {path} must contain one object", 2)
    return payload


def seller_url(route: str, listing_id: int | None = None) -> str:
    if route == "listing":
        if listing_id is None:
            die("listing route requires a listing id", 2)
        return f"{BASE_WEB}/a/listing/{listing_id}"
    if route in {"edit", "withdraw"}:
        if listing_id is None:
            die(f"{route} route requires a listing id", 2)
        return f"{BASE_WEB}/a/marketplace/edit/{listing_id}?reloadDraft=1"
    return BASE_WEB + SELLER_ROUTES[route]


def browser_plan(
    operation: str,
    *,
    route: str,
    listing_id: int | None = None,
    mutation: bool = False,
    input_file: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if listing_id is not None and listing_id <= 0:
        die("listing id must be a positive integer", 2)
    plan: dict[str, Any] = {
        "operation": operation,
        "surface": "browser",
        "url": seller_url(route, listing_id),
        "authentication": "ordinary Trade Me website session",
        "browser_session_data": "never read, copy, export, persist, or send",
        "login_handoff": (
            "If redirected to sign-in, email/2FA verification, or CAPTCHA, let "
            "the user complete it in the same browser, then resume."
        ),
        "mutation": mutation,
        "action_time_confirmation_required": mutation,
        "instructions": (
            "Use the browser-backed workflow in references/browser-workflow.md; "
            "this CLI only validates and describes the browser task."
        ),
    }
    if listing_id is not None:
        plan["listing_id"] = listing_id
        plan["target_match"] = "match the exact visible listing id before reading or acting"
    if input_file:
        plan["input_file"] = str(pathlib.Path(input_file).expanduser())
    if details:
        plan["details"] = details
    if mutation:
        plan["final_step"] = (
            "Stop on Trade Me's review/confirmation screen. Report the exact "
            "target, changes, and fee shown, then obtain a separate user "
            "confirmation immediately before the final submit click."
        )
    return plan


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
    listings = [
        parse_listing(x)
        for x in (payload or {}).get("List", [])
        if isinstance(x, dict)
    ][: args.limit]
    return {
        "type": args.type,
        "query": args.query,
        "total_count": (payload or {}).get("TotalCount"),
        "page": (payload or {}).get("Page"),
        "page_size": (payload or {}).get("PageSize"),
        "requested_limit": args.limit,
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


def cmd_seller_summary(args: argparse.Namespace) -> None:
    emit(browser_plan("seller-summary", route="summary"), args.json)


def cmd_my_selling(args: argparse.Namespace) -> None:
    emit(browser_plan("my-selling", route="selling"), args.json)


def cmd_my_sold(args: argparse.Namespace) -> None:
    emit(browser_plan("my-sold", route="sold"), args.json)


def cmd_my_unsold(args: argparse.Namespace) -> None:
    emit(browser_plan("my-unsold", route="unsold"), args.json)


def cmd_seller_listing(args: argparse.Namespace) -> None:
    emit(
        browser_plan(
            "seller-listing",
            route="listing",
            listing_id=args.listing_id,
        ),
        args.json,
    )


def cmd_prepare_edit(args: argparse.Namespace) -> None:
    emit(
        browser_plan(
            "prepare-edit",
            route="edit",
            listing_id=args.listing_id,
        ),
        args.json,
    )


def cmd_validate_listing(args: argparse.Namespace) -> None:
    payload = read_json_object(args.data_file)
    checks = {
        "title_present": bool(str(payload.get("Title") or "").strip()),
        "description_present": bool(payload.get("Description")),
        "category_present": bool(payload.get("Category")),
        "price_present": any(
            payload.get(key) is not None
            for key in ("StartPrice", "BuyNowPrice", "Price")
        ),
    }
    emit(
        {
            "valid_for_browser_preparation": all(checks.values()),
            "checks": checks,
            "note": (
                "Trade Me performs authoritative validation in the normal "
                "website form; no authenticated API call was made."
            ),
        },
        args.json,
    )


def cmd_create_listing(args: argparse.Namespace) -> None:
    payload = read_json_object(args.data_file)
    title = str(payload.get("Title") or "").strip()
    if not title:
        die("listing payload must include a non-empty Title", 2)
    emit(
        browser_plan(
            "create-listing",
            route="create",
            mutation=True,
            input_file=args.data_file,
            details={"title": title},
        ),
        args.json,
    )


def cmd_edit_listing(args: argparse.Namespace) -> None:
    payload = read_json_object(args.data_file)
    listing_id = payload.get("ListingId")
    if listing_id is None:
        die("edit payload must include ListingId", 2)
    try:
        listing_number = int(listing_id)
    except (TypeError, ValueError):
        die("edit payload ListingId must be an integer", 2)
    emit(
        browser_plan(
            "edit-listing",
            route="edit",
            listing_id=listing_number,
            mutation=True,
            input_file=args.data_file,
            details={"title": payload.get("Title")},
        ),
        args.json,
    )


def validate_withdraw_args(args: argparse.Namespace) -> None:
    if args.sold and args.sale_price is None:
        die("--sale-price is required with --sold", 2)
    if not args.sold and args.sale_price is not None:
        die("--sale-price may only be used with --sold", 2)


def cmd_withdraw_listing(args: argparse.Namespace) -> None:
    validate_withdraw_args(args)
    emit(
        browser_plan(
            "withdraw-listing",
            route="withdraw",
            listing_id=args.listing_id,
            mutation=True,
            details={
                "disposition": "sold" if args.sold else "not-sold",
                "sale_price": args.sale_price,
                "reason": args.reason,
            },
        ),
        args.json,
    )


def cmd_relist_listing(args: argparse.Namespace) -> None:
    emit(
        browser_plan(
            "relist-listing",
            route="unsold",
            listing_id=args.listing_id,
            mutation=True,
            details={
                "note": (
                    "Find the listing by exact id on Unsold and use the visible "
                    "relist action; do not guess a direct action URL."
                )
            },
        ),
        args.json,
    )


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
    ap = argparse.ArgumentParser(
        description=(
            "Trade Me NZ public search and browser-backed seller workflow planner. "
            "Seller commands do not access or persist browser credentials."
        )
    )
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

    sp = sub.add_parser("seller-summary", help="plan a browser-backed seller summary read")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_seller_summary)

    def add_browser_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true")

    sp = sub.add_parser("my-selling", help="plan a signed-in browser read of active listings")
    add_browser_flags(sp)
    sp.set_defaults(func=cmd_my_selling)

    sp = sub.add_parser("my-sold", help="plan a signed-in browser read of sold items")
    add_browser_flags(sp)
    sp.set_defaults(func=cmd_my_sold)

    sp = sub.add_parser("my-unsold", help="plan a signed-in browser read of unsold items")
    add_browser_flags(sp)
    sp.set_defaults(func=cmd_my_unsold)

    sp = sub.add_parser("seller-listing", help="plan a browser read of one seller listing")
    sp.add_argument("listing_id", type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_seller_listing)

    sp = sub.add_parser("prepare-edit", help="open an existing listing's website edit flow")
    sp.add_argument("listing_id", type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_prepare_edit)

    sp = sub.add_parser("validate-listing", help="perform local checks before filling the website form")
    sp.add_argument("--data-file", required=True)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_validate_listing)

    def add_mutation_plan_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true")

    sp = sub.add_parser("create-listing", help="plan filling a new website listing from JSON")
    sp.add_argument("--data-file", required=True)
    add_mutation_plan_flags(sp)
    sp.set_defaults(func=cmd_create_listing)

    sp = sub.add_parser("edit-listing", help="plan filling an existing website edit form from JSON")
    sp.add_argument("--data-file", required=True)
    add_mutation_plan_flags(sp)
    sp.set_defaults(func=cmd_edit_listing)

    sp = sub.add_parser("withdraw-listing", help="plan withdrawing an active listing in the browser")
    sp.add_argument("listing_id", type=int)
    sp.add_argument("--sold", action="store_true", help="declare the item sold")
    sp.add_argument("--sale-price", type=float)
    sp.add_argument("--reason", help="reason for withdrawing as not sold; maximum 255 characters")
    add_mutation_plan_flags(sp)
    sp.set_defaults(func=cmd_withdraw_listing)

    sp = sub.add_parser("relist-listing", help="plan relisting an unsold item in the browser")
    sp.add_argument("listing_id", type=int)
    add_mutation_plan_flags(sp)
    sp.set_defaults(func=cmd_relist_listing)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(args, "limit") and not 1 <= args.limit <= 100:
        die("--limit must be between 1 and 100", 2)
    if hasattr(args, "page") and args.page < 1:
        die("--page must be at least 1", 2)
    if getattr(args, "reason", None) and len(args.reason) > 255:
        die("--reason must be 255 characters or fewer", 2)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
