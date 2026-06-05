---
name: homes-nz
description: Query homes.co.nz NZ residential property estimates (HomesEstimate/HEV), sales history, suburb trends, and nearby comparable properties. No login required.
---

# Homes NZ

## Goal

Query live homes.co.nz residential property estimates and historical sale data through a lightweight deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks for a homes.co.nz HomesEstimate, HEV, or estimated value for a NZ home
- A user wants sales history for a residential property
- A user has a homes.co.nz property id and wants property details
- A user wants nearby comparable homes around a known property id
- A user wants suburb-level HomesEstimate trend data
- A workflow needs machine-readable public homes.co.nz property estimate data

## Do not use this for

- Trade Me current sale/rental listing searches; use `trademe-nz` for active listings and listing-market scans
- Property valuation advice, lending decisions, or substitute professional valuation reports
- Authenticated homes.co.nz account, claim-home, favourite, agent enquiry, lead, update, or mutation actions
- High-volume scraping or dataset redistribution
- Non-residential, overseas, or non-homes.co.nz property data

## Preferred workflow

1. Run `scripts/cli.py address` to find a property id from a partial address
2. Use `property <id>` for HomesEstimate, beds/baths/area, council attributes, last sale, and sales history
3. Use `nearby <id>` for compact comparable-property snapshots around a known property
4. Use `suburb <name>` for suburb estimate trend and rental estimate snapshots
5. Use `--json` for agent chaining, comparisons, alerts, or structured reports
6. Mention that homes.co.nz estimates are automated public snapshots and not formal valuations

## CLI

Run with:

```bash
python3 skills/homes-nz/scripts/cli.py <command> [flags]
```

### Commands

- `address <query> [--limit N] [--json]` — search partial addresses and return matching properties with ids, HomesEstimate, and last sale when exposed
- `property <property-id> [--json]` — fetch full public property detail, HomesEstimate, beds/baths/area, last sale, and sales history
- `suburb <name-or-id> [--history-limit N] [--json]` — fetch suburb HomesEstimate trend and median rent estimate
- `nearby <property-id> [--radius N] [--limit N] [--json]` — fetch nearby comparable property snapshots around a known property id

Examples:

```bash
python3 skills/homes-nz/scripts/cli.py address "100 Queen Street Auckland" --limit 5
python3 skills/homes-nz/scripts/cli.py property 868a7ea3-36ac-4f10-8709-0023d96910a7 --json
python3 skills/homes-nz/scripts/cli.py suburb "Northcote Point" --json
python3 skills/homes-nz/scripts/cli.py nearby ae4c05ca-2662-44ca-9573-a3e00772fdf7 --radius 150 --limit 8 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, private token, or browser automation is required for supported read-only commands
- Scope is intentionally distinct from `trademe-nz`: Trade Me is for current listings and market scans; homes.co.nz is for estimated values, property attributes, and historical sales
- Address search can return suburb/street/city suggestions without a property id; use a more specific address or select a returned property id before calling `property`
- Treat estimates and sales data as live public snapshots; endpoint shapes and available fields can change without notice
- Keep usage narrow and respectful
