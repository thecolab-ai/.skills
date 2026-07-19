---
name: woolworths-nz
description: "Query Woolworths NZ product search, specials, category browse, and SKU detail. Use for Woolworths NZ grocery prices, specials, and product lookup. Read-only; no trolley or checkout actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "food-and-fuel"
  thecolab.source_owner: "Woolworths New Zealand"
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
  thecolab.source_url: "https://www.woolworths.co.nz"
  thecolab.allowed_domains: "www.woolworths.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Woolworths NZ

## Goal

Query live Woolworths NZ product data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Woolworths NZ product prices or specials
- A user wants to search Woolworths products by keyword
- A user has Woolworths SKUs and wants product details
- A user needs lightweight machine-readable Woolworths product data
- A workflow needs a fast read-only alternative to browser-driven Woolworths tooling

## Do not use this for

- Woolworths Australia or non-Woolworths retailers
- Authenticated account, Everyday Rewards, personalised, delivery-slot, trolley, checkout, or order actions
- Redistributing scraped Woolworths product data as a dataset
- Historical pricing or price-change claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword price/product lookup and `specials` for promotional products
3. Use `product` when exact SKUs are known
4. Use `browse` only when a numeric category id is known from product/category data
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that prices are live online Woolworths snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/woolworths-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--size text] [--in-stock-only] [--json]` — product search with prices
- `specials [query] [--limit N] [--page N] [--in-stock-only] [--json]` — promotional products
- `browse <category-id> [--limit N] [--page N] [--in-stock-only] [--json]` — browse a known numeric category id
- `product <sku...> [--json]` — fetch exact product SKUs

Examples:

```bash
python3 skills/woolworths-nz/scripts/cli.py search milk --limit 10
python3 skills/woolworths-nz/scripts/cli.py search "wholemeal bread" --limit 5 --json
python3 skills/woolworths-nz/scripts/cli.py specials cheese --limit 10 --json
python3 skills/woolworths-nz/scripts/cli.py product 705692 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, or browser automation is required for read-only product lookup
- This is intentionally lighter than browser/login-based Woolworths CLIs: Python stdlib only, public GET endpoints only
- Endpoint shapes can change; verify with a small live query before relying on large workflows
- The upstream inspiration repo is MIT-licensed, but this skill is a clean lightweight standalone implementation focused on public read-only product endpoints
