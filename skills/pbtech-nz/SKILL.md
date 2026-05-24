---
name: pbtech-nz
description: Query PB Tech NZ public product search, category/product pages, prices, stock summary, and store-location pages through a lightweight no-login CLI. Use when the task involves PB Tech product lookup, electronics/computer prices, part codes, availability, store pickup counts, store addresses, opening hours, or machine-readable PB Tech retail data. Read-only; no login, cart, checkout, wishlist, or account actions.
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
