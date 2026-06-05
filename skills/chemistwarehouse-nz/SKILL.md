---
name: chemistwarehouse-nz
description: Query Chemist Warehouse NZ public searchapiv2 suggestion, product search, category listing, and product detail endpoints through a lightweight no-login CLI. Use for live NZ pharmacy product names, prices, categories, product IDs, ratings, and machine-readable Chemist Warehouse NZ data. Read-only; no cart, checkout, account, prescription, order, or payment mutations.
---

# Chemist Warehouse NZ

## Goal

Query live Chemist Warehouse NZ product data through a small deterministic CLI with concise human output and normalized JSON, without browser automation, login, or write actions.

## Use this when

- A user asks for Chemist Warehouse NZ product prices, IDs, ratings, or product URLs
- A user wants keyword suggestions, product search, category listings, or product detail
- A workflow needs lightweight machine-readable Chemist Warehouse NZ product data

## Do not use this for

- Chemist Warehouse Australia or unrelated pharmacies
- Cart, checkout, payment, account, order, wishlist, stock reservation, prescription upload, prescription management, or other mutations
- Authenticated, personalised, medical-record, or prescription-only workflows
- Historical price claims unless another source provides history

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest command that answers the task.
2. Use `suggest` to discover terms, product IDs, and category IDs.
3. Use `search` for keyword price/product lookup; use `category` when a category ID is known.
4. Use `product` for exact detail by product ID or Chemist Warehouse `/buy/<id>/...` URL.
5. Use `--json` for comparisons, reports, or agent chaining.
6. State that prices are live online snapshots from an unofficial read-only wrapper.

## CLI

Run with:

```bash
python3 skills/chemistwarehouse-nz/scripts/cli.py <command> [flags]
```

Commands:

- `suggest TERM [--limit N] [--json]`
- `search TERM [--limit N] [--page N] [--json]`
- `category ID [--limit N] [--page N] [--json]`
- `product PRODUCT_ID_OR_URL [--json]`

Examples:

```bash
python3 skills/chemistwarehouse-nz/scripts/cli.py suggest panadol --limit 5
python3 skills/chemistwarehouse-nz/scripts/cli.py search "vitamin c" --limit 10 --json
python3 skills/chemistwarehouse-nz/scripts/cli.py category 256 --limit 10
python3 skills/chemistwarehouse-nz/scripts/cli.py product 6973 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live read-only smoke test: `scripts/smoke_test.py`
- API and safety notes: `references/api-notes.md`

## Notes

- The CLI uses public unauthenticated `searchapiv2` endpoints with browser-compatible headers.
- Product detail supports numeric product IDs directly; product URLs are parsed for `/buy/<id>/`.
- Search can redirect for some brand-exact terms; use more general terms such as `vitamin c` for smoke tests.
- Endpoint shapes can change; verify with a small live query before relying on broader workflows.
