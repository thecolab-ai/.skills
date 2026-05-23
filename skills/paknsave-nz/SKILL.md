---
name: paknsave-nz
description: Query PAK'nSAVE NZ stores, product categories, product search results, specials, and store-specific grocery prices using the public website's guest-token APIs. Use when the task involves PAK'nSAVE NZ product lookup, Papakura or other store prices, specials, category browsing, or product ID decoration. No account login required.
---

# PAK'nSAVE NZ

## Goal

Query live PAK'nSAVE NZ store and grocery product data through a small deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks for PAK'nSAVE NZ product prices or specials
- A user wants to search PAK'nSAVE products by keyword
- A user needs store IDs, store lookup, or category browsing
- A user has PAK'nSAVE product IDs and wants store-specific price/details
- A workflow needs machine-readable PAK'nSAVE product data

## Do not use this for

- New World, Four Square, Woolworths, or non-PAK'nSAVE retailers
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
python3 skills/paknsave-nz/scripts/cli.py <command> [flags]
```

Default store is PAK'nSAVE Papakura: `a7d09522-bee2-41e4-8fe0-0b82b7f342f5`.
Override with `--store-id <id>` or `PAKNSAVE_STORE_ID`.

### Commands

- `stores [--query text] [--limit N] [--json]` — list or filter PAK'nSAVE stores
- `categories [--store-id id] [--depth N] [--json]` — browse a store category tree
- `search <query> [--store-id id] [--limit N] [--page N] [--promo] [--json]` — product search with prices
- `specials [query] [--store-id id] [--limit N] [--page N] [--json]` — promotional products
- `product <product-id...> [--store-id id] [--json]` — decorate exact product IDs with details
- `token [--refresh] [--raw]` — fetch/cache a short-lived guest token

Examples:

```bash
python3 skills/paknsave-nz/scripts/cli.py stores --query papakura --limit 5
python3 skills/paknsave-nz/scripts/cli.py search milk --limit 10
python3 skills/paknsave-nz/scripts/cli.py specials cheese --limit 10 --json
python3 skills/paknsave-nz/scripts/cli.py product 5201479 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke-test.ts`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key or account login required
- Uses the same guest-token flow as the public website and caches tokens under `~/.cache/paknsave-cli/guest-token.json`
- Endpoint shapes can change; retry with a fresh token before assuming data is unavailable
- `--json` output is intended for exact product matching, basket comparison, and agent workflows
