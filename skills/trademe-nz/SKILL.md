---
name: trademe-nz
description: "Query Trade Me NZ public listings: marketplace, property sale/rental, motors, jobs, flatmates, rural, retirement, regions, categories, and listing details. No login or credentials required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Trade Me"
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
  thecolab.source_url: "https://www.trademe.co.nz"
  thecolab.allowed_domains: "api.trademe.co.nz,www.trademe.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Trade Me NZ

## Goal

Query live public Trade Me NZ listing data through a lightweight deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks to search Trade Me marketplace listings
- A user wants property sale/rental scans or open market snapshots
- A user wants used-car, job, flatmate, rural, retirement, or commercial listing searches
- A user has a Trade Me listing id and wants public details
- A workflow needs machine-readable Trade Me public listing data

## Do not use this for

- Bidding, buying, selling, listing creation, watchlists, saved searches, or account actions
- Authenticated/private Trade Me data
- High-volume scraping or dataset redistribution
- Price-history claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py search` with the narrowest `--type` that answers the task
2. Use `--region` for location-scoped searches; names like `auckland` are mapped to common ids
3. Use `--price-min`, `--price-max`, and bedroom flags where relevant
4. Use `listing <id>` for public detail after selecting a result
5. Use `regions` and `categories` to discover ids
6. Use `--json` for agent chaining, alerts, comparisons, or structured reports

## CLI

Run with:

```bash
python3 skills/trademe-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search [query] --type marketplace|property-sale|property-rent|motors|jobs|flatmates|commercial-sale|commercial-lease|rural|retirement [--region id/name] [--price-min N] [--price-max N] [--bedrooms-min N] [--bedrooms-max N] [--limit N] [--page N] [--json]`
- `listing <listing-id> [--json] [--raw]` — fetch public listing details
- `regions [--json]` — list Trade Me region ids
- `categories [--query text] [--depth N] [--limit N] [--json]` — list/search public category tree

Examples:

```bash
python3 skills/trademe-nz/scripts/cli.py search iphone --limit 5
python3 skills/trademe-nz/scripts/cli.py search auckland --type property-rent --region auckland --bedrooms-min 2 --price-max 800 --json
python3 skills/trademe-nz/scripts/cli.py search aqua --type motors --region auckland --price-max 15000 --json
python3 skills/trademe-nz/scripts/cli.py search developer --type jobs --region auckland --json
python3 skills/trademe-nz/scripts/cli.py listing 5945835894 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, OAuth app credentials, username, password, cookie, or browser automation is required for supported read-only commands
- The old uppercase `.json` API paths may require application credentials; this skill uses the lowercase endpoints used by the modern website
- Treat results as live snapshots; listings can disappear, sell, close, or change without notice
- Keep usage narrow and respectful
