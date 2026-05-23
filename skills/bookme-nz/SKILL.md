---
name: bookme-nz
description: Query Bookme NZ public read-only deal/search endpoints for discounted activities, experiences, tours, restaurants, and last-minute things to do. Use when the task involves Bookme.co.nz deals, cheap activities by region/category, hot deals, cheapest current offers, restaurant discounts, or machine-readable public Bookme deal data. No login, booking, checkout, or account credentials required.
---

# Bookme NZ

## Goal

Query live Bookme NZ discount marketplace data through a lightweight deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks for cheap or discounted things to do in New Zealand
- A user wants Bookme activity, experience, tour, restaurant, or last-minute deal lookup
- A user wants current hot/featured Bookme offers
- A user wants cheapest current Bookme deals in a region
- A user has a Bookme deal id or URL and wants public deal details
- A workflow needs machine-readable public Bookme deal data

## Do not use this for

- Booking, checkout, payment, cart, voucher redemption, login, favourites, account, or operator actions
- Official venue ticketing outside Bookme
- Non-Bookme deal marketplaces or historical price tracking
- High-volume scraping or dataset redistribution
- Claims that a Bookme deal is available beyond the current live snapshot

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `deals --region ... --category ...` for region/category discount scans
3. Use `cheapest` for lowest current discounted prices and `hot` for featured offers
4. Use `search` for keyword lookups such as activity names, operators, or themes
5. Use `deal <id-or-url>` after selecting a result to fetch public detail fields
6. Use `regions` and `categories` to discover supported slugs
7. Use `--json` for agent chaining, alerts, comparisons, or structured reports

## CLI

Run with:

```bash
python3 skills/bookme-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--region name] [--category slug/id] [--sort featured|discount|low|high] [--limit N] [--json]` — search current discounted deals by keyword
- `deals [--region name] [--category slug/id] [--sort featured|discount|low|high] [--limit N] [--json]` — list current discounted deals
- `cheapest [--region name] [--category slug/id] [--limit N] [--json]` — cheapest current discounted deals
- `hot [--region name] [--limit N] [--json]` — featured/hot discounted deals
- `deal <id-or-slug-or-url> [--region name] [--json]` — fetch public detail fields for one deal
- `regions [--json]` — list supported Bookme NZ regions
- `categories [--query text] [--limit N] [--json]` — list/search supported deal categories

Examples:

```bash
python3 skills/bookme-nz/scripts/cli.py deals --region auckland --category jet-boating --limit 5
python3 skills/bookme-nz/scripts/cli.py cheapest --region queenstown --category jet-boating --limit 10 --json
python3 skills/bookme-nz/scripts/cli.py search curry --region wellington --category restaurants --json
python3 skills/bookme-nz/scripts/cli.py hot --region rotorua --limit 5 --json
python3 skills/bookme-nz/scripts/cli.py deal 8004 --region auckland --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, private token, or browser session is required for supported read-only commands
- The CLI uses Bookme's public website JSON deal endpoints and public detail pages only
- Discount-focused commands require `reduction_raw > 0`, so price-guarantee or reservation-only cards are not treated as discounted deals
- Treat prices, spaces, dates, and discounts as live Bookme snapshots that can change or sell out quickly
- Bookme.co.nz is the upstream source for all deal data returned by this skill
