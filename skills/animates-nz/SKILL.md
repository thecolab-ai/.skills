---
name: animates-nz
description: Use when looking up Animates NZ products, current public prices, availability, or product details. Queries bounded public Magento search results and parses product-page JSON-LD through a read-only Python CLI; no cart, checkout, account, payment, prescription, booking, grooming, or other mutations.
---

# Animates NZ

## Goal

Retrieve current public Animates NZ product search and detail data without login or browser automation.

## Use this when

- Searching Animates NZ products by keyword
- Looking up a public Animates product URL or numeric product ID
- Capturing a current price and availability snapshot with source evidence

## Do not use this for

- Cart, checkout, account, Petpoints, payment, prescription, booking, grooming, hire, stock reservation, or any mutation
- Medical or veterinary advice
- Bulk scraping, historical-price claims, or redistribution as a dataset

## Workflow

1. Use `search` to discover products. Results are capped at 10 and each result is verified against its public detail page.
2. Use `product` for one known Animates URL, `.html` path, or numeric product ID.
3. Use `price-snapshot` for the smallest price-and-availability record.
4. Add `--json` for machine-readable output. Every command reports `source_url` and UTC `retrieved_at`.
5. Treat values as live website observations, not guaranteed store stock or a historical record.

## CLI

```bash
python3 skills/animates-nz/scripts/cli.py search "dog food" --limit 3 --json
python3 skills/animates-nz/scripts/cli.py product 18463 --json
python3 skills/animates-nz/scripts/cli.py price-snapshot https://www.animates.co.nz/example.html --json
```

The global `--timeout N` option goes before the command and defaults to 10 seconds.

## Output and safety

- Uses Python standard library only and unauthenticated GET requests.
- Search uses the public Magento read-only search endpoint only to obtain bounded product IDs, then parses Product JSON-LD from detail HTML.
- Responses are size-capped; malformed or incomplete upstream data fails instead of returning fabricated success.
- Search can make one search request plus up to `--limit` detail requests; keep limits narrow.

## Resources

- CLI: `scripts/cli.py`
- Live and fixture smoke tests: `scripts/smoke_test.py`
- Endpoint, parser, and safety notes: `references/api-notes.md`
