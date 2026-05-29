---
name: briscoes-nz
description: Query Briscoes NZ homewares product search, sale/deal snapshots, SKU detail, and store-finder. Use for Briscoes product lookup, prices, sale products, or store locations. No cart or account.
---

# Briscoes NZ

## Goal

Query live Briscoes NZ product and store data through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for Briscoes NZ product prices or sale/deal products
- A user wants to search Briscoes products by keyword
- A user has a Briscoes SKU and wants product details
- A user wants Briscoes store locations or contact details
- A workflow needs lightweight machine-readable Briscoes public product or store data

## Do not use this for

- Non-Briscoes retailers or Briscoes Group brands other than Briscoes NZ
- Authenticated account, rewards, personalised, cart, checkout, order, gift registry, or payment actions
- Redistributing scraped Briscoes product data as a dataset
- Historical pricing or price-change claims unless another dataset provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `search` for keyword price/product lookup
3. Use `specials` for sale/deal-flagged products; this is a search-derived view verified against Magento product pricing, not a dedicated Briscoes specials API
4. Use `product` when an exact SKU is known and full Magento price-range detail matters
5. Use `stores --region` to narrow store-finder results by city, region, suburb, or name
6. Use `--json` for agent chaining, comparisons, alerts, or structured reports
7. Mention that prices are live Briscoes online snapshots and the source is unofficial

## CLI

Run with:

```bash
python3 skills/briscoes-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--json]` - product search with current prices
- `product <sku> [--json]` - fetch exact SKU detail
- `stores [--region text] [--json]` - list public Briscoes store-finder locations
- `specials [query] [--limit N] [--page N] [--json]` - sale/deal-flagged products verified to have a sale price below regular price, optionally filtered by query

Examples:

```bash
python3 skills/briscoes-nz/scripts/cli.py search towel --limit 10
python3 skills/briscoes-nz/scripts/cli.py search "cast iron" --limit 5 --json
python3 skills/briscoes-nz/scripts/cli.py product 1129433 --json
python3 skills/briscoes-nz/scripts/cli.py stores --region auckland --json
python3 skills/briscoes-nz/scripts/cli.py specials bedding --limit 10 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key secret, username, password, account cookie, or browser automation is required for supported read-only operations
- Briscoes uses an Adobe Commerce/Magento PWA backed by Klevu for product search/listing
- `search` uses Klevu search data; `specials` uses Klevu discovery plus Magento price verification; `product` and `stores` use Briscoes Magento GraphQL
- Endpoint shapes can change; verify with a small live query before relying on large workflows
- Keep usage narrow and respectful
