---
name: nature-baby-nz
description: Query Nature Baby NZ's public Shopify product search, product details, current online price snapshots, variant availability, and verified store-details page. Use when comparing Nature Baby products, looking up a product handle or URL, or finding official Nature Baby store information. Read-only; no cart, checkout, account, payment, booking, or other mutations.
---

# Nature Baby NZ

Use this skill for narrow, live lookups against Nature Baby NZ's public storefront.

## Workflow

1. Use `search` to discover products by keyword.
2. Use the returned handle with `product` for variants and exact product detail.
3. Use `stores` to retrieve the verified official store-details page.
4. Prefer `--json` for comparisons and agent workflows.
5. Cite `source_url` and `retrieved_at`; describe prices as current snapshots.

## CLI

```bash
python3 skills/nature-baby-nz/scripts/cli.py search "organic cotton" --limit 5 --json
python3 skills/nature-baby-nz/scripts/cli.py product cot-duvet-inner-none --json
python3 skills/nature-baby-nz/scripts/cli.py stores --json
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
