---
name: first-table-nz
description: Query First Table NZ restaurants, 50%-off early-table deals, city/suburb discovery, cuisine search, and availability slots. Read-only; no booking, login, or payment.
---

# First Table NZ

## Goal

Query live First Table NZ restaurant and availability information through a deterministic Python CLI using public website data and unauthenticated GraphQL calls observed from the frontend.

## Use this when

- A user asks which First Table restaurants are available in a NZ city or suburb
- A user wants to search First Table restaurants by cuisine, suburb, or name
- A user wants restaurant detail, ratings, session types, diner limits, or booking-fee snapshots
- A workflow needs machine-readable First Table NZ restaurant or availability data

## Do not use this for

- Booking, checkout, payment, account signup, login, favourites, cancellations, or member actions
- First Table countries outside New Zealand unless the CLI is explicitly extended and verified for that host
- Claiming guaranteed table availability without rechecking live data immediately before use
- Redistributing First Table data as a bulk dataset

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `city` to inspect city metadata, suburbs, and tags before a targeted search
3. Use `search` for restaurant discovery and `detail` when an exact First Table restaurant id is known
4. Use `availability` for read-only slot checks; never attempt booking mutations
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that data is a live, unofficial public snapshot from First Table NZ

## CLI

Run with:

```bash
python3 skills/first-table-nz/scripts/cli.py <command> [flags]
```

### Commands

- `cities [--json]` — list discoverable NZ First Table city/region pages
- `city [city-slug] [--json]` — inspect a city/region page, suburbs, tags, sessions, and counts
- `search [query] [--city slug] [--session breakfast|lunch|dinner|dinner2|lasttable] [--date YYYY-MM-DD] [--people N] [--limit N] [--json]` — find restaurants in a city
- `detail <restaurant-id> [--json]` — fetch restaurant detail by First Table id
- `availability <id...> [--date YYYY-MM-DD] [--people N] [--available-only] [--limit N] [--json]` — fetch read-only public slots for one or more restaurant ids

Examples:

```bash
python3 skills/first-table-nz/scripts/cli.py city auckland --json
python3 skills/first-table-nz/scripts/cli.py search sushi --city auckland --limit 5
python3 skills/first-table-nz/scripts/cli.py detail 1142 --json
python3 skills/first-table-nz/scripts/cli.py availability 1142,1698 --date 2026-05-25 --people 2 --available-only --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, or browser automation is required for the read-only commands
- The CLI uses Python stdlib only
- The upstream GraphQL and frontend SSR shapes are unofficial and can change; verify with live smoke tests before large workflows
- Availability responses can include cached or stale status fields from the upstream service; treat them as source metadata, not an agent-side guarantee
