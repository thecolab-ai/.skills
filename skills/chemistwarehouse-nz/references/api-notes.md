# Chemist Warehouse NZ API notes

Observed live on 2026-05-24. This skill is an unofficial read-only wrapper around public endpoints used by `www.chemistwarehouse.co.nz`.

## Source and auth boundary

- Website: `https://www.chemistwarehouse.co.nz/`
- API base: `https://www.chemistwarehouse.co.nz/searchapiv2`
- Auth model for implemented commands: none
- Required headers in live tests:
  - `User-Agent: Mozilla/5.0`
  - `Accept: application/json,text/plain,*/*`
  - `Referer: https://www.chemistwarehouse.co.nz/`

No username, password, account cookie, bearer token, private API key, or browser session is required for the implemented read-only operations.

Do not call or automate cart, checkout, payment, account, order, wishlist, stock reservation, prescription upload, prescription management, or any other mutating endpoint. Do not submit patient, prescription, or account data through this skill.

## Suggest endpoint

Request:

```text
GET /suggest?identifier=nz&search=panadol
```

Response shape:

- Top-level `suggestionGroups`
- `indexName: 1keywords` suggestions include `searchterm`, `nrResults`
- `indexName: 2categories` suggestions include `mlValue`, `fhLocation`, `catid`, `nrResults`
- `indexName: 3products` suggestions include `secondId`, `name`, `_thumburl`, `producturl`, `brand`, `price`, `rrp`, `ams_schedule`, `is_prescription`, `bv_star_rating`, `bv_total_votes`, `splat`

The CLI normalizes product suggestions into `items[]` and keeps grouped keyword/category/product suggestions under `groups`.

## Search endpoint

Request pattern:

```text
GET /search?identifier=nz&fh_location=//catalog01/en_AU/categories<{catalog01_chemnz}/$s=<term>&fh_start_index=<offset>&fh_view_size=<limit>
```

Response shape:

- Product listing items are under `universes.universe[0].items-section.items.item`
- Total item count is under `universes.universe[0].items-section.results.total-items`
- Product attributes are a list at `item.attribute`
- Common attribute names: `secondid`, `name`, `producturl`, `price_cw_nz`, `rrp_cw_nz`, `_thumburl`, `ams_schedule`, `is_prescription`, `bv_star_rating`, `bv_total_votes`, `l1_category`, `l2_category`, `l3_category`
- `item.link[0].url-params` usually contains a reusable detail query with `fh_secondid`

Some brand-exact or heavily merchandised terms can redirect and return no normal listing items. `vitamin c` was robust in live smoke tests.

## Category endpoint

Request pattern:

```text
GET /search?identifier=nz&fh_location=//catalog01/en_AU/categories<{catalog01_chemnz}/categories<{chemnz<ID>}&fh_start_index=<offset>&fh_view_size=<limit>
```

Category `256` returned `3376` total items in a prior live test. The CLI accepts `256`, `chemnz256`, or a full category token and normalizes digit-only IDs to `chemnz<ID>`.

## Detail endpoint

Preferred detail lookup is another `/search` request with a product second ID:

```text
GET /search?identifier=nz&site=cw_nz&channel=desktop&fh_location=//catalog01/en_AU/categories<{catalog01_chemnz}&fh_start_index=0&fh_refview=search&fh_secondid=<product_id>&fh_lister_pos=1&fh_modification=
```

The detail query can also be made by taking a search/category product item's `link[0].url-params`, appending it to `/search`, and adding `identifier=nz`.

Observed detail response notes:

- `info.view` is the string `detail`
- The detail product remains under `universes.universe[0].items-section.items.item`
- Detail attributes include `description`, `_imageurl`, `price_cw_nz`, `rrp_cw_nz`, `bv_star_rating`, `bv_total_votes`, plus the normal product fields

## CLI normalization

JSON commands include:

- `source`: `chemistwarehouse-nz-searchapiv2`
- `source_url`: exact URL called
- `query`, `category_id`, or `product_id` as applicable
- `total`: upstream total when available
- `results`: number of returned normalized items, or grouped suggestion counts for `suggest`
- `items`: normalized product records

Product records include product ID, name, brand when supplied, price, RRP, currency, URL, image/thumbnail, prescription flag, AMS schedule, Bazaarvoice rating/votes, categories, and detail URL params when provided.

## Stability and safety

- Treat prices, ratings, and product availability signals as live online snapshots.
- Store, account, prescription, or logged-in state may change what a real customer sees.
- Endpoint fields and Fredhopper query parameters are not an official public API contract and can change.
- Keep queries narrow and limits small; avoid high-volume scraping.
- Do not commit cookies, credentials, HAR files, private account data, patient data, or raw browser captures.
