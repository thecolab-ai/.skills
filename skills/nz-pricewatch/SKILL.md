---
name: nz-pricewatch
description: Query PriceSpy NZ public read-only product search, merchant offers, and price-history data for NZ electronics and appliances through a lightweight CLI. Use when the task involves NZ price comparison, cheapest current electronics/appliance prices, store price spread, PriceSpy product ids, or recent price movement. No login, cart, checkout, or account credentials required.
---

# NZ Pricewatch

## Goal

Query live NZ electronics and appliance price comparison data through a small deterministic CLI with human-readable and JSON output, focused on PriceSpy NZ as the primary source.

## Use this when

- A user asks for the cheapest current NZ electronics or appliance price
- A user wants to compare store prices for a specific PriceSpy product
- A user wants to know whether a model price has moved in the last week or month
- A user asks for a PriceSpy product id, product detail, merchant list, or price spread
- A user wants lightweight machine-readable NZ price comparison data

## Do not use this for

- Buying, checkout, carts, alerts, wishlists, logins, or account actions
- Non-NZ price comparisons
- High-volume scraping or dataset redistribution
- Warranty, finance, delivery-date, or stock guarantees beyond the current public snapshot
- The Warehouse or Bunnings-specific workflows; use those dedicated skills when the user asks for those retailers directly

## Preferred workflow

1. Run `scripts/cli.py cheapest` for lowest current price questions
2. Use `search` to shortlist products, with `--category tvs`, `phones`, `laptops`, or a numeric PriceSpy category id when helpful
3. Use `product <id>` after selecting a result to fetch merchant offers and store price spread
4. Use `history <id> --days 30` for price stability or drop/rise claims
5. Use `trending --category ...` for a sampled view of products moving down or up
6. Use `categories --query ...` to discover PriceSpy category ids
7. Use `--json` for agent chaining, comparisons, alerts, or structured reports

## CLI

Run with:

```bash
python3 skills/nz-pricewatch/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--category id/name] [--limit N] [--max-price N] [--min-price N] [--json]` — product search across NZ retailers via PriceSpy
- `product <id-or-url> [--json]` — product detail with current merchant list and price spread
- `cheapest <query> [--category id/name] [--limit N] [--json]` — cheapest current PriceSpy match, enriched with offers and 30-day movement summary
- `history <id-or-url> [--days 30] [--json]` — PriceSpy price-history points and movement summary
- `trending [--category id/name] [--direction down|up|any] [--days N] [--limit N] [--json]` — sampled category products with notable price moves
- `categories [--query text] [--limit N] [--json]` — list/search PriceSpy category ids

Examples:

```bash
python3 skills/nz-pricewatch/scripts/cli.py cheapest "65 inch oled" --json
python3 skills/nz-pricewatch/scripts/cli.py search "iphone 15" --max-price 1500 --limit 10 --json
python3 skills/nz-pricewatch/scripts/cli.py product 15843963 --json
python3 skills/nz-pricewatch/scripts/cli.py history 15843963 --days 30 --json
python3 skills/nz-pricewatch/scripts/cli.py trending --category tvs --direction down --json
python3 skills/nz-pricewatch/scripts/cli.py categories --query washer --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- PriceSpy NZ (`pricespy.co.nz`) is the upstream source for product search, merchant offer rows, and price-history points returned by this skill
- PriceMe NZ currently presents a Cloudflare challenge to plain no-login CLI requests, so it is documented as a caveat rather than wired into the read-only CLI
- GetPrice NZ is secondary and not used by the CLI because PriceSpy provides the stronger electronics/appliance aggregation and price-history data
- PriceSpy search and product pages are public but unofficial; endpoint and embedded RSC shapes can change without notice
- Treat prices, stock status, store count, and history summaries as live snapshots; click through to the retailer before purchasing
