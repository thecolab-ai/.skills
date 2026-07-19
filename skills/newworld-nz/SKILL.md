---
name: newworld-nz
description: "Query New World NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves New World NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "food-and-fuel"
  thecolab.source_owner: "Foodstuffs New Zealand"
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
  thecolab.source_url: "https://www.newworld.co.nz"
  thecolab.allowed_domains: "api-prod.newworld.co.nz,www.newworld.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# New World NZ

## Goal

Query live New World NZ store and grocery product data through a small deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks for New World NZ product prices or specials
- A user wants to search New World products by keyword
- A user needs store IDs, store lookup, or category browsing
- A user has New World product IDs and wants store-specific price/details
- A workflow needs machine-readable New World product data

## Do not use this for

- PAK'nSAVE, Four Square, Woolworths, or non-New-World retailers
- Authenticated Clubcard/member-only account data
- Historical pricing or price-change claims unless another dataset provides history
- Checkout, ordering, trolley mutation, or destructive account actions

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `stores` first when the requested location is not the default store
3. Use `search` for keyword price/product lookup and `specials` for promotional products
4. Use `product` when exact product IDs are known
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that prices are store-specific and source stability is unofficial

## CLI

Run with:

```bash
python3 skills/newworld-nz/scripts/cli.py <command> [flags]
```

Default store is New World Papakura: `ef977d89-f3d8-4e8b-8a48-b895ded38646`.
Override with `--store-id <id>` or `NEWWORLD_STORE_ID`.

### Commands

- `stores [--query text] [--limit N] [--json]` — list or filter New World stores
- `categories [--store-id id] [--depth N] [--json]` — browse a store category tree
- `search <query> [--store-id id] [--limit N] [--page N] [--promo] [--json]` — product search with prices
- `specials [query] [--store-id id] [--limit N] [--page N] [--json]` — promotional products
- `product <product-id...> [--store-id id] [--json]` — decorate exact product IDs with details
- `token [--refresh] [--json]` — fetch/cache a short-lived guest token without emitting its value

Examples:

```bash
python3 skills/newworld-nz/scripts/cli.py stores --query auckland --limit 5
python3 skills/newworld-nz/scripts/cli.py search milk --limit 10
python3 skills/newworld-nz/scripts/cli.py specials cheese --limit 10 --json
python3 skills/newworld-nz/scripts/cli.py product 5201479 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key or account login required
- Uses the same guest-token flow as the public website and caches tokens under `~/.cache/newworld-cli/guest-token.json`
- Endpoint shapes can change; retry with a fresh token before assuming data is unavailable
- `--json` output is intended for exact product matching, basket comparison, and agent workflows
