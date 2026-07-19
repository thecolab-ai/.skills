---
name: kmart
description: "Query Kmart NZ and AU product search, prices, SKU lookup, clearance/promotional snapshots, and store-location data. Read-only; no login, cart, checkout, or account actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "Kmart"
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
  thecolab.source_url: "https://ac.cnstrc.com"
  thecolab.allowed_domains: "ac.cnstrc.com,www.kmart.co.nz,www.kmart.com.au,www.sitemaps.org"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Kmart

## Goal

Query live Kmart NZ and AU public product data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Kmart NZ or AU product prices
- A user wants to search Kmart products by keyword
- A user has Kmart SKUs and wants product details
- A user wants a lightweight clearance or promotional product snapshot
- A user needs public Kmart store-location URLs from the site sitemaps
- A workflow needs fast read-only Kmart data for comparisons or reports

## Do not use this for

- Authenticated account, OnePass, personalised, cart, checkout, delivery-slot, payment, order, or review actions
- High-volume scraping or redistributing scraped Kmart product data as a dataset
- Historical pricing or price-change claims unless another dataset provides history
- Canonical store trading-hour or stock-availability claims; verify store pages or official locator output before publishing

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Default to NZ unless the user asks for AU; pass `--country au` for Australia
3. Use `search` for keyword product lookup and `product` when an exact SKU is known
4. Use `specials` for a clearance/promotional snapshot based on product metadata
5. Use `stores` for public store-detail URL discovery from Kmart sitemaps
6. Use `--json` for agent chaining, comparisons, or structured reports
7. Mention that prices and specials are live online Kmart snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/kmart/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--country nz|au] [--limit N] [--page N] [--json]` — product search with prices
- `product <sku> [--country nz|au] [--json]` — fetch exact SKU details via product search metadata
- `stores [--region text] [--country nz|au] [--limit N] [--json]` — list store-detail URLs and public store metadata
- `specials [query] [--country nz|au] [--limit N] [--page N] [--json]` — clearance/promotional products inferred from product metadata

Examples:

```bash
python3 skills/kmart/scripts/cli.py search lego --limit 10
python3 skills/kmart/scripts/cli.py search "air fryer" --country au --limit 5 --json
python3 skills/kmart/scripts/cli.py product 43684687 --json
python3 skills/kmart/scripts/cli.py specials sale --limit 10 --json
python3 skills/kmart/scripts/cli.py stores --country au --region melbourne --limit 5 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, or browser automation is required for the implemented read-only operations
- Product search and SKU lookup use the public Constructor.io search endpoints configured by the Kmart web app
- AU store discovery uses the public Kmart XML sitemap. NZ store discovery uses official store-detail pages because the NZ store sitemap currently returns AU locations.
- Specials are a best-effort live snapshot from public product metadata such as clearance badges, sale badges, save-price text, and non-list price types
- Endpoint shapes can change; verify with a small live query before relying on large workflows
