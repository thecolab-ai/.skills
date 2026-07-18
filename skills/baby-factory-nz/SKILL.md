---
name: baby-factory-nz
description: Use when searching Baby Factory NZ products, checking current public sale prices, or reading product details and offers. Parses bounded public search-page state and product JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, booking, hire, registry, or other mutations.
---

# Baby Factory NZ

## Goal

Retrieve current public Baby Factory NZ search, product, offer, and price data without login or browser automation.

## Use this when

- Searching Baby Factory products by keyword
- Checking a current public sale or regular price
- Reading Product JSON-LD for a known product URL or slug

## Do not use this for

- Cart, checkout, account, payment, booking, hire, gift registry, order, stock reservation, or mutations
- Child-safety or medical advice; consult product manuals and qualified professionals
- Bulk scraping, historical-price claims, or redistribution as a dataset

## Workflow

1. Use `search` for discovery. Results are capped at 20 and parsed from bounded public page state.
2. Use `product` for one Baby Factory product URL or slug.
3. Use `price-snapshot` for a compact current offer record.
4. Add `--json` for machine-readable output. Every command reports `source_url` and UTC `retrieved_at`.
5. Treat values as live website observations; verify safety-critical specifications against the manufacturer.

## CLI

```bash
python3 skills/baby-factory-nz/scripts/cli.py search "car seat" --limit 5 --json
python3 skills/baby-factory-nz/scripts/cli.py product disney-baby-everslim-4-in-1-convertible-car-seat-vintage-disney-4020561-black-grey --json
python3 skills/baby-factory-nz/scripts/cli.py price-snapshot https://www.babyfactory.co.nz/example-product --json
```

The global `--timeout N` option goes before the command and defaults to 10 seconds.

## Output and safety

- Uses Python standard library only and unauthenticated GET requests.
- Search parses bounded `window.category` JSON; detail commands parse Product JSON-LD.
- Responses are size-capped and normalized; raw HTML is never emitted.
- Missing, malformed, or incomplete product data fails rather than returning fabricated success.

## Resources

- CLI: `scripts/cli.py`
- Live and fixture smoke tests: `scripts/smoke_test.py`
- Endpoint, parser, and safety notes: `references/api-notes.md`
