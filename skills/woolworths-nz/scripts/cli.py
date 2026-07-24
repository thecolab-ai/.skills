#!/usr/bin/env python3
"""Woolworths NZ product and optional personal-account CLI.

Public product lookup is stdlib-only. Account commands are registered only when
the caller supplies Woolworths credentials; browser-assisted login is isolated
to ``browser_auth.py`` and persists cookies, never the password.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

BASE_WEB = "https://www.woolworths.co.nz"
BASE_API = BASE_WEB + "/api/v1"
UA = os.environ.get(
    "WOOLWORTHS_NZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)
UI_VER = os.environ.get("WOOLWORTHS_NZ_UI_VER", "7.70.51")
ACCOUNT_USER_KEYS = ("WOOLWORTHS_USERNAME", "WOOLWORTHS_EMAIL")
ACCOUNT_SIGNIN_ENV = "WOOLWORTHS_PASSWORD"
SESSION_COOKIE_DOMAINS = {"woolworths.co.nz", ".woolworths.co.nz", "www.woolworths.co.nz"}


def credential_value(keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return None


def account_credentials() -> tuple[str, str] | None:
    username = credential_value(ACCOUNT_USER_KEYS)
    password = os.environ.get(ACCOUNT_SIGNIN_ENV)
    return (username, password) if username and password else None


def account_commands_enabled(env: Any = None) -> bool:
    source = os.environ if env is None else env
    username = any(source.get(key) for key in ACCOUNT_USER_KEYS)
    return bool(username and source.get(ACCOUNT_SIGNIN_ENV))


def session_file() -> pathlib.Path:
    override = os.environ.get("WOOLWORTHS_SESSION_FILE")
    if override:
        return pathlib.Path(override).expanduser()
    state_home = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state"))
    return state_home / "woolworths-nz" / "cookies.json"


def die(message: str, code: int = 1) -> None:
    print(f"woolworths-nz: {message}", file=sys.stderr)
    raise SystemExit(code)


def request_json(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    url = BASE_API + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    headers = {
        "X-Requested-With": "OnlineShopping.WebApp",
        "X-UI-Ver": UI_VER,
        "Referer": BASE_WEB + "/",
        "Origin": BASE_WEB,
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


def load_session_cookies() -> list[dict[str, Any]]:
    path = session_file()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"could not read session cache {path}: {exc}")
    if not isinstance(payload, list):
        die(f"invalid session cache {path}")
    return [
        item
        for item in payload
        if isinstance(item, dict)
        and item.get("name")
        and str(item.get("domain", "")).lower() in SESSION_COOKIE_DOMAINS
    ]


def session_cookie_header(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(f"{item['name']}={item.get('value', '')}" for item in cookies)


def xsrf_token(cookies: list[dict[str, Any]]) -> str | None:
    for item in cookies:
        if item.get("name") == "XSRF-TOKEN":
            return urllib.parse.unquote(str(item.get("value", "")))
    return None


def browser_login(*, headed: bool = False) -> dict[str, Any]:
    credentials = account_credentials()
    if not credentials:
        die(
            "account commands require WOOLWORTHS_USERNAME (or WOOLWORTHS_EMAIL) "
            "and WOOLWORTHS_PASSWORD",
            2,
        )
    try:
        from browser_auth import login_and_save
    except ImportError:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        try:
            from browser_auth import login_and_save
        except ImportError as exc:
            die(f"browser login helper is unavailable: {exc}")
    try:
        return login_and_save(
            credentials[0],
            credentials[1],
            session_file(),
            headed=headed,
        )
    except RuntimeError as exc:
        die(str(exc))


def ensure_account_session(*, force: bool = False, headed: bool = False) -> list[dict[str, Any]]:
    cookies = [] if force else load_session_cookies()
    if cookies:
        return cookies
    browser_login(headed=headed)
    cookies = load_session_cookies()
    if not cookies:
        die("login completed without a reusable Woolworths session")
    return cookies


def account_api(
    method: str,
    path: str,
    data: Any = None,
    *,
    params: dict[str, Any] | None = None,
    retry_auth: bool = True,
) -> Any:
    if not path.startswith("/") or path.startswith("//"):
        die("unsafe account API path")
    url = BASE_API + path
    if params:
        clean = {key: str(value) for key, value in params.items() if value is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    cookies = ensure_account_session()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "OnlineShopping.WebApp",
        "X-UI-Ver": UI_VER,
        "Referer": BASE_WEB + "/",
        "Origin": BASE_WEB,
        "User-Agent": UA,
        "Cookie": session_cookie_header(cookies),
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        token = xsrf_token(cookies)
        if not token:
            if retry_auth:
                ensure_account_session(force=True)
                return account_api(method, path, data, params=params, retry_auth=False)
            die("authenticated session is missing the XSRF token; run `auth login`")
        headers["X-XSRF-TOKEN"] = token
    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8", "replace")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                if retry_auth:
                    ensure_account_session(force=True)
                    return account_api(method, path, data, params=params, retry_auth=False)
                die("Woolworths returned a non-JSON account response; run `auth login`")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403) and retry_auth:
            ensure_account_session(force=True)
            return account_api(method, path, data, params=params, retry_auth=False)
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            if isinstance(payload, dict):
                detail = str(
                    payload.get("message")
                    or payload.get("Message")
                    or payload.get("title")
                    or ""
                )
        except Exception:
            pass
        suffix = f": {detail}" if detail else ""
        die(f"Woolworths account request failed (HTTP {exc.code}){suffix}")
    except urllib.error.URLError as exc:
        die(f"network error: {exc.reason}")


def positive_quantity(value: str) -> float:
    try:
        quantity = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("quantity must be numeric")
    if quantity <= 0 or quantity > 999:
        raise argparse.ArgumentTypeError("quantity must be greater than 0 and at most 999")
    return int(quantity) if quantity.is_integer() else quantity


def nonempty_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise argparse.ArgumentTypeError("list name cannot be empty")
    if len(cleaned) > 100:
        raise argparse.ArgumentTypeError("list name must be at most 100 characters")
    return cleaned


def confidence(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("confidence must be numeric")
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("confidence must be between 0 and 1")
    return parsed


def money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"${float(value):.2f}"
    except Exception:
        return str(value)


def nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def category_from(item: dict[str, Any]) -> str:
    breadcrumb = item.get("breadcrumb") or {}
    parts: list[str] = []
    for key in ("department", "aisle", "shelf"):
        name = nested(breadcrumb, key, "name")
        if name:
            parts.append(str(name))
    if parts:
        return " / ".join(parts)
    departments = item.get("departments") or []
    if departments and isinstance(departments[0], dict):
        return departments[0].get("name") or ""
    return ""


def parse_product(item: dict[str, Any]) -> dict[str, Any]:
    price = item.get("price") or {}
    size = item.get("size") or {}
    quantity = item.get("quantity") or {}
    images_raw = item.get("images") or {}
    if isinstance(images_raw, dict):
        image = images_raw.get("big") or images_raw.get("small")
    elif isinstance(images_raw, list) and images_raw:
        first_image = images_raw[0]
        image = first_image.get("url") if isinstance(first_image, dict) else str(first_image)
    else:
        image = None
    sale_price = price.get("salePrice")
    original_price = price.get("originalPrice")
    is_special = bool(price.get("isSpecial") or price.get("isClubPrice"))
    return {
        "sku": str(item.get("sku") or ""),
        "name": item.get("name") or "",
        "brand": item.get("brand") or "",
        "barcode": item.get("barcode") or "",
        "slug": item.get("slug") or "",
        "price": original_price,
        "sale_price": sale_price,
        "save_price": price.get("savePrice"),
        "save_percentage": price.get("savePercentage"),
        "is_special": is_special,
        "is_club_price": bool(price.get("isClubPrice")),
        "unit": item.get("unit") or "Each",
        "selected_purchasing_unit": item.get("selectedPurchasingUnit"),
        "size": size.get("volumeSize") or "",
        "package_type": size.get("packageType"),
        "cup_price": size.get("cupPrice"),
        "cup_measure": size.get("cupMeasure"),
        "availability": item.get("availabilityStatus") or "Unknown",
        "in_stock": item.get("availabilityStatus") == "In Stock",
        "category": category_from(item),
        "supports_dual_pricing": bool(item.get("supportsBothEachAndKgPricing")),
        "average_weight_per_unit": item.get("averageWeightPerUnit"),
        "average_price_per_each": price.get("averagePricePerSingleUnit"),
        "purchasing_unit_price": price.get("purchasingUnitPrice"),
        "minimum_quantity": quantity.get("min"),
        "maximum_quantity": quantity.get("max"),
        "quantity_increment": quantity.get("increment"),
        "image": image or item.get("imageUrl") or item.get("bigImageUrl"),
        "source_url": BASE_WEB + "/shop/productdetails/" + str(item.get("sku") or "") + "/" + str(item.get("slug") or ""),
    }


def product_items(payload: Any) -> list[dict[str, Any]]:
    items = nested(payload or {}, "products", "items", default=[])
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("type", "Product") == "Product":
            p = parse_product(item)
            if p["sku"] and p["name"]:
                out.append(p)
    return out


def products_query(target: str, *, search: str | None = None, category_id: str | None = None, limit: int = 10, page: int = 1, in_stock_only: bool = False) -> dict[str, Any]:
    size = min(max(1, limit), 48)
    params: dict[str, Any] = {
        "target": target,
        "size": size,
        "page": max(1, page),
        "inStockProductsOnly": str(bool(in_stock_only)).lower(),
    }
    if search:
        params["search"] = search
    if category_id:
        params["categoryId"] = category_id
    started = time.perf_counter()
    payload = request_json("/products", params=params)
    products = product_items(payload)[:limit]
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "target": target,
        "query": search,
        "category_id": category_id,
        "count": len(products),
        "elapsed_ms": elapsed_ms,
        "products": products,
        "raw_total": nested(payload or {}, "products", "totalRecordCount"),
    }


def cmd_search(args: argparse.Namespace) -> None:
    data = products_query("search", search=args.query, limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    if args.size:
        needle = args.size.lower()
        data["products"] = [p for p in data["products"] if needle in (p.get("size") or "").lower()]
        data["count"] = len(data["products"])
    emit(data, args.json)


def cmd_specials(args: argparse.Namespace) -> None:
    if args.query:
        # The upstream specials endpoint ignores the search parameter, so when the
        # user supplies a query we use the search target and filter to specials
        # client-side. Fetch up to the API max so the filter has enough to work with.
        fetch_size = max(args.limit * 4, 24)
        data = products_query("search", search=args.query, limit=fetch_size, page=args.page, in_stock_only=args.in_stock_only)
        specials_only = [p for p in data["products"] if p.get("is_special")]
        data["products"] = specials_only[:args.limit]
        data["count"] = len(data["products"])
        data["target"] = "specials"
    else:
        data = products_query("specials", limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    emit(data, args.json)


def cmd_browse(args: argparse.Namespace) -> None:
    data = products_query("browse", category_id=args.category_id, limit=args.limit, page=args.page, in_stock_only=args.in_stock_only)
    emit(data, args.json)


def cmd_product(args: argparse.Namespace) -> None:
    products = []
    started = time.perf_counter()
    for sku in args.skus:
        payload = request_json(f"/products/{urllib.parse.quote(str(sku))}")
        if isinstance(payload, dict):
            products.append(parse_product(payload))
    data = {"count": len(products), "elapsed_ms": round((time.perf_counter() - started) * 1000), "products": products}
    emit(data, args.json)


def price_label(p: dict[str, Any]) -> str:
    original = p.get("price")
    sale = p.get("sale_price")
    if p.get("is_special") and sale is not None and sale != original:
        label = f"{money(sale)} special"
        if original is not None:
            label += f" (was {money(original)})"
        if p.get("is_club_price"):
            label += " club"
        return label
    return money(sale if sale is not None else original)


def print_products(data: dict[str, Any]) -> None:
    label = data.get("query") or data.get("target") or "products"
    print(f"{label}: {data.get('count', 0)} products ({data.get('elapsed_ms')} ms)")
    total = data.get("raw_total")
    if total is not None:
        print(f"Total available from source: {total}")
    print()
    for p in data.get("products") or []:
        bits = []
        size = p.get("size") or ""
        if size:
            bits.append(str(size))
        if p.get("package_type"):
            bits.append(str(p["package_type"]))
        bits.append(price_label(p))
        stock = "in stock" if p.get("in_stock") else p.get("availability", "unknown")
        bits.append(str(stock).lower())
        print(f"{p.get('sku'):>8}  {p.get('brand', '').title()} {p.get('name', '').title()}".strip())
        print("          " + " | ".join(x for x in bits if x))
        if p.get("cup_price") and p.get("cup_measure"):
            print(f"          unit: {money(p.get('cup_price'))} per {p.get('cup_measure')}")
        if p.get("category"):
            print(f"          category: {p.get('category')}")
        if p.get("supports_dual_pricing"):
            avg = p.get("average_weight_per_unit")
            print(f"          purchase options: Each or Kg" + (f"; avg wt {avg}kg" if avg else ""))
        print()


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_products(data)


def emit_json_or_summary(data: Any, as_json: bool, label: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if isinstance(data, list):
        print(f"{len(data)} {label}")
        for item in data:
            if isinstance(item, dict):
                ident = first_value(item, "id", "listId", "orderId", "sku")
                name = first_value(item, "name", "listName", "title", "productName")
                count = first_value(item, "itemCount", "totalItems", "count")
                values = [value for value in (ident, name, count) if value not in (None, "")]
                print("  " + "  ".join(str(value) for value in values))
            else:
                print(f"  {item}")
        return
    if isinstance(data, dict):
        records = records_from(data, "savedLists", "items", "orders", "products", "results")
        if records:
            emit_json_or_summary(records, False, label)
            return
        print(f"{label}: ok")
        for key in ("id", "listId", "orderId", "name", "listName", "message"):
            if data.get(key) not in (None, ""):
                print(f"  {key}: {data[key]}")
        return
    print(f"{label}: ok")


def first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def records_from(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested_items = value.get("items")
                if isinstance(nested_items, list):
                    return [item for item in nested_items if isinstance(item, dict)]
    return []


def cmd_auth_login(args: argparse.Namespace) -> None:
    result = browser_login(headed=args.headed)
    print(f"Authenticated Woolworths session saved to {result['session_file']}")


def cmd_auth_status(args: argparse.Namespace) -> None:
    path = session_file()
    if not path.exists():
        print("No cached Woolworths session")
        return
    data = account_api("GET", "/bff/get-user")
    if args.json:
        safe = {
            "session_file": str(path),
            "authenticated": bool(
                isinstance(data, dict)
                and (
                    data.get("isAuthenticated")
                    or data.get("isLoggedIn")
                    or data.get("isShopper")
                    or data.get("shopper")
                )
            ),
        }
        print(json.dumps(safe, indent=2))
    else:
        print(f"Woolworths session is valid ({path})")


def cmd_auth_logout(_args: argparse.Namespace) -> None:
    path = session_file()
    if path.exists():
        path.unlink()
        print(f"Removed local Woolworths session cache {path}")
    else:
        print("No cached Woolworths session")


def cmd_orders(args: argparse.Namespace) -> None:
    data = account_api(
        "GET",
        "/shoppers/my/past-orders",
        params={"page": args.page, "dateFilter": args.date_filter},
    )
    emit_json_or_summary(data, args.json, "orders")


def cmd_order(args: argparse.Namespace) -> None:
    order_id = urllib.parse.quote(args.order_id, safe="")
    data = account_api("GET", f"/shoppers/my/past-orders/{order_id}")
    emit_json_or_summary(data, args.json, "order")


def cmd_order_items(args: argparse.Namespace) -> None:
    order_id = urllib.parse.quote(args.order_id, safe="")
    suffix = "/items" if args.order_id == "all" else f"/{order_id}/items"
    data = account_api(
        "GET",
        f"/shoppers/my/past-orders{suffix}",
        params={"page": args.page, "size": args.limit, "sort": args.sort},
    )
    emit_json_or_summary(data, args.json, "order items")


def fetch_past_order_items(order_id: str, *, page_size: int = 100) -> Any:
    """Fetch every catalogue page for one past order (the API caps size at 100)."""
    payload = account_api(
        "GET",
        f"/shoppers/my/past-orders/{order_id}/items",
        params={"page": 1, "size": page_size},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), dict):
        return payload
    first_products = payload["products"]
    items = list(first_products.get("items") or [])
    try:
        total = int(first_products.get("totalItems") or len(items))
    except (TypeError, ValueError):
        total = len(items)

    page = 1
    while len(items) < total and page < 50:
        page += 1
        next_payload = account_api(
            "GET",
            f"/shoppers/my/past-orders/{order_id}/items",
            params={"page": page, "size": page_size},
        )
        next_products = (
            next_payload.get("products")
            if isinstance(next_payload, dict)
            and isinstance(next_payload.get("products"), dict)
            else {}
        )
        next_items = next_products.get("items")
        if not isinstance(next_items, list) or not next_items:
            break
        items.extend(next_items)

    combined = dict(payload)
    combined_products = dict(first_products)
    combined_products["items"] = items
    combined_products["totalItems"] = total
    combined["products"] = combined_products
    return combined


def cmd_invoice_items(args: argparse.Namespace) -> None:
    order_id = urllib.parse.quote(args.order_id, safe="")
    payload = fetch_past_order_items(order_id)
    try:
        from invoice_parser import InvoiceParseError, combine_invoice_with_order_items
    except ImportError:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from invoice_parser import InvoiceParseError, combine_invoice_with_order_items

    try:
        data = combine_invoice_with_order_items(
            args.invoice_pdf,
            payload,
            min_confidence=args.min_confidence,
        )
    except InvoiceParseError as exc:
        die(str(exc), 2)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    summary = data["summary"]
    print(
        f"{summary['matched']}/{summary['invoice_items']} invoice item(s) matched "
        f"to {summary['order_products']} past-order product(s)"
    )
    print(
        f"Unmatched invoice items: {summary['unmatched_invoice_items']}; "
        f"ambiguous matches: {summary['ambiguous']}"
    )
    for item in data["items"]:
        sku = item.get("sku") or "UNMATCHED"
        confidence_label = f"{float(item.get('match_confidence') or 0):.1%}"
        warning = " ambiguous" if item.get("match_ambiguous") else ""
        print(
            f"  ref {item['ref']:>3}  {sku:<10}  {confidence_label}{warning}  "
            f"{item['invoice_description']}"
        )


def cmd_favourites(args: argparse.Namespace) -> None:
    data = account_api(
        "GET",
        "/shoppers/my/favourites",
        params={
            "page": args.page,
            "size": args.limit,
            "sort": args.sort,
            "inStockProductsOnly": str(bool(args.in_stock_only)).lower(),
        },
    )
    emit_json_or_summary(data, args.json, "favourites")


def cmd_lists(args: argparse.Namespace) -> None:
    data = account_api("GET", "/shoppers/my/saved-lists")
    emit_json_or_summary(data, args.json, "saved lists")


def cmd_list_detail(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api(
        "GET",
        f"/shoppers/my/saved-lists/{list_id}/items",
        params={"page": args.page, "size": args.limit, "sort": args.sort},
    )
    emit_json_or_summary(data, args.json, "list items")


LIST_CREATE_SOURCES = {
    "empty": "Unspecified",
    "trolley": "Trolley",
    "favourites": "FavouritesAllItems",
    "list": "MySavedList",
    "order": "PastOrders",
    "all-orders": "PastOrdersMasterAllItems",
}


def list_create_payload(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "listName": args.name,
        "addFromListSource": LIST_CREATE_SOURCES[args.source],
    }
    if args.source_id:
        body["sourceListId"] = args.source_id
    if args.source in {"list", "order"} and not args.source_id:
        die(f"list-create --source {args.source} requires --source-id", 2)
    return body


def cmd_list_create(args: argparse.Namespace) -> None:
    data = account_api("POST", "/shoppers/my/saved-lists", list_create_payload(args))
    emit_json_or_summary(data, args.json, "list created")


def cmd_list_delete(args: argparse.Namespace) -> None:
    if not args.yes:
        die("list-delete is destructive; repeat with --yes to confirm", 2)
    list_id = urllib.parse.quote(args.list_id, safe="")
    data = account_api("DELETE", f"/shoppers/my/saved-lists/{list_id}")
    emit_json_or_summary(data, args.json, "list deleted")


def list_item_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {"itemsToAdd": [{"sku": str(args.sku), "quantity": args.quantity}]}


def cmd_list_add(args: argparse.Namespace) -> None:
    list_id = urllib.parse.quote(args.list_id, safe="")
    sku = urllib.parse.quote(args.sku, safe="")
    data = account_api(
        "POST",
        f"/shoppers/my/saved-lists/{list_id}/items/{sku}",
        list_item_payload(args),
    )
    emit_json_or_summary(data, args.json, "list item saved")


def cmd_list_remove(args: argparse.Namespace) -> None:
    if not args.yes:
        die("list-remove is destructive; repeat with --yes to confirm", 2)
    list_id = urllib.parse.quote(args.list_id, safe="")
    sku = urllib.parse.quote(args.sku, safe="")
    data = account_api("DELETE", f"/shoppers/my/saved-lists/{list_id}/items/{sku}")
    emit_json_or_summary(data, args.json, "list item removed")


def cart_products(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("sku") and (
                "quantity" in value
                or "quantityInTrolley" in value
                or isinstance(value.get("item"), dict)
            ):
                found.append(value)
            for nested_value in value.values():
                walk(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                walk(nested_value)

    walk(data)
    unique: dict[str, dict[str, Any]] = {}
    for item in found:
        unique.setdefault(str(item.get("sku")), item)
    return list(unique.values())


def cart_item_quantity(item: dict[str, Any]) -> float:
    value = first_value(item, "quantity", "quantityInTrolley", "purchasingQuantity")
    if isinstance(value, dict):
        value = first_value(value, "value", "quantity")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def cart_payload(sku: str, quantity: int | float, unit: str) -> dict[str, Any]:
    if unit == "Each" and float(quantity) != int(float(quantity)):
        die("Each quantities must be whole numbers; use --unit Kg for a weight", 2)
    return {"sku": str(sku), "quantity": quantity, "pricingUnit": unit}


def cmd_cart(args: argparse.Namespace) -> None:
    data = account_api("GET", "/trolleys/my")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    products = cart_products(data)
    print(f"{len(products)} trolley product(s)")
    for item in products:
        name = first_value(item, "name", "productName")
        if not name and isinstance(item.get("item"), dict):
            name = first_value(item["item"], "name", "productName")
        print(f"  {item.get('sku')}  {name or ''}  qty {cart_item_quantity(item):g}".rstrip())


def cmd_cart_add(args: argparse.Namespace) -> None:
    current = account_api("GET", "/trolleys/my")
    existing = 0.0
    for item in cart_products(current):
        if str(item.get("sku")) == str(args.sku):
            existing = cart_item_quantity(item)
            break
    target = existing + float(args.quantity)
    if target.is_integer():
        target = int(target)
    data = account_api(
        "POST",
        "/trolleys/my/items",
        cart_payload(args.sku, target, args.unit),
    )
    emit_json_or_summary(data, args.json, "trolley item added")


def cmd_cart_update(args: argparse.Namespace) -> None:
    data = account_api(
        "POST",
        "/trolleys/my/items",
        cart_payload(args.sku, args.quantity, args.unit),
    )
    emit_json_or_summary(data, args.json, "trolley item updated")


def cmd_cart_remove(args: argparse.Namespace) -> None:
    if not args.yes:
        die("cart-remove is destructive; repeat with --yes to confirm", 2)
    data = account_api(
        "POST",
        "/trolleys/my/items",
        cart_payload(args.sku, 0, args.unit),
    )
    emit_json_or_summary(data, args.json, "trolley item removed")


def cmd_cart_clear(args: argparse.Namespace) -> None:
    if not args.yes:
        die("cart-clear is destructive; repeat with --yes to confirm", 2)
    data = account_api("DELETE", "/trolleys/my/items")
    emit_json_or_summary(data, args.json, "trolley cleared")


def build_parser(include_account: bool | None = None) -> argparse.ArgumentParser:
    if include_account is None:
        include_account = account_commands_enabled()
    description = (
        "Woolworths NZ product lookup, personal orders, saved lists, and trolley CLI."
        if include_account
        else "Lightweight Woolworths NZ product lookup CLI (public endpoints; no login required)."
    )
    ap = argparse.ArgumentParser(description=description)
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="search products")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--size", help="filter returned products by size text, e.g. 2L")
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("specials", help="list specials, optionally filtered by query")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_specials)

    sp = sub.add_parser("browse", help="browse a numeric Woolworths category id")
    sp.add_argument("category_id", help="numeric category id from Woolworths breadcrumb/category data")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_browse)

    sp = sub.add_parser("product", help="fetch one or more product SKUs")
    sp.add_argument("skus", nargs="+")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    if not include_account:
        return ap

    sp = sub.add_parser("auth", help="manage the local Woolworths browser session")
    auth_sub = sp.add_subparsers(dest="auth_command", required=True)
    auth_login = auth_sub.add_parser("login", help="sign in and cache a reusable browser session")
    auth_login.add_argument("--headed", action="store_true", help="show the login browser")
    auth_login.set_defaults(func=cmd_auth_login)
    auth_status = auth_sub.add_parser("status", help="validate the cached session")
    auth_status.add_argument("--json", action="store_true")
    auth_status.set_defaults(func=cmd_auth_status)
    auth_logout = auth_sub.add_parser("logout", help="remove only the local session cache")
    auth_logout.set_defaults(func=cmd_auth_logout)

    sp = sub.add_parser("orders", help="list personal past orders")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--date-filter", help="server date filter, e.g. 180")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_orders)

    sp = sub.add_parser("order", help="fetch one personal past order")
    sp.add_argument("order_id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_order)

    sp = sub.add_parser("order-items", help="list items from a past order, or all past orders")
    sp.add_argument("order_id", help="order id or 'all'")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--limit", type=int, default=48)
    sp.add_argument("--sort")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_order_items)

    sp = sub.add_parser(
        "invoice-items",
        help="join a tax-invoice PDF to past-order products and SKUs",
    )
    sp.add_argument("order_id", help="order id for the invoice")
    sp.add_argument("invoice_pdf", help="local Woolworths tax-invoice PDF")
    sp.add_argument(
        "--min-confidence",
        type=confidence,
        default=0.72,
        help="minimum name-match confidence from 0 to 1 (default: 0.72)",
    )
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_invoice_items)

    sp = sub.add_parser("favourites", help="list personal Woolworths favourites")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--limit", type=int, default=48)
    sp.add_argument("--sort")
    sp.add_argument("--in-stock-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_favourites)

    sp = sub.add_parser("lists", help="list personal saved lists")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_lists)

    sp = sub.add_parser("list", help="read the products in one saved list")
    sp.add_argument("list_id")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--limit", type=int, default=48)
    sp.add_argument("--sort")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_detail)

    sp = sub.add_parser("list-create", help="create a personal saved list")
    sp.add_argument("name", type=nonempty_name)
    sp.add_argument("--source", choices=sorted(LIST_CREATE_SOURCES), default="empty")
    sp.add_argument("--source-id", help="existing list or order id for the selected source")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_create)

    sp = sub.add_parser("list-delete", help="permanently delete a personal saved list")
    sp.add_argument("list_id")
    sp.add_argument("--yes", action="store_true", help="confirm permanent deletion")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_delete)

    for command, help_text in (
        ("list-add", "add a product to a personal saved list"),
        ("list-update", "set a saved-list product quantity"),
    ):
        sp = sub.add_parser(command, help=help_text)
        sp.add_argument("list_id")
        sp.add_argument("sku")
        sp.add_argument("--quantity", type=positive_quantity, default=1)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=cmd_list_add)

    sp = sub.add_parser("list-remove", help="remove a product from a personal saved list")
    sp.add_argument("list_id")
    sp.add_argument("sku")
    sp.add_argument("--yes", action="store_true", help="confirm item removal")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_remove)

    sp = sub.add_parser("cart", help="show the current personal trolley")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cart)

    for command, help_text, func in (
        ("cart-add", "increment a product quantity in the trolley", cmd_cart_add),
        ("cart-update", "set a product quantity in the trolley", cmd_cart_update),
    ):
        sp = sub.add_parser(command, help=help_text)
        sp.add_argument("sku")
        sp.add_argument("--quantity", type=positive_quantity, default=1)
        sp.add_argument("--unit", choices=("Each", "Kg"), default="Each")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=func)

    sp = sub.add_parser("cart-remove", help="remove a product from the trolley")
    sp.add_argument("sku")
    sp.add_argument("--unit", choices=("Each", "Kg"), default="Each")
    sp.add_argument("--yes", action="store_true", help="confirm item removal")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cart_remove)

    sp = sub.add_parser("cart-clear", help="remove every product from the trolley")
    sp.add_argument("--yes", action="store_true", help="confirm clearing the trolley")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_cart_clear)
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
