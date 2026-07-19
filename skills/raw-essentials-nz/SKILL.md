---
name: raw-essentials-nz
description: "Query Raw Essentials NZ public catalogue, product-page, and store-page HTML through a no-login read-only CLI. Use when a task needs current Raw Essentials product discovery or source-page detail; never for cart, checkout, account, payment, booking, or veterinary advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "retail"
  thecolab.source_owner: "Raw Essentials"
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
  thecolab.source_url: "https://rawessentials.co.nz"
  thecolab.allowed_domains: "rawessentials.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Raw Essentials NZ

Use this skill for bounded live snapshots of Raw Essentials public HTML pages. It makes unauthenticated GET requests only.

## Commands

```bash
python3 skills/raw-essentials-nz/scripts/cli.py search chicken --pet-type dog --limit 10 --json
python3 skills/raw-essentials-nz/scripts/cli.py product https://rawessentials.co.nz/product/raw-essentials-chicken-venison-mix --json
python3 skills/raw-essentials-nz/scripts/cli.py stores --json
```

- `search <query> [--pet-type dog|cat] [--page N] [--limit N] [--json]` searches one public listing page.
- `product <url> [--json]` fetches a same-site public `/product/...` page.
- `stores [--json]` extracts bounded public store-location links.
- `--timeout N` defaults to 10 seconds.

## Safety and limits

Returned prices, product text, and locations are public snapshots; include `source_url` and `retrieved_at` in downstream claims. Do not access carts, checkout, accounts, payment, subscriptions, bookings, or mutations. Raw feeding, supplements, and pet health content are source data, not veterinary or nutritional advice.

## Resources

- CLI: `scripts/cli.py`
- Live outage-tolerant smoke test: `scripts/smoke_test.py`
- Surface notes: `references/api-notes.md`
