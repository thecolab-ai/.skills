# grocer.nz API / asset notes

Sniffed 2026-05-31 from `https://grocer.nz/` using the browser resource list and bundled JS assets.

## Frontend assets

Main bundles observed:

- `https://grocer.nz/assets/index-D3XCRpnM.js`
- `https://grocer.nz/assets/server-DLE0sY-V.js`

The server worker bundle contains the data access layer. Important discoveries:

```text
Remote public asset base: https://assets-prod.grocer.nz/public
Meilisearch host:        https://meilisearch.grocer.nz
Meilisearch index:       products
```

The frontend search key is embedded client-side and used as a public bearer token for product search. Treat it as a public frontend key, not a secret. Do not store private tokens or user credentials in this skill.

## Static public files

Base database:

```text
https://assets-prod.grocer.nz/public/base_v3.duckdb.br
```

Despite the `.br` suffix, responses may be transparently decoded by the CDN and arrive as a DuckDB database file. The CLI saves it as `base_v3.duckdb`.

Per-store current prices:

```text
https://assets-prod.grocer.nz/public/prices_per_store_v3/public_prices_<store_id>.parquet
```

Per-product price history:

```text
https://assets-prod.grocer.nz/public/price_history_v3/price_history_<product_id>.parquet
```

## DuckDB schema from worker bundle

The app creates these public tables locally:

```sql
create table if not exists public_meta (updated_at timestamptz);

create table if not exists public_vendors (
  id integer,
  name varchar
);

create table if not exists public_stores (
  id           integer,
  vendor_id    integer,
  name         varchar,
  is_enabled   boolean
);

create table if not exists public_products (
  id             integer,
  name           varchar,
  brand          varchar,
  unit           varchar,
  size           varchar,
  redirected_to  integer
);

create table if not exists public_barcodes (
  barcode varchar,
  product_id integer
);

create table if not exists public_prices (
  updated_at               timestamptz,
  store_id                 integer,
  product_id               integer,
  original_price_cent      integer,
  sale_price_cent          integer,
  club_price_cent          integer,
  online_price_cent        integer,
  multibuy_price_cent      integer,
  multibuy_quantity        integer,
  club_multibuy_price_cent integer,
  club_multibuy_quantity   integer
);

create table if not exists public_collections (
  id            integer,
  name          varchar,
  is_comparable boolean
);

create table if not exists public_collection_members (
  collection_id integer,
  product_id    integer
);

create table if not exists public_collection_hierarchy (
  parent_id integer,
  child_id  integer
);

create table if not exists public_price_history (
  updated_at timestamptz,
  store_id integer,
  product_id integer,
  price_cent integer
);
```

Actual history parquet files are per-product and contain at least:

```text
updated_at, store_id, price_cent
```

The CLI injects the product id from the requested file path instead of expecting a `product_id` column in history parquet.

## Meilisearch search shape

Search endpoint:

```http
POST https://meilisearch.grocer.nz/indexes/products/search
Authorization: Bearer <frontend search key>
Content-Type: application/json
```

Useful payload:

```json
{
  "q": "milk",
  "limit": 10,
  "offset": 0,
  "filter": ["stores IN [ 118, 230, 307 ]"],
  "attributesToRetrieve": ["id", "name", "brand", "size", "unit", "categories", "stores"]
}
```

Search results include product ids and the store ids that carry each product, but not current prices. Current prices come from the per-store parquet files.

## Cross-retailer barcode matching

Verified live on 2026-07-24 with Anchor Blue Milk 2L:

- Grocer product id: `5452`
- Grocer canonical barcode: `00000094152210`
- Compact retailer search term: `94152210`
- Woolworths search returns SKU `282819` with barcode `94152210`
- New World and PAK'nSAVE barcode search both return Foodstuffs product id `5000527-EA-000`

Grocer's zero-padded barcode is the canonical join key. Remove left-padding zeroes when sending it to retailer search. For Woolworths, normalise each returned `barcode` back to GTIN-14 and require equality. Foodstuffs search does not echo the barcode in its decorated product response, so treat a result from the exact numeric barcode query as a barcode-query match and retain the returned Foodstuffs product id.

## Live smoke receipts

Verified live with:

```bash
python3 scripts/cli.py stores --query Papakura --json
python3 scripts/cli.py search "milk" --store-query Papakura --limit 2
python3 scripts/cli.py prices 5461 --store-query Papakura --limit 10
python3 scripts/cli.py history 5461 --store-query Papakura --limit 5
```

Observed Papakura ids:

- `118` Woolworths Papakura
- `206` Fresh Choice Papakura
- `230` PAK'nSAVE Papakura
- `307` New World Papakura

Observed product smoke:

- Product `5461` — Anchor Milk Lite 98.5% Fat Free 2L
- Current price rows returned for PAK'nSAVE Papakura, Woolworths Papakura, and New World Papakura.
- History rows returned from `price_history_v3/price_history_5461.parquet`.
