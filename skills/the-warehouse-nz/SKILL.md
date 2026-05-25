---
name: the-warehouse-nz
description: Query The Warehouse NZ product search, specials, product detail, and store finder. Use for The Warehouse NZ product lookup, prices, specials, SKUs, store locations, or opening hours. No cart or account.
---

# The Warehouse NZ

## Goal

Query live The Warehouse NZ product and store data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for The Warehouse NZ product prices or specials
- A user wants to search Warehouse products by keyword
- A user has a Warehouse SKU and wants public product details
- A user wants The Warehouse store locations, phone numbers, or current opening-hour summaries
- A workflow needs lightweight machine-readable The Warehouse product or store data

## Do not use this for

- Warehouse Stationery, Noel Leeming, TheMarket, or non-Warehouse retailers
- Authenticated account, MarketClub, personalised, wishlist, cart, checkout, order, delivery-slot, or payment actions
- Redistributing scraped Warehouse product or store data as a dataset
- Historical pricing or price-change claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword product lookup and `specials` for promotional products
3. Use `product` when an exact `R...` SKU is known
4. Use `stores --region` for region-scoped store lookups
5. Use `--json` for agent chaining, comparisons, alerts, or structured reports
6. Mention that prices and hours are live The Warehouse website snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/the-warehouse-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--json]` - product search with prices
- `product <sku> [--json]` - fetch public product details for one SKU
- `stores [--region name/code] [--json]` - list stores, optionally scoped to a NZ region
- `specials [query] [--limit N] [--page N] [--json]` - promotional products, optionally filtered by query

Examples:

```bash
python3 skills/the-warehouse-nz/scripts/cli.py search lego --limit 5
python3 skills/the-warehouse-nz/scripts/cli.py search "school bag" --limit 5 --json
python3 skills/the-warehouse-nz/scripts/cli.py product R3077131 --json
python3 skills/the-warehouse-nz/scripts/cli.py stores --region auckland --json
python3 skills/the-warehouse-nz/scripts/cli.py specials lego --limit 5 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, private token, or browser automation is required for the implemented read-only operations
- The CLI uses public Salesforce Commerce Cloud storefront endpoints and parses server-rendered product markup where JSON product search is not exposed
- Product and store response shapes can change without notice; verify with a small live query before relying on larger workflows
- Keep usage narrow and respectful
