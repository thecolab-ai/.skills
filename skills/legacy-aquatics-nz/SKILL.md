---
name: legacy-aquatics-nz
description: Query Legacy Aquatics NZ public WooCommerce category, product-search, and product-page HTML through a no-login read-only CLI. Use when a task needs current aquarium or reptile product discovery and source detail; never for cart, checkout, account, payment, hire, or husbandry advice.
---

# Legacy Aquatics NZ

Use this skill for bounded snapshots of public Legacy Aquatics WooCommerce HTML. It uses unauthenticated GET requests only.

## Commands

```bash
python3 skills/legacy-aquatics-nz/scripts/cli.py category aquariums-and-equipment --limit 10 --json
python3 skills/legacy-aquatics-nz/scripts/cli.py search filter --limit 10 --json
python3 skills/legacy-aquatics-nz/scripts/cli.py product https://legacyaquatics.co.nz/product/hailea-hang-on-filter-he-200/ --json
```

- `category <slug> [--page N] [--limit N] [--json]` lists bounded public category product links.
- `search <query> [--page N] [--limit N] [--json]` searches public WooCommerce results.
- `product <url> [--json]` fetches a same-site public product page.
- `--timeout N` defaults to 10 seconds.

## Safety and limits

Use returned `source_url` and `retrieved_at`; prices and stock are live public snapshots, not guarantees. Do not access cart, checkout, account, payment, booking, hire, or mutations. Aquarium and reptile product content is source data, not fitment, safety, or husbandry advice.

## Resources

- CLI: `scripts/cli.py`
- Live outage-tolerant smoke test: `scripts/smoke_test.py`
- Surface notes: `references/api-notes.md`
