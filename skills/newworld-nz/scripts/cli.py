#!/usr/bin/env python3
"""New World NZ CLI — live product/store lookup via New World web APIs.

Generated after sniffing newworld.co.nz with Hermes+CloakBrowser CDP. Unofficial.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_WEB = "https://www.newworld.co.nz"
BASE_API = "https://api-prod.newworld.co.nz/v1/edge"
DEFAULT_STORE_ID = os.environ.get("NEWWORLD_STORE_ID", "ef977d89-f3d8-4e8b-8a48-b895ded38646")  # New World Papakura
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "newworld-cli"
TOKEN_FILE = CACHE_DIR / "guest-token.json"
UA = os.environ.get(
    "NEWWORLD_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)


def die(msg: str, code: int = 1) -> None:
    print(f"newworld: {msg}", file=sys.stderr)
    raise SystemExit(code)


def money(cents: Any) -> str:
    try:
        return f"${int(cents) / 100:.2f}"
    except Exception:
        return "-"


def request_json(method: str, url: str, data: Any = None, token: str | None = None, timeout: int = 30) -> Any:
    body = None
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE_WEB,
        "Referer": BASE_WEB + "/",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            detail = payload.get("message") or payload.get("code") or raw[:300]
        except Exception:
            detail = raw[:300]
        die(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e.reason}")


def get_guest_token(force: bool = False) -> str:
    if not force and TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text())
            if cached.get("access_token") and cached.get("expires_epoch", 0) > time.time() + 60:
                return cached["access_token"]
        except Exception:
            pass
    fingerprint_user = os.environ.get("NEWWORLD_FINGERPRINT_USER", "newworld-cli")
    payload = {"fingerprintUser": fingerprint_user, "fingerprintGuest": UA}
    data = request_json("POST", BASE_WEB + "/api/user/get-current-user", payload)
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        die("could not obtain guest access token")
    expires = data.get("expires_time") or ""
    # Tokens are typically 30 minutes. Avoid needing date parsing deps.
    expires_epoch = time.time() + 25 * 60
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({"access_token": token, "expires_time": expires, "expires_epoch": expires_epoch}, indent=2))
    return token


def api(method: str, path: str, data: Any = None) -> Any:
    token = get_guest_token()
    return request_json(method, BASE_API + path, data, token=token)


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_token(args: argparse.Namespace) -> None:
    token = get_guest_token(force=args.refresh)
    if args.raw:
        print(token)
    else:
        print(f"guest token ok ({len(token)} chars, cached at {TOKEN_FILE})")


def cmd_stores(args: argparse.Namespace) -> None:
    data = api("GET", "/store")
    stores = data.get("stores", data if isinstance(data, list) else [])
    q = (args.query or "").lower()
    if q:
        stores = [s for s in stores if q in (s.get("name", "") + " " + s.get("address", "")).lower()]
    if args.json:
        print_json(stores[: args.limit])
        return
    for s in stores[: args.limit]:
        flags = []
        if s.get("clickAndCollect"):
            flags.append("collect")
        if s.get("delivery"):
            flags.append("delivery")
        print(f"{s.get('id')}  {s.get('name')}  ({', '.join(flags) or 'store'})")
        print(f"  {s.get('address')}")


def cmd_categories(args: argparse.Namespace) -> None:
    data = api("GET", f"/store/{args.store_id}/categories")
    if args.json:
        print_json(data)
        return
    def walk(nodes: list[dict], depth: int = 0):
        for n in nodes:
            print("  " * depth + "- " + n.get("name", ""))
            if depth < args.depth:
                walk(n.get("children") or [], depth + 1)
    walk(data)


def product_summary(p: dict[str, Any]) -> str:
    pid = p.get("productId") or p.get("productID") or p.get("objectID") or ""
    brand = p.get("brand") or ""
    name = p.get("name") or p.get("displayName") or ""
    display = p.get("displayName") or ""
    price = "-"
    if p.get("singlePrice"):
        price = money(p["singlePrice"].get("price"))
    elif p.get("averagePrice") is not None:
        # Algolia result can be dollars, decorated result is cents.
        try: price = f"${float(p.get('averagePrice')):.2f}"
        except Exception: pass
    promo = ""
    promos = p.get("promotions") or p.get("promotionBadges") or []
    if promos:
        promo_bits = []
        for x in promos[:2]:
            if isinstance(x, dict):
                desc = x.get("description") or x.get("name") or x.get("decalDescription")
                if not desc and x.get("rewardValue"):
                    desc = f"special {money(x.get('rewardValue'))}"
                if x.get("cardDependencyFlag"):
                    desc = (desc or "special") + " with Clubcard"
                promo_bits.append(desc or "special")
            else:
                promo_bits.append(str(x))
        promo = "  promo: " + "; ".join(promo_bits)
    cat = ""
    trees = p.get("categoryTrees") or []
    if trees:
        t = trees[0]
        cat = " / ".join(x for x in [t.get("level0"), t.get("level1"), t.get("level2")] if x)
    elif p.get("category0"):
        cat = " / ".join((p.get("category0") or [])[:1] + (p.get("category1") or [])[:1] + (p.get("category2") or [])[:1])
    line = f"{pid:18} {price:>8}  {brand} {name} {display}".strip()
    if cat:
        line += f"\n  {cat}"
    if promo:
        line += f"\n  {promo}"
    return line


def search_payload(query: str, store_id: str, limit: int, page: int, promo_only: bool = False, category: str | None = None) -> dict[str, Any]:
    filters = [f"stores:{store_id}"]
    if promo_only:
        filters.append(f"onPromotion:{store_id}")
    if category:
        # Useful for exact Algolia category facet values; command keeps it raw intentionally.
        filters.append(category)
    page0 = max(page - 1, 0)
    return {
        "algoliaQuery": {
            "attributesToHighlight": [],
            "attributesToRetrieve": ["productID", "Type", "sponsored", "category0NI", "category1NI", "category2NI"],
            "facets": ["brand", "category1NI", "onPromotion", "productFacets", "tobacco"],
            "filters": " AND ".join(filters),
            "highlightPostTag": "__/ais-highlight__",
            "highlightPreTag": "__ais-highlight__",
            "hitsPerPage": limit,
            "maxValuesPerFacet": 100,
            "page": page0,
            "query": query,
            "analyticsTags": ["fs#WEB:desktop"],
        },
        "algoliaFacetQueries": [],
        "storeId": store_id,
        "hitsPerPage": limit,
        "page": page0,
        "sortOrder": "NI_POPULARITY_ASC",
        "tobaccoQuery": True,
        "precisionMedia": {
            "adDomain": "SEARCH_PAGE" if query else "CATEGORY_PAGE",
            "adPositions": [4, 8, 12],
            "publishImpressionEvent": False,
            "disableAds": False,
        },
    }


def cmd_search(args: argparse.Namespace) -> None:
    data = api("POST", "/search/paginated/products", search_payload(args.query, args.store_id, args.limit, args.page, args.promo))
    products = data.get("products") or []
    if args.json:
        print_json(data)
        return
    print(f"{len(products)} products for {args.query!r} at store {args.store_id}")
    for p in products:
        print(product_summary(p))


def normalize_product_id(pid: str) -> str:
    pid = pid.strip().upper().replace("_", "-")
    if pid.isdigit():
        return f"{pid}-EA-000"
    if "-" not in pid and len(pid) >= 7:
        return pid
    return pid


def cmd_product(args: argparse.Namespace) -> None:
    ids = [normalize_product_id(x) for x in args.product_ids]
    data = api("POST", f"/store/{args.store_id}/decorateProducts", {"productIds": ids})
    products = data.get("products") or []
    if args.json:
        print_json(data)
        return
    for p in products:
        print(product_summary(p))
        if p.get("description"):
            print("  " + str(p.get("description"))[:300])


def cmd_specials(args: argparse.Namespace) -> None:
    args.query = args.query or ""
    args.promo = True
    cmd_search(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="newworld",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Unofficial New World NZ CLI for stores, categories, product search and prices.",
        epilog=textwrap.dedent(f"""
        Defaults:
          store id: {DEFAULT_STORE_ID} (override with --store-id or NEWWORLD_STORE_ID)

        Examples:
          newworld stores --query auckland
          newworld search milk --limit 10
          newworld specials --limit 20
          newworld product 5201479
          newworld categories --depth 2
        """),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("token", help="fetch/cache a guest token")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--raw", action="store_true")
    sp.set_defaults(func=cmd_token)

    sp = sub.add_parser("stores", help="list New World stores")
    sp.add_argument("--query", "-q", default="", help="filter by name/address")
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("categories", help="list categories for a store")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--depth", type=int, default=2)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_categories)

    sp = sub.add_parser("search", help="search products and prices")
    sp.add_argument("query")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--promo", action="store_true", help="only promotional products")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("specials", help="search promotional products")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--limit", "-n", type=int, default=20)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)

    sp = sub.add_parser("product", help="decorate product IDs with store-specific price/details")
    sp.add_argument("product_ids", nargs="+")
    sp.add_argument("--store-id", default=DEFAULT_STORE_ID)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
