---
name: bunnings
description: "Query Bunnings NZ product search, prices, SKUs, store details, category browse, and redemption specials via no-login CLI. Optional --country au for Bunnings Australia. Read-only; no cart, checkout, or account actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "Bunnings"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.bunnings.co.nz"
  thecolab.allowed_domains: "authorisation.api.bunnings.co.nz,authorisation.api.bunnings.com.au,www.bunnings.co.nz,www.bunnings.com.au"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Bunnings

## Goal

Query live Bunnings NZ product, pricing, store, category, and promotion data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Bunnings NZ product prices, product details, or SKUs
- A user wants to search Bunnings products by keyword
- A user wants Bunnings store details, phone numbers, opening hours, or map links
- A user wants current Bunnings redemption/promotional offer products
- A workflow needs lightweight machine-readable Bunnings product or store data
- Bunnings AU is acceptable and the user explicitly asks for Australian results

## Do not use this for

- Cart, checkout, project list, account, login, delivery-slot, payment, order, or trade account actions
- Authenticated/private Bunnings data
- High-volume scraping or dataset redistribution
- Historical price tracking or price-change claims unless another dataset provides history
- Guaranteed local stock claims beyond the live default-store snapshot returned by the site

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword price/product lookup and `product` when an exact SKU is known
3. Use `browse` when a product category path is known
4. Use `stores --region` for location-scoped store lookup
5. Use `specials` for redemption/promotion products, optionally filtered by query
6. Use `--json` for agent chaining, comparisons, or structured reports
7. Mention that prices, stock, stores, search, and category results are live Bunnings `_apis` snapshots; redemption specials still come from public page state

## CLI

Run with:

```bash
python3 skills/bunnings/scripts/cli.py <command> [flags]
```

Set `--country au` before the subcommand for Bunnings Australia. The default is `nz`.

### Commands

- `search <query> [--limit N] [--json]` - product search with prices
- `product <sku-or-product-url> [--json]` - fetch product detail, price, default-store stock, and aisle data when present
- `browse <category-path> [--limit N] [--json]` - browse a known category path such as `tools/power-tools/drills`
- `stores [--region text] [--limit N] [--json]` - list store details, optionally filtered by region/path/name text
- `specials [query] [--limit N] [--json]` - list redemption/promotion products

Examples:

```bash
python3 skills/bunnings/scripts/cli.py search drill --limit 5
python3 skills/bunnings/scripts/cli.py product 0715241 --json
python3 skills/bunnings/scripts/cli.py browse tools/power-tools/drills --limit 5
python3 skills/bunnings/scripts/cli.py stores --region uppernorthisland --limit 5 --json
python3 skills/bunnings/scripts/cli.py specials dewalt --limit 5
python3 skills/bunnings/scripts/cli.py --country au search drill --limit 5
```

## Notes

- No username, password, account cookie, cart, checkout, or browser automation is required at runtime
- The CLI mints a short-lived cached guest bearer token through Bunnings' public guest authorize redirect flow, then calls read-only `_apis` JSON endpoints with stdlib `urllib`
- Search and browse use `POST /_apis/v1/coveo/search`
- Product detail combines `GET /_apis/v1/products/{sku}`, `GET /_apis/v2/products/{sku}/priceInfo`, `POST /_apis/v2/products/{sku}/fulfillment`, and `GET /_apis/v1/item-api/locations`
- Store lookup uses `GET /_apis/v1/stores/country/{NZ|AU}?fields=FULL`
- Redemption specials remain a public page-state fallback from `/campaign/redemption-offers`; no clean read-only `_apis` feed was found during CDP discovery
- Product prices and stock are live snapshots and may vary by store, fulfilment method, country, and time
- Endpoint shapes can change without notice because this is not an official public API
- Keep usage narrow and respectful
- See `references/api-notes.md` for detailed endpoint shapes and request patterns
