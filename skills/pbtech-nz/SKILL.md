---
name: pbtech-nz
description: "Query PB Tech NZ public product search, category/product pages, prices, stock summary, and store-location pages through a lightweight no-login CLI. Use when the task involves PB Tech product lookup, electronics/computer prices, part codes, availability, store pickup counts, store addresses, opening hours, or machine-readable PB Tech retail data. Read-only; no login, cart, checkout, wishlist, or account actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "PB Tech"
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
  thecolab.source_url: "https://www.pbtech.co.nz"
  thecolab.allowed_domains: "www.pbtech.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# PB Tech NZ

## Goal

Fetch public PB Tech product and store information without logging in or mutating carts/accounts.

## CLI

```bash
python3 skills/pbtech-nz/scripts/cli.py search ssd --limit 5
python3 skills/pbtech-nz/scripts/cli.py product HDDTGM0050 --json
python3 skills/pbtech-nz/scripts/cli.py stores --query auckland --json
```

Commands:

- `search QUERY [--limit N] [--json]` - search PB Tech and parse public product cards.
- `product CODE_OR_URL [--json]` - fetch a public product detail page by product code or PB Tech URL.
- `stores [--query TEXT] [--limit N] [--json]` - parse public PB Tech store-location cards.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
