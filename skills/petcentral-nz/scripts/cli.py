#!/usr/bin/env python3
"""Read-only Pet Central NZ Shopify catalogue CLI."""
from __future__ import annotations
import argparse, datetime as dt, json, re, sys, urllib.error, urllib.parse, urllib.request
from typing import Any

BASE = "https://petcentral.co.nz"
UA = "TheColabSkills/1.0 (+https://github.com/thecolab-ai/.skills; read-only)"
MAX_LIMIT = 50
MAX_RESPONSE_BYTES = 5_000_000

class CliError(Exception): pass

def allowed(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in {"petcentral.co.nz", "www.petcentral.co.nz"} and parsed.username is None and parsed.password is None and port in (None, 443)

class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl): raise CliError("refusing redirect outside the Pet Central HTTPS storefront")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def timestamp() -> str: return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def limit(value: str) -> int:
    try: n = int(value)
    except ValueError as e: raise argparse.ArgumentTypeError("must be an integer") from e
    if not 1 <= n <= MAX_LIMIT: raise argparse.ArgumentTypeError(f"must be 1-{MAX_LIMIT}")
    return n

def get(url: str, timeout: int) -> tuple[bytes, str]:
    if not allowed(url): raise CliError("refusing request outside the Pet Central HTTPS storefront")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.8"})
    try:
        with urllib.request.build_opener(StorefrontRedirectHandler()).open(req, timeout=timeout) as r:
            if not allowed(r.url): raise CliError("refusing response outside the Pet Central HTTPS storefront")
            body = r.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES: raise CliError("upstream response exceeded the 5 MB safety limit")
            return body, r.url
    except urllib.error.HTTPError as e: raise CliError(f"upstream returned HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e: raise CliError(f"network error for {url}: {getattr(e, 'reason', str(e))}") from e

def product(raw: dict[str, Any]) -> dict[str, Any]:
    variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    images = raw.get("images") if isinstance(raw.get("images"), list) else []
    prices = [float(v["price"]) for v in variants if isinstance(v, dict) and str(v.get("price", "")).replace(".", "", 1).isdigit()]
    return {"id": raw.get("id"), "title": raw.get("title") or "", "handle": raw.get("handle") or "", "url": BASE + "/products/" + str(raw.get("handle") or ""), "vendor": raw.get("vendor") or "", "product_type": raw.get("product_type") or "", "tags": raw.get("tags") or [], "available": raw.get("available"), "price_min_nzd": min(prices) if prices else None, "price_max_nzd": max(prices) if prices else None, "variants": [{"id": v.get("id"), "title": v.get("title"), "sku": v.get("sku"), "available": v.get("available"), "price_nzd": float(v["price"]) if str(v.get("price", "")).replace(".", "", 1).isdigit() else None} for v in variants if isinstance(v, dict)], "images": [i.get("src") for i in images if isinstance(i, dict) and i.get("src")]}

def fetch_products(page: int, timeout: int) -> tuple[list[dict[str, Any]], str]:
    body, final = get(f"{BASE}/products.json?limit=250&page={page}", timeout)
    try: data = json.loads(body)
    except json.JSONDecodeError as e: raise CliError("invalid JSON from Shopify products endpoint") from e
    return [p for p in data.get("products", []) if isinstance(p, dict)], final

def search(query: str, page: int, max_results: int, timeout: int) -> dict[str, Any]:
    if not query.strip(): raise CliError("search query must not be empty")
    rows, url = fetch_products(page, timeout)
    needle = query.casefold()
    matches = [product(p) for p in rows if needle in (str(p.get("title", "")) + " " + str(p.get("vendor", "")) + " " + str(p.get("product_type", "")) + " " + " ".join(p.get("tags", []) if isinstance(p.get("tags"), list) else [])).casefold()]
    return {"source": "shopify-products-json", "source_url": url, "retrieved_at": timestamp(), "query": query, "page": page, "limit": max_results, "results": matches[:max_results], "catalogue_page_count": len(rows), "note": "Public catalogue snapshot only; product suitability is not veterinary advice."}

def detail(value: str, timeout: int) -> dict[str, Any]:
    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        if not allowed(value) or "/products/" not in parsed.path: raise CliError("provide a Pet Central HTTPS /products/<handle> URL")
        value = parsed.path.split("/products/", 1)[1]
    handle = urllib.parse.unquote(value.rstrip("/").split("/products/")[-1].split("?")[0]).removesuffix(".js")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", handle): raise CliError("provide a Pet Central product handle or HTTPS /products/<handle> URL")
    url = f"{BASE}/products/{urllib.parse.quote(handle)}.js"
    body, final = get(url, timeout)
    try: raw = json.loads(body)
    except json.JSONDecodeError as e: raise CliError("invalid JSON from Shopify product endpoint") from e
    return {"source": "shopify-product-json", "source_url": final, "retrieved_at": timestamp(), "product": product(raw), "note": "Public product data only; verify nutrition and health decisions with an appropriate professional."}

def collections(timeout: int) -> dict[str, Any]:
    body, final = get(BASE + "/collections.json?limit=250", timeout)
    try: data = json.loads(body)
    except json.JSONDecodeError as e: raise CliError("invalid JSON from Shopify collections endpoint") from e
    rows = [{"id": c.get("id"), "title": c.get("title"), "handle": c.get("handle"), "url": BASE + "/collections/" + str(c.get("handle") or "")} for c in data.get("collections", []) if isinstance(c, dict)]
    return {"source": "shopify-collections-json", "source_url": final, "retrieved_at": timestamp(), "results": rows}

def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json: print(json.dumps(data, ensure_ascii=False, indent=2)); return
    for p in data.get("results", [data.get("product")] if data.get("product") else []): print(f"{p.get('title')} | ${p.get('price_min_nzd', '-') } | {p.get('url', '')}")

def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Pet Central NZ public Shopify catalogue CLI.")
    ap.add_argument("--timeout", type=limit, default=10, help="network timeout seconds, 1-50 (default: 10)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="search one bounded Shopify catalogue page"); s.add_argument("query"); s.add_argument("--page", type=limit, default=1); s.add_argument("--limit", type=limit, default=12); s.add_argument("--json", action="store_true")
    p = sub.add_parser("product", help="get product detail by handle or URL"); p.add_argument("handle_or_url"); p.add_argument("--json", action="store_true")
    c = sub.add_parser("collections", help="list public collections"); c.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        data = search(a.query, a.page, a.limit, a.timeout) if a.cmd == "search" else detail(a.handle_or_url, a.timeout) if a.cmd == "product" else collections(a.timeout)
        emit(data, a.json)
    except CliError as e: print(f"petcentral-nz: {e}", file=sys.stderr); return 1
    return 0
if __name__ == "__main__": raise SystemExit(main())
