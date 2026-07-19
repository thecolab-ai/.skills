---
name: the-warehouse-nz
description: "Query The Warehouse NZ product search, specials, product detail, and store finder. Use for The Warehouse NZ product lookup, prices, specials, SKUs, store locations, or opening hours. Optional --browser mode uses CloakBrowser for public read-only page/API fetches when installed. No cart or account."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "The Warehouse Group"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "true"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.thewarehouse.co.nz"
  thecolab.allowed_domains: "www.thewarehouse.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# The Warehouse NZ

## Goal

Query live The Warehouse NZ product and store data through a small deterministic CLI with human-readable and JSON output, using direct public HTTP by default and optional CloakBrowser `--browser` mode for public read-only fetches when edge protection makes browser context useful.

## Use this when

- A user asks for The Warehouse NZ product prices or specials
- A user wants to search Warehouse products by keyword
- A user has a Warehouse SKU and wants public product details
- A user wants The Warehouse store locations, phone numbers, or current opening-hour summaries
- A workflow needs lightweight machine-readable The Warehouse product or store data

## Do not use this for

- Warehouse Stationery, Noel Leeming, TheMarket, or non-Warehouse retailers
- Authenticated account, MarketClub, personalised, wishlist, cart, checkout, order, delivery-slot, or payment actions
- Redistributing scraped Warehouse product or store data as a dataset
- Historical pricing or price-change claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword product lookup and `specials` for promotional products
3. Use `product` when an exact `R...` SKU is known
4. Use `stores --region` for region-scoped store lookups
5. Use `--browser` when CI/headless edge protection blocks direct HTTP; if CloakBrowser is missing, the CLI returns `cloakbrowser_not_installed`
6. Use `--json` for agent chaining, comparisons, alerts, or structured reports
7. Mention that prices and hours are live The Warehouse website snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/the-warehouse-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--json] [--browser]` - product search with prices
- `product <sku> [--json] [--browser]` - fetch public product details for one SKU
- `stores [--region name/code] [--json] [--browser]` - list stores, optionally scoped to a NZ region
- `specials [query] [--limit N] [--page N] [--json] [--browser]` - promotional products, optionally filtered by query

Examples:

```bash
python3 skills/the-warehouse-nz/scripts/cli.py search lego --limit 5
python3 skills/the-warehouse-nz/scripts/cli.py search "school bag" --limit 5 --json
python3 skills/the-warehouse-nz/scripts/cli.py product R3077131 --json
python3 skills/the-warehouse-nz/scripts/cli.py stores --region auckland --json
python3 skills/the-warehouse-nz/scripts/cli.py specials lego --limit 5 --json
python3 skills/the-warehouse-nz/scripts/cli.py search toys --limit 3 --json --browser
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Direct public HTTP is the default path; optional `--browser` imports CloakBrowser only when requested and uses a headless public page context for search, specials, product, and store fetches
- If `--browser --json` is requested and CloakBrowser is missing, the CLI returns `{"error": "cloakbrowser_not_installed", ...}` so agents can recommend installation
- CAPTCHA, queue, or challenge pages are treated as blocked states, not bypass targets
- No API key, username, password, account cookie, private token, cart, or checkout action is required for the implemented read-only operations
- The CLI uses public Salesforce Commerce Cloud storefront endpoints and parses server-rendered product markup where JSON product search is not exposed
- Product and store response shapes can change without notice; verify with a small live query before relying on larger workflows
- Keep usage narrow and respectful
