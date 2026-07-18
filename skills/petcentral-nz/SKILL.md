---
name: petcentral-nz
description: Query Pet Central NZ public Shopify product, collection, price, and availability snapshots through a no-login read-only CLI. Use when a task needs current Pet Central catalogue lookup or structured product detail; never for cart, checkout, account, payment, prescription, or veterinary advice.
---

# Pet Central NZ

Use this skill for live public Pet Central catalogue snapshots. It uses bounded unauthenticated Shopify GET requests only.

## Commands

```bash
python3 skills/petcentral-nz/scripts/cli.py search "dog food" --limit 10 --json
python3 skills/petcentral-nz/scripts/cli.py product small-animal-treat-mini-sticks-12pc --json
python3 skills/petcentral-nz/scripts/cli.py collections --json
```

- `search <query> [--page N] [--limit N] [--json]` searches one bounded catalogue page locally.
- `product <handle-or-url> [--json]` fetches Shopify product detail.
- `collections [--json]` lists public Shopify collections.
- `--timeout N` defaults to 10 seconds.

## Safety and limits

Prices and stock are a moment-in-time public website snapshot; cite returned `source_url` and `retrieved_at`. Do not use for cart, checkout, account, payment, prescription, delivery, or any mutation. Pet food, treatments, and health product content is source data, not veterinary or suitability advice.

## Resources

- CLI: `scripts/cli.py`
- Live outage-tolerant smoke test: `scripts/smoke_test.py`
- Surface notes: `references/api-notes.md`
