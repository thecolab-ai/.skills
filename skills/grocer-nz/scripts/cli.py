#!/usr/bin/env python3
"""CLI for public grocer.nz supermarket price data.

Uses Grocer's public static DuckDB/parquet assets plus its public frontend
Meilisearch search key. Dependencies are bootstrapped via uv when absent.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

duckdb = None


def ensure_dependencies() -> None:
    """Load optional data dependencies only when a data command needs them."""
    global duckdb
    if duckdb is not None:
        return
    try:
        import duckdb as loaded_duckdb  # type: ignore
        import pytz  # type: ignore  # noqa: F401
    except Exception:
        if os.environ.get("GROCER_NZ_BOOTSTRAPPED") != "1" and shutil.which("uv"):
            env = os.environ.copy()
            env["GROCER_NZ_BOOTSTRAPPED"] = "1"
            os.execvpe(
                "uv",
                ["uv", "run", "--quiet", "--with", "duckdb", "--with", "pytz", "python", __file__, *sys.argv[1:]],
                env,
            )
        raise RuntimeError("grocer-nz requires duckdb and pytz; install them or run with uv")
    duckdb = loaded_duckdb

BASE = "https://assets-prod.grocer.nz/public"
MEILI = "https://meilisearch.grocer.nz"
# Public read-only search key shipped to every grocer.nz browser client.
MEILI_KEY = "7f58239330307ec585c86863f985ab83cbb9ce951a9601c66e158548fb632fd1"
ALLOWED_HOSTS = {"assets-prod.grocer.nz", "grocer.nz", "meilisearch.grocer.nz"}
CACHE = pathlib.Path(os.environ.get("GROCER_NZ_CACHE", "~/.cache/grocer-nz")).expanduser()
HEADERS = {"Referer": "https://grocer.nz/"}
MAX_LIMIT = 100


def http_get(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    body, _content_type, _final_url = nzfetch.fetch_bytes(
        url,
        timeout=120,
        headers={**HEADERS, **(headers or {})},
        allowed_hosts=ALLOWED_HOSTS,
    )
    return body


def http_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    return nzfetch.fetch_json(
        url,
        timeout=60,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **HEADERS, **(headers or {})},
        allowed_hosts={"meilisearch.grocer.nz"},
    )


def _is_missing(err: nzfetch.FetchError) -> bool:
    """True when a fetch failed with an HTTP 403/404 — grocer treats a missing or
    forbidden per-store/per-product asset as 'no file' (returns None), matching the
    original urllib.error.HTTPError code check."""
    msg = str(err)
    return "HTTP 403" in msg or "HTTP 404" in msg


def download(url: str, path: pathlib.Path, *, force: bool = False) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if force or not path.exists() or path.stat().st_size == 0:
        path.write_bytes(http_get(url))
    return path


def base_db(force: bool = False) -> pathlib.Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    # Despite the .br suffix, CDN responses are often transparently decoded.
    return download(f"{BASE}/base_v3.duckdb.br", CACHE / "base_v3.duckdb", force=force)


def price_file(store_id: int, force: bool = False) -> pathlib.Path | None:
    path = CACHE / "prices_per_store_v3" / f"public_prices_{store_id}.parquet"
    try:
        return download(f"{BASE}/prices_per_store_v3/public_prices_{store_id}.parquet", path, force=force)
    except nzfetch.FetchError as e:
        if _is_missing(e):
            return None
        raise


def history_file(product_id: int, force: bool = False) -> pathlib.Path | None:
    path = CACHE / "price_history_v3" / f"price_history_{product_id}.parquet"
    try:
        return download(f"{BASE}/price_history_v3/price_history_{product_id}.parquet", path, force=force)
    except nzfetch.FetchError as e:
        if _is_missing(e):
            return None
        raise


def con(force: bool = False):
    ensure_dependencies()
    db = base_db(force=force)
    c = duckdb.connect(":memory:")
    sql = "attach " + sql_quote_path(db) + " as base (READ_ONLY)"
    c.execute(sql)
    return c


def rows_to_dicts(cur) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    out = []
    for row in cur.fetchall():
        item = {}
        for k, v in zip(cols, row):
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            item[k] = v
        out.append(item)
    return out


def cents(v: Any) -> str:
    return "-" if v is None else f"${int(v)/100:.2f}"


def effective_expr(alias: str = "pr") -> str:
    return f"least(coalesce({alias}.sale_price_cent, 999999999), coalesce({alias}.club_price_cent, 999999999), coalesce({alias}.online_price_cent, 999999999), coalesce({alias}.original_price_cent, 999999999))"


def bounded_limit(value: int) -> int:
    return max(1, min(int(value), MAX_LIMIT))


def bounded_offset(value: int) -> int:
    return max(0, int(value))


def normalize_gtin(value: Any) -> str:
    """Return a digits-only GTIN padded to the Grocer catalogue's GTIN-14 shape."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits or len(digits) > 14:
        return ""
    return digits.zfill(14)


