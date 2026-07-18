---
name: petdirect-nz
description: Use when searching Petdirect NZ products, comparing current public variant prices, checking availability, or reading product details. Parses bounded public search-page state and product JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, subscription, prescription, or other mutations.
---

# Petdirect NZ

## Goal

Retrieve current public Petdirect NZ search, product, variant, and price data without login or browser automation.

## Use this when

- Searching Petdirect products by keyword
- Comparing public prices and variants for a known product
- Capturing a current public price snapshot with source evidence

## Do not use this for

- Cart, checkout, account, Pet Perks, payment, subscription, prescription, booking, order, stock reservation, or mutations
- Veterinary advice or product-suitability decisions
- Bulk scraping, historical-price claims, or redistribution as a dataset

## Workflow

1. Use `search` for discovery. Results are capped at 24 and come from embedded public search state.
2. Use `product` for a Petdirect product URL, `/p/` path, or slug.
3. Use `price-snapshot` for current ProductGroup variant prices.
4. Add `--json` for agent chaining. Every command reports `source_url` and UTC `retrieved_at`.
5. Treat member prices, promotions, and availability as live public observations that may change.

## CLI

```bash
python3 skills/petdirect-nz/scripts/cli.py search "dog food" --limit 5 --json
python3 skills/petdirect-nz/scripts/cli.py product lamb-rice-adult-dry-dog-food --json
python3 skills/petdirect-nz/scripts/cli.py price-snapshot /p/lamb-rice-adult-dry-dog-food/ --json
```

The global `--timeout N` option goes before the command and defaults to 10 seconds.

## Output and safety

- Uses Python standard library only and unauthenticated GET requests.
- Search parses the first bounded `window.__SERVER_STATE__` object and never emits the raw multi-megabyte page.
- Detail commands parse Product or ProductGroup JSON-LD defensively.
- Responses are size-capped; missing or incomplete product data is an error rather than empty success.

## Resources

- CLI: `scripts/cli.py`
- Live and fixture smoke tests: `scripts/smoke_test.py`
- Endpoint, parser, and safety notes: `references/api-notes.md`
