---
name: gaspy-nz
description: Query Gaspy NZ public crowd-sourced fuel price statistics through a lightweight no-login CLI. Use when the task involves Gaspy crowd-sourced NZ fuel price snapshots, national observed averages, top cheapest 91 stations, station/brand counts, or recent confirmation totals. Read-only; no login or price reporting.
---

# Gaspy NZ

## Goal

Query live Gaspy NZ public crowd-sourced fuel price statistics through a small deterministic CLI with human-readable and JSON output, without browser automation, login, or price reporting.

## Use this when

- A user specifically asks for Gaspy NZ or crowd-sourced/user-reported NZ fuel price data
- A user wants national observed Gaspy averages, minimums, maximums, and station counts by fuel type
- A user wants the public Gaspy top cheapest stations for 91
- A user wants Gaspy public activity metadata such as station count, brand count, Gas Spies, or recent confirmations
- A workflow needs a lightweight read-only Gaspy complement to official-source fuel price tools

## Do not use this for

- Official retailer-published NZ fuel prices from Gull, Z, BP, or FuelClock; use `fuelclock-nz` for that official-source alternative
- Station lookup, nearby search, regional search, or station detail requests; those Gaspy mobile API surfaces require login and are intentionally not implemented here
- Updating, confirming, reporting, or correcting Gaspy prices
- Authenticated Gaspy account, favourites, notifications, leaderboards, Gaspy Gold, garage, or vehicle actions
- Historical or commercial Gaspy datasets; contact Datamine/Gaspy for licensed extracts

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `summary` for a quick Gaspy public snapshot across prices, metadata, and top 91 stations
3. Use `prices --fuel` when the user asks about one fuel type
4. Use `cheapest --fuel 91` only for the public top-cheapest 91 table
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that Gaspy data is crowd-sourced/user-reported and may be stale or wrong

## CLI

Run with:

```bash
python3 skills/gaspy-nz/scripts/cli.py <command> [flags]
```

### Commands

- `summary [--json]` - national observed price stats, feed metadata, and top cheapest 91
- `prices [--fuel 91|95|98|100|diesel|lpg|type-21] [--json]` - national observed price stats by fuel
- `cheapest [--fuel 91] [--limit N] [--json]` - public top cheapest stations for 91
- `metadata [--json]` - station count, brand count, Gas Spies, confirmations, and feed timestamps
- `fuel-types [--json]` - fuel type ids observed in the public feed

Examples:

```bash
python3 skills/gaspy-nz/scripts/cli.py summary
python3 skills/gaspy-nz/scripts/cli.py prices --fuel diesel --json
python3 skills/gaspy-nz/scripts/cli.py cheapest --fuel 91 --limit 3 --json
python3 skills/gaspy-nz/scripts/cli.py metadata --json
python3 skills/gaspy-nz/scripts/cli.py fuel-types --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, private token, or browser session is required for the implemented read-only operations
- Uses the public Firebase Realtime Database feed behind `https://www.gaspy.nz/stats.html`
- Python stdlib only; no package install required
- `--json` output is intended for chaining into other tools or agent steps
- Public Gaspy station/nearby mobile endpoints were checked and require login, so they are documented as out of scope rather than exposed as broken commands
- Gaspy prices are crowd-sourced observations; incorrect, discounted, stale, or missing station prices are possible
- `fuelclock-nz` remains the better tool when the user asks for official retailer-published prices or FuelClock supply/watch data
