---
name: nz-airports
description: Query live public New Zealand airport arrivals and departures boards for supported airports through a lightweight read-only CLI. Use when the task involves current flight board data for Christchurch, Queenstown, or Wellington airports.
---

# NZ Airports

## Goal

Query live arrivals and departures board data for supported New Zealand airports through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

## Use this when

- A user asks for current arrivals or departures at a supported NZ airport
- A user wants to look up a flight number on a supported airport flight board
- A user needs lightweight machine-readable NZ airport FIDS-style data
- A workflow needs a fast read-only alternative to opening airport flight-board pages

## Do not use this for

- Booking, check-in, ticketing, PNR, passenger, baggage ownership, or account actions
- Aviation tracking outside the public airport flight boards
- Historical flight status or delay analysis
- Airports not listed by the `airports` command
- Auckland Airport until its public flight-board surface can be fetched without Cloudflare blocking

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `arrivals` or `departures` with `--airport CODE` when a specific airport is known
3. Use `flight <flight-number>` when the user asks about a specific flight
4. Use `airports` to confirm currently supported airport codes
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that data is a live public airport-board snapshot and the source is unofficial

## CLI

Run with:

```bash
python3 skills/nz-airports/scripts/cli.py <command> [flags]
```

## Commands

- `arrivals [--airport CHC|ZQN|WLG] [--limit N] [--json]` - current arrivals board
- `departures [--airport CHC|ZQN|WLG] [--limit N] [--json]` - current departures board
- `flight <flight-number> [--airport CHC|ZQN|WLG] [--json]` - lookup a flight number across current boards
- `airports [--json]` - list supported airports and investigated gaps

## Examples

```bash
python3 skills/nz-airports/scripts/cli.py arrivals --airport CHC --limit 10
python3 skills/nz-airports/scripts/cli.py departures --airport ZQN --limit 10 --json
python3 skills/nz-airports/scripts/cli.py arrivals --airport WLG --json
python3 skills/nz-airports/scripts/cli.py flight NZ5640 --json
python3 skills/nz-airports/scripts/cli.py airports
```

## Notes

- Supported live sources: Christchurch (CHC), Queenstown (ZQN), and Wellington (WLG)
- Christchurch uses public JSON endpoints split by domestic/international and arrivals/departures
- Queenstown uses public JSON endpoints for arrivals and departures; the CLI filters to today's NZ board when possible
- Wellington embeds the current flight-board JSON in the public flight page; departures can be empty late in the local operating day
- Auckland (AKL) was investigated, but direct fetches and CloakBrowser/CDP attempts returned Cloudflare challenge/block pages from this environment, so AKL is not listed as supported
- No API key, username, password, account cookie, browser session, or write action is required
- Endpoint shapes can change without notice because these are unofficial public website surfaces
- API and stability notes: `references/api-notes.md`
- CLI entrypoint: `scripts/cli.py`
