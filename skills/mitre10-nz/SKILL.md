---
name: mitre10-nz
description: "Query Mitre 10 NZ product search, specials, store locator, and product detail. Use for Mitre 10 NZ product lookup, hardware prices, catalogue specials, product codes, or store locations. No cart or account."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "Mitre 10 New Zealand"
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
  thecolab.source_url: "https://www.mitre10.co.nz"
  thecolab.allowed_domains: "ccapi.mitre10.co.nz,cq00o09oxx-dsn.algolia.net,www.mitre10.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Mitre 10 NZ

## Goal

Query live Mitre 10 NZ product and store data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Mitre 10 NZ product prices or specials
- A user wants to search Mitre 10 products by keyword
- A user has Mitre 10 product codes and wants product details
- A user needs Mitre 10 store locations or contact details
- A user needs lightweight machine-readable Mitre 10 product or store data
- A workflow needs a fast read-only alternative to browser-driven Mitre 10 tooling

## Do not use this for

- Mitre 10 Australia or non-Mitre 10 retailers
- Authenticated account, Club, personalised pricing, delivery-slot, cart, checkout, order, wishlist, or quote actions
- Redistributing scraped Mitre 10 product data as a dataset
- Historical pricing or price-change claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword price/product lookup and `specials` for promotional products
3. Use `product` when exact product codes are known
4. Use `stores` for store lookup, optionally with `--region` for a city, suburb, or region query
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that prices are live online Mitre 10 snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/mitre10-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--json]` - product search with prices
- `specials [query] [--limit N] [--page N] [--json]` - promotional products
- `stores [--region text] [--limit N] [--page N] [--json]` - store locator results
- `product <code> [--json]` - fetch exact product details

Examples:

```bash
python3 skills/mitre10-nz/scripts/cli.py search drill --limit 10
python3 skills/mitre10-nz/scripts/cli.py search "circular saw" --limit 5 --json
python3 skills/mitre10-nz/scripts/cli.py specials drill --limit 10 --json
python3 skills/mitre10-nz/scripts/cli.py stores --region auckland
python3 skills/mitre10-nz/scripts/cli.py product 2030160 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Mitre 10 product search and specials use Algolia public search-only credentials embedded in the site configuration
- Product detail and stores use unauthenticated SAP Commerce OCC endpoints on `ccapi.mitre10.co.nz`
- No username, password, account cookie, private token, or browser automation is required for read-only lookup
- Endpoint shapes and public Algolia keys can change; verify with a small live query before relying on large workflows
- Do not use this skill for cart mutation, checkout, order placement, account actions, or high-volume scraping
