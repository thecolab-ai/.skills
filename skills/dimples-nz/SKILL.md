---
name: dimples-nz
description: "Query Dimples NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-locator page. Use when comparing Dimples products, looking up a product handle or URL, or finding official Dimples Auckland and Christchurch store information. Read-only; no cart, checkout, account, payment, booking, or other mutations."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Dimples"
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
  thecolab.source_url: "https://www.dimples.co.nz/"
  thecolab.allowed_domains: "babyonthemove.co.nz,www.babycity.co.nz,www.dimples.co.nz,www.naturebaby.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Dimples NZ

Use this skill for narrow, live lookups against Dimples NZ's public storefront.

## Workflow

1. Use `search` to discover products by keyword.
2. Use the returned handle with `product` for variants and exact product detail.
3. Use `stores` to retrieve the verified official store-locator page.
4. Prefer `--json` for comparisons and agent workflows.
5. Cite `source_url` and `retrieved_at`; describe prices as current snapshots.

## CLI

```bash
python3 skills/dimples-nz/scripts/cli.py search "merino" --limit 5 --json
python3 skills/dimples-nz/scripts/cli.py product smart-dri-cot-protector-2 --json
python3 skills/dimples-nz/scripts/cli.py stores --json
```

Commands:

- `search <query> [--limit 1..10] [--timeout 1..30] [--json]`
- `product <handle-or-product-url> [--timeout 1..30] [--json]`
- `stores [--timeout 1..30] [--json]`

Network timeout defaults to 10 seconds. Search is bounded to 10 predictive-search results. Availability means the online storefront state only, never physical store stock.

## Boundaries

Only public HTTPS GET requests are implemented. Do not use this skill for carts, checkout, accounts, payments, orders, prescriptions, bookings, hire, or mutations. Do not claim historical pricing or physical-store inventory.

## Resources

- CLI: `scripts/cli.py`
- Live outage-tolerant checks: `scripts/smoke_test.py`
- Endpoints and response notes: `references/api-notes.md`
