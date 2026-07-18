---
name: raw-essentials-nz
description: Query Raw Essentials NZ public catalogue, product-page, and store-page HTML through a no-login read-only CLI. Use when a task needs current Raw Essentials product discovery or source-page detail; never for cart, checkout, account, payment, booking, or veterinary advice.
---

# Raw Essentials NZ

Use this skill for bounded live snapshots of Raw Essentials public HTML pages. It makes unauthenticated GET requests only.

## Commands

```bash
python3 skills/raw-essentials-nz/scripts/cli.py search treats --pet-type dog --limit 10 --json
python3 skills/raw-essentials-nz/scripts/cli.py product https://rawessentials.co.nz/products/example --json
python3 skills/raw-essentials-nz/scripts/cli.py stores --json
```

- `search <query> [--pet-type dog|cat] [--page N] [--limit N] [--json]` searches one public listing page.
- `product <url> [--json]` fetches a same-site public product page.
- `stores [--json]` extracts bounded public store-page headings.
- `--timeout N` defaults to 10 seconds.

## Safety and limits

Returned prices, product text, and locations are public snapshots; include `source_url` and `retrieved_at` in downstream claims. Do not access carts, checkout, accounts, payment, subscriptions, bookings, or mutations. Raw feeding, supplements, and pet health content are source data, not veterinary or nutritional advice.

## Resources

- CLI: `scripts/cli.py`
- Live outage-tolerant smoke test: `scripts/smoke_test.py`
- Surface notes: `references/api-notes.md`
