---
name: grocer-nz
description: Query grocer.nz public NZ supermarket price data — store lookup, product search, current per-store prices, and historical product price rows from public DuckDB/parquet assets. Use for NZ grocery/supermarket pricing across Woolworths, New World, PAK'nSAVE, Fresh Choice, and related stores. Read-only; no login or private user data.
---


# Grocer.nz Public Price Data

## Overview

This skill queries public data exposed by **grocer.nz**, a New Zealand grocery price comparison app. It is useful for current supermarket price checks, per-store comparisons, and historical product price rows.

The CLI uses:

- Grocer public static assets: `https://assets-prod.grocer.nz/public/`
- Public DuckDB base database: `base_v3.duckdb.br`
- Per-store current price parquet files: `prices_per_store_v3/public_prices_<store_id>.parquet`
- Per-product history parquet files: `price_history_v3/price_history_<product_id>.parquet`
- Grocer frontend Meilisearch product index for search.

Script path:

```bash
skills/grocer-nz/scripts/cli.py
```

The script bootstraps `duckdb` via `uv` when the active Python does not already have it.

## When to Use

- Adam asks for historic supermarket pricing in NZ.
- Adam wants to compare prices across Woolworths, New World, PAK'nSAVE, Fresh Choice, Super Value, The Warehouse, etc.
- Adam wants a store id for a known store, e.g. Papakura.
- Adam wants price history for a known Grocer product id.
- Adam wants current prices for one product across selected stores.

Do **not** use this for authenticated Grocer Pro features, private user lists, or anything requiring sign-in. This skill is read-only public data only.

## Commands

Set a helper variable:

```bash
GROCER=skills/grocer-nz/scripts/cli.py
```

### List stores

```bash
python3 $GROCER stores --query Papakura
python3 $GROCER stores --vendor "PAK" --limit 20 --json
```

Useful known Papakura ids from live smoke:

- `118` — Woolworths Papakura
- `206` — Fresh Choice Papakura
- `230` — PAK'nSAVE Papakura
- `307` — New World Papakura

### Search products

Search only:

```bash
python3 $GROCER search "milk" --limit 5
```

Search plus current prices in matching stores:

```bash
python3 $GROCER search "milk" --store-query Papakura --limit 3
python3 $GROCER search "whittakers" --store-id 230 --store-id 307 --json
```

The search command returns Grocer product ids. Use those ids with `prices` and `history`.

### Current prices for a product

```bash
python3 $GROCER prices 5461 --store-query Papakura
python3 $GROCER prices 5461 --store-id 230 --store-id 307 --json
```

`--all-stores` is supported but can be slow because it downloads many per-store parquet files:

```bash
python3 $GROCER prices 5461 --all-stores --limit 30
```

### Price history for a product

```bash
python3 $GROCER history 5461 --store-query Papakura --limit 20
python3 $GROCER history 5461 --store-id 230 --json
```

History files are per product and include store-level rows when available.

### Raw product metadata

```bash
python3 $GROCER product 5461 --json
```

## Data Notes

See `references/api-notes.md` for the sniffed endpoints and file layout.

Important model fields:

- Products: `id`, `name`, `brand`, `unit`, `size`, `redirected_to`
- Stores: `id`, `vendor_id`, `name`, `is_enabled`
- Current prices: `updated_at`, `store_id`, `product_id`, `original_price_cent`, `sale_price_cent`, `club_price_cent`, `online_price_cent`, multibuy fields
- Price history: `updated_at`, `store_id`, `price_cent`

Prices are stored in **NZ cents**. `$5.50` is represented as `550`.

## Common Pitfalls

1. **No store selected = limited price context.** Product search comes from Meilisearch. Current per-store pricing requires store ids or `--store-query` so the CLI can download the relevant parquet files.
2. **`--all-stores` can be noisy/slow.** It may download hundreds of current price parquet files. Prefer targeted store ids for fast checks.
3. **The `.br` DuckDB file may arrive already decompressed.** The CLI treats Grocer's `base_v3.duckdb.br` CDN response as a DuckDB file directly because Cloudflare/Caddy often transparently decodes it.
4. **DuckDB DDL cannot use prepared parameters for `read_parquet(?)`.** Quote local parquet paths explicitly before `create view ... as select * from read_parquet('<path>')`; parameter binding works for normal `select` filters but not this statement shape.
5. **History parquet schema is leaner than the app's local table.** Per-product history files may only include `updated_at`, `store_id`, and `price_cent`; get `vendor_id` by joining `public_stores`, and infer product id from the requested history file.
6. **Historical availability varies.** Some products/stores have no history parquet or no rows for a selected store.
7. **Effective price is conservative.** The CLI reports `effective_price_cent` as the minimum of original/sale/club/online when present. Multibuy needs human interpretation because quantity matters.
8. **Live smoke tests depend on upstream stock/history.** Product `5461` and Papakura stores were live-valid when added, but upstream catalogue changes can make the smoke fail without a code bug.
9. **This is public read-only data.** Do not try to bypass sign-in or scrape private Grocer user/list/pro features.

## Verification Checklist

Run these before relying on a fresh install:

```bash
python3 $GROCER stores --query Papakura --json
python3 $GROCER search "milk" --store-query Papakura --limit 2
python3 $GROCER prices 5461 --store-query Papakura --limit 10
python3 $GROCER history 5461 --store-query Papakura --limit 5
```

Expected smoke signal: Papakura stores include Woolworths/New World/PAK'nSAVE, and product `5461` returns Anchor 2L milk pricing/history rows for at least PAK'nSAVE/New World/Woolworths Papakura when current Grocer data includes them.