def retailer_barcode(value: Any) -> str:
    """Return the compact barcode form accepted by retailer product search."""
    gtin = normalize_gtin(value)
    return gtin.lstrip("0") or "0" if gtin else ""


def meili_filter_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def print_result(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    elif isinstance(data, list):
        for item in data:
            print(" | ".join(f"{k}={v}" for k, v in item.items()))
    else:
        print(data)


def cmd_stores(args):
    c = con(force=args.refresh)
    where = ["s.is_enabled = true"] if not args.include_disabled else []
    params: list[Any] = []
    if args.query:
        where.append("lower(s.name) like ?")
        params.append(f"%{args.query.lower()}%")
    if args.vendor:
        where.append("lower(v.name) like ?")
        params.append(f"%{args.vendor.lower()}%")
    sql = """
      select s.id, v.name as vendor, s.name, s.is_enabled
      from base.public_stores s
      left join base.public_vendors v on v.id = s.vendor_id
    """
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by v.name, s.name limit ?"
    params.append(args.limit)
    rows = rows_to_dicts(c.execute(sql, params))
    print_result(rows, args.json)


def resolve_store_ids(c, store_ids: list[int], store_query: str | None) -> list[int]:
    ids = list(dict.fromkeys(store_ids))
    if store_query:
        rows = c.execute(
            "select id from base.public_stores where is_enabled=true and lower(name) like ? order by name",
            [f"%{store_query.lower()}%"],
        ).fetchall()
        ids.extend(int(r[0]) for r in rows)
    return list(dict.fromkeys(ids))


def meili_search(term: str, limit: int, offset: int, store_ids: list[int] | None = None, category: str = "") -> dict[str, Any]:
    filters = []
    limit = bounded_limit(limit)
    offset = bounded_offset(offset)
    if store_ids:
        filters.append(f"stores IN [ {', '.join(map(str, store_ids))} ]")
    if category:
        level = len(category.split(" > "))
        filters.append(f'categories.level_{level} = "{meili_filter_string(category)}"')
    payload = {
        "q": term,
        "limit": limit,
        "offset": offset,
        "filter": filters,
        "attributesToRetrieve": ["id", "name", "brand", "size", "unit", "categories", "stores"],
    }
    return http_json(f"{MEILI}/indexes/products/search", payload, headers={"Authorization": f"Bearer {MEILI_KEY}"})


def sql_quote_path(path: pathlib.Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def attach_price_views(c, store_ids: list[int], refresh: bool = False) -> list[int]:
    ok = []
    for sid in store_ids:
        p = price_file(sid, force=refresh)
        if not p:
            continue
        sql = "create or replace view prices_{} as select * from read_parquet({})".format(
            sid, sql_quote_path(p)
        )
        c.execute(sql)
        ok.append(sid)
    return ok


def barcodes_for_product_ids(c, product_ids: list[int]) -> dict[int, list[str]]:
    ids = list(dict.fromkeys(int(pid) for pid in product_ids))
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = c.execute(
        f"""
        select distinct product_id, barcode
        from base.public_barcodes
        where product_id in ({placeholders})
        order by product_id, barcode
        """,
        ids,
    ).fetchall()
    result: dict[int, list[str]] = {}
    for product_id, barcode in rows:
        gtin = normalize_gtin(barcode)
        if gtin:
            result.setdefault(int(product_id), []).append(gtin)
    return result


def decorate_barcodes(c, products: list[dict[str, Any]], id_key: str = "id") -> None:
    ids = [int(product[id_key]) for product in products if product.get(id_key) is not None]
    by_product = barcodes_for_product_ids(c, ids)
    for product in products:
        product_id = product.get(id_key)
        barcodes = by_product.get(int(product_id), []) if product_id is not None else []
        product["barcodes"] = barcodes
        product["retailer_search_terms"] = list(
            dict.fromkeys(term for term in map(retailer_barcode, barcodes) if term)
        )


def cmd_search(args):
    c = con(force=args.refresh)
    store_ids = resolve_store_ids(c, args.store_id or [], args.store_query)
    result = meili_search(args.term, args.limit, args.offset, store_ids or None, args.category or "")
    hits = result.get("hits", [])
    ids = [int(h["id"]) for h in hits]
    decorate_barcodes(c, hits)
    if store_ids and ids:
        ok = attach_price_views(c, store_ids, refresh=args.refresh)
        if ok:
            union = " union all ".join([f"select * from prices_{sid}" for sid in ok])
            placeholders = ",".join(["?"] * len(ids))
            sql = """
              with price_union as ({union})
              select p.id as product_id, s.id as store_id, s.name as store_name,
                     pr.updated_at, pr.original_price_cent, pr.sale_price_cent, pr.club_price_cent,
                     pr.online_price_cent, pr.multibuy_price_cent, pr.multibuy_quantity,
                     {effective_price} as effective_price_cent
              from price_union pr
              join base.public_products p on p.id = pr.product_id
              join base.public_stores s on s.id = pr.store_id
              where p.id in ({placeholders})
              order by p.id, effective_price_cent, s.name
            """.format(union=union, effective_price=effective_expr(), placeholders=placeholders)
            price_rows = rows_to_dicts(c.execute(sql, ids))
            by_pid: dict[int, list[dict[str, Any]]] = {}
            for r in price_rows:
                by_pid.setdefault(int(r["product_id"]), []).append(r)
            for h in hits:
                h["prices"] = by_pid.get(int(h["id"]), [])
    # The Meilisearch document carries a full `stores` array (every store id that
    # stocks the product — often hundreds). Replace it with a count to keep the
    # payload lean and well under the MCP output cap.
    for h in hits:
        if "stores" in h:
            h["store_count"] = len(h["stores"]) if isinstance(h["stores"], list) else None
            del h["stores"]
    if args.json:
        print_result({"estimatedTotalHits": result.get("estimatedTotalHits"), "hits": hits}, True)
    else:
        print(f"estimatedTotalHits={result.get('estimatedTotalHits')}")
        for h in hits:
            label = " ".join(str(x) for x in [h.get("brand"), h.get("name"), h.get("size")] if x)
            print(f"{h['id']} | {label}")
            if h.get("barcodes"):
                print(
                    "  GTIN "
                    + ", ".join(h["barcodes"])
                    + " | retailer search "
                    + ", ".join(h["retailer_search_terms"])
                )
            for p in h.get("prices", [])[:10]:
                print(f"  {p['store_name']}: eff {cents(p['effective_price_cent'])} orig {cents(p['original_price_cent'])} sale {cents(p['sale_price_cent'])} club {cents(p['club_price_cent'])} updated {p['updated_at']}")


def cmd_barcode(args):
    gtin = normalize_gtin(args.barcode)
    if not gtin:
        raise SystemExit("barcode: expected a numeric barcode no longer than 14 digits")
    c = con(force=args.refresh)
    rows = rows_to_dicts(c.execute(
        """
        select distinct p.id as product_id, p.brand, p.name, p.unit, p.size, p.redirected_to
        from base.public_barcodes b
        join base.public_products p on p.id=b.product_id
        where b.barcode=?
        order by p.id
        """,
        [gtin],
    ))
    decorate_barcodes(c, rows, id_key="product_id")
    if args.json:
        print_result(
            {
                "query_barcode": str(args.barcode),
                "gtin": gtin,
                "matches": rows,
            },
            True,
        )
        return
    if not rows:
        print(f"No Grocer product found for GTIN {gtin}")
        return
    for row in rows:
        label = " ".join(
            str(value)
            for value in (row.get("brand"), row.get("name"), row.get("size"))
            if value
        )
        print(
            f"{row['product_id']} | {label} | GTIN {gtin} | "
            f"retailer search {', '.join(row['retailer_search_terms'])}"
        )


def cmd_prices(args):
    c = con(force=args.refresh)
    store_ids = resolve_store_ids(c, args.store_id or [], args.store_query)
    if args.all_stores or not store_ids:
        store_ids = [int(r[0]) for r in c.execute("select id from base.public_stores where is_enabled=true order by id").fetchall()]
    ok = attach_price_views(c, store_ids, refresh=args.refresh)
    if not ok:
        print_result([], args.json)
        return
    union = " union all ".join([f"select * from prices_{sid}" for sid in ok])
    sql = """
      with price_union as ({union})
      select p.id as product_id, p.brand, p.name, p.size, s.id as store_id, s.name as store_name,
             pr.updated_at, pr.original_price_cent, pr.sale_price_cent, pr.club_price_cent,
             pr.online_price_cent, pr.multibuy_price_cent, pr.multibuy_quantity,
             {effective_price} as effective_price_cent
      from price_union pr
      join base.public_products p on p.id=pr.product_id
      join base.public_stores s on s.id=pr.store_id
      where p.id=?
      order by effective_price_cent, s.name
      limit ?
    """.format(union=union, effective_price=effective_expr())
    rows = rows_to_dicts(c.execute(sql, [args.product_id, args.limit]))
    if args.json:
        print_result(rows, True)
    else:
        for r in rows:
            print(f"{r['store_name']}: eff {cents(r['effective_price_cent'])} orig {cents(r['original_price_cent'])} sale {cents(r['sale_price_cent'])} club {cents(r['club_price_cent'])} updated {r['updated_at']}")


def cmd_history(args):
    c = con(force=args.refresh)
    p = history_file(args.product_id, force=args.refresh)
    if not p:
        print_result([], args.json)
        return
    sql = "create or replace view hist as select * from read_parquet({})".format(
        sql_quote_path(p)
    )
    c.execute(sql)
    where = []
    params: list[Any] = []
    ids = resolve_store_ids(c, args.store_id or [], args.store_query)
    if ids:
        where.append("h.store_id in (" + ",".join(["?"] * len(ids)) + ")")
        params.extend(ids)
    where_sql = "where " + " and ".join(where) if where else ""
    sql = """
      select h.updated_at, h.store_id, s.vendor_id, s.name as store_name, h.price_cent
      from hist h
      left join base.public_stores s on s.id=h.store_id
      {where_sql}
      order by h.updated_at desc, s.name
      limit ?
    """.format(where_sql=where_sql)
    rows = rows_to_dicts(c.execute(sql, [*params, args.limit]))
    if args.json:
        print_result(rows, True)
    else:
        for r in rows:
            print(f"{r['updated_at']} | {r['store_name'] or r['store_id']} | {cents(r['price_cent'])}")


# ── Guarded read-only SQL (`query`) ───────────────────────────────────────────
# Lets callers run ad-hoc analysis over the grocer dataset. Safety model:
#   * statement must be a single SELECT / WITH (no ';', no DDL/DML)
#   * filesystem + network reads are blocked (enable_external_access=false) and
#     the config is locked (lock_configuration=true) AFTER our own parquet loads
#   * base catalogue is attached READ_ONLY; results are row-capped
# Net effect: an arbitrary query can only read the public grocery data we expose
# — it cannot write, read other files, reach the network, or change settings.
QUERY_ROW_CAP = 5000

# File/network reader functions. enable_external_access=false already blocks
# these at runtime; rejecting them up front gives a clearer error.
_BLOCKED_FUNCS = (
    "read_csv", "read_csv_auto", "read_parquet", "parquet_scan", "read_json",
    "read_json_auto", "read_ndjson", "read_text", "read_blob", "glob", "sniff_csv",
)


def _strip_string_literals(sql: str) -> str:
    # Replace '...' literal contents so product names like 'copy paper' don't
    # trip the keyword scan.
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_select(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise SystemExit("query: empty SQL")
    if ";" in s:
        raise SystemExit("query: only a single statement is allowed (no ';')")
    scan = _strip_string_literals(s).lower()
    if not (scan.startswith("select") or scan.startswith("with")):
        raise SystemExit("query: only SELECT / WITH statements are allowed")
    for tok in _BLOCKED_FUNCS:
        if re.search(r"\b" + re.escape(tok) + r"\b", scan):
            raise SystemExit(f"query: disallowed function '{tok}' (filesystem/network access is blocked)")
    return s


def fetch_limited(cur, limit: int) -> tuple[list[dict[str, Any]], bool]:
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    rows = cur.fetchmany(limit + 1)
    truncated = len(rows) > limit
    for row in rows[:limit]:
        item = {}
        for k, v in zip(cols, row):
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            item[k] = v
        out.append(item)
    return out, truncated


def cmd_query(args):
    statement = validate_select(args.sql)
    c = con(force=args.refresh)
    # Convenience relations over the base catalogue.
    c.execute("create view products as select * from base.public_products")
    c.execute("create view stores as select * from base.public_stores")
    c.execute("create view barcodes as select * from base.public_barcodes")
    try:
        c.execute("create view vendors as select * from base.public_vendors")
    except Exception:
        pass

    # Materialise current prices for selected stores into a `prices` table.
    loaded_stores: list[int] = []
    store_ids = resolve_store_ids(c, args.store_id or [], args.store_query)
    if args.all_stores and not store_ids:
        store_ids = [int(r[0]) for r in c.execute(
            "select id from base.public_stores where is_enabled=true order by id").fetchall()]
    price_parts = []
    for sid in store_ids:
        pth = price_file(sid, force=args.refresh)
        if not pth:
            continue
        price_parts.append("select * from read_parquet(" + sql_quote_path(pth) + ")")
        loaded_stores.append(sid)
    if price_parts:
        c.execute("create temp table prices as " + " union all ".join(price_parts))

    # Materialise price history for selected products into a `history` table.
    loaded_products: list[int] = []
    hist_parts = []
    for pid in (args.product or []):
        f = history_file(int(pid), force=args.refresh)
        if not f:
            continue
        hist_parts.append("select *, " + str(int(pid)) + " as product_id from read_parquet(" + sql_quote_path(f) + ")")
        loaded_products.append(int(pid))
    if hist_parts:
        c.execute("create temp table history as " + " union all ".join(hist_parts))

    # Lock down: no filesystem/network, no further config changes.
    c.execute("set enable_external_access=false")
    c.execute("set lock_configuration=true")

    limit = max(1, min(int(args.limit), QUERY_ROW_CAP))
    try:
        cur = c.execute(statement)
        rows, truncated = fetch_limited(cur, limit)
    except Exception as e:
        raise SystemExit("query error: " + str(e).splitlines()[0])

    relations = ["products", "barcodes", "stores", "vendors"]
    if price_parts:
        relations.append("prices")
    if hist_parts:
        relations.append("history")
    payload = {
        "row_count": len(rows),
        "truncated": truncated,
        "loaded_stores": loaded_stores,
        "loaded_products": loaded_products,
        "available_relations": relations,
        "rows": rows,
    }
    if args.json:
        print_result(payload, True)
    else:
        for r in rows:
            print(" | ".join(f"{k}={v}" for k, v in r.items()))
        if truncated:
            print(f"... truncated at {limit} rows")


def cmd_product(args):
    c = con(force=args.refresh)
    rows = rows_to_dicts(c.execute("""
      select p.*, c1.name as category_1, c2.name as category_2, c3.name as category_3
      from base.public_products p
      left join base.public_collection_members cm1 on cm1.product_id=p.id
      left join base.public_collections c1 on c1.id=cm1.collection_id and c1.is_comparable=true
      left join base.public_collections c2 on false
      left join base.public_collections c3 on false
      where p.id=?
      limit 1
    """, [args.product_id]))
    # Category joins in the app are hierarchy-derived; raw product row is the reliable bit here.
    if not rows:
        rows = rows_to_dicts(c.execute("select * from base.public_products where id=?", [args.product_id]))
    decorate_barcodes(c, rows)
    print_result(rows[0] if rows else {}, args.json)


def main(argv=None):
    p = argparse.ArgumentParser(description="Query public grocer.nz supermarket price/search/history data")
    p.add_argument("--refresh", action="store_true", help="refresh cached public files")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("stores", help="list stores")
    sp.add_argument("--query", "-q")
    sp.add_argument("--vendor")
    sp.add_argument("--include-disabled", action="store_true")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stores)

    sp = sub.add_parser("search", help="search products; optionally include current prices for selected stores")
    sp.add_argument("term")
    sp.add_argument("--store-id", type=int, action="append", default=[])
    sp.add_argument("--store-query")
    sp.add_argument("--category", default="")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--offset", type=int, default=0)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("barcode", help="resolve a UPC/EAN/GTIN to Grocer product ids")
    sp.add_argument("barcode")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_barcode)

    sp = sub.add_parser("prices", help="current prices for a product id across selected stores")
    sp.add_argument("product_id", type=int)
    sp.add_argument("--store-id", type=int, action="append", default=[])
    sp.add_argument("--store-query")
    sp.add_argument("--all-stores", action="store_true", help="download/query all enabled store price parquet files; can be slow")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_prices)

    sp = sub.add_parser("history", help="historical price rows for a product id")
    sp.add_argument("product_id", type=int)
    sp.add_argument("--store-id", type=int, action="append", default=[])
    sp.add_argument("--store-query")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("product", help="raw product metadata by id")
    sp.add_argument("product_id", type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_product)

    sp = sub.add_parser(
        "query",
        help="run a guarded read-only SELECT over the grocer dataset",
        description=(
            "Run a single read-only SELECT/WITH statement. Relations: products, "
            "barcodes, stores, vendors (always), plus prices (load with --store-id/--store-query "
            "or --all-stores) and history (load with --product). Filesystem and network "
            "access are disabled; only the public grocery data is readable."
        ),
    )
    sp.add_argument("sql", help="a single SELECT/WITH statement")
    sp.add_argument("--store-id", type=int, action="append", default=[],
                    help="load current prices for this store id into `prices` (repeatable)")
    sp.add_argument("--store-query", help="load current prices for stores matching this name into `prices`")
    sp.add_argument("--all-stores", action="store_true",
                    help="load current prices for ALL enabled stores (slow; many parquet downloads)")
    sp.add_argument("--product", type=int, action="append", default=[],
                    help="load price history for this product id into `history` (repeatable)")
    sp.add_argument("--limit", type=int, default=200, help=f"max rows returned (cap {QUERY_ROW_CAP})")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_query)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
