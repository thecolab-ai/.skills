---
name: nz-airports
description: Query live public New Zealand airport arrivals and departures data for supported airports through a lightweight read-only CLI. Use when the task involves current flight board data for Auckland, Christchurch, Queenstown, or Wellington airports, or live ADS-B aircraft positions near Auckland Airport.
---

# NZ Airports

## Goal

Query live arrivals and departures data for supported New Zealand airports through a small deterministic CLI with human-readable and JSON output, without browser automation or account login.

AKL, CHC, ZQN, and WLG use airport/airline-published FIDS-style boards with scheduled and estimated times. AKL also keeps an optional adsb.lol live ADS-B aircraft-position view via `--source adsb`.

## Use this when

- A user asks for current arrivals or departures at a supported NZ airport
- A user wants to look up a flight number on a supported airport flight board
- A user needs lightweight machine-readable NZ airport FIDS-style data, or current aircraft-position data near AKL
- A workflow needs a fast read-only alternative to opening airport flight-board pages

## Do not use this for

- Booking, check-in, ticketing, PNR, passenger, baggage ownership, or account actions
- Aviation tracking outside the supported airport surfaces and AKL local ADS-B view
- Historical flight status or delay analysis
- Airports not listed by the `airports` command

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `arrivals` or `departures` with `--airport CODE` when a specific airport is known
3. Use `flight <flight-number>` when the user asks about a specific flight
4. Use `airports` to confirm currently supported airport codes
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention the source type: AKL/CHC/ZQN/WLG default to live public airport-board snapshots; AKL `--source adsb` is live aircraft-position data

## CLI

Run with:

```bash
python3 skills/nz-airports/scripts/cli.py <command> [flags]
```

## Commands

- `arrivals [--airport AKL|CHC|ZQN|WLG] [--source fids|adsb] [--limit N] [--json]` - current arrivals board; `--source adsb` is AKL-only
- `departures [--airport AKL|CHC|ZQN|WLG] [--source fids|adsb] [--limit N] [--json]` - current departures board; `--source adsb` is AKL-only
- `flight <flight-number> [--airport AKL|CHC|ZQN|WLG] [--source fids|adsb] [--json]` - lookup a flight number across current boards, or current AKL ADS-B callsigns
- `airports [--json]` - list supported airports and investigated gaps

## Examples

```bash
python3 skills/nz-airports/scripts/cli.py arrivals --airport AKL --limit 5
python3 skills/nz-airports/scripts/cli.py arrivals --airport AKL --source adsb --limit 5
python3 skills/nz-airports/scripts/cli.py arrivals --airport CHC --limit 10
python3 skills/nz-airports/scripts/cli.py departures --airport ZQN --limit 10 --json
python3 skills/nz-airports/scripts/cli.py arrivals --airport WLG --json
python3 skills/nz-airports/scripts/cli.py flight NZ5640 --json
python3 skills/nz-airports/scripts/cli.py airports
```

## Notes

- Supported sources: Auckland (AKL), Christchurch (CHC), Queenstown (ZQN), and Wellington (WLG)
- AKL defaults to Auckland Airport's scheduled FIDS API from the mobile app v5 backend. It exposes airline-published scheduled/estimated times, gates, terminals, baggage carousel, and status text where available.
- AKL `--source adsb` is a live ADS-B view from adsb.lol. It shows aircraft actually broadcasting near Auckland Airport right now and classifies low-altitude traffic as arrivals or departures from altitude and vertical-rate signals.
- CHC, ZQN, and WLG are scheduled FIDS-style airport boards. They expose airline-published scheduled/estimated times, gates, terminals, and status text where available.
- Christchurch uses public JSON endpoints split by domestic/international and arrivals/departures
- Queenstown uses public JSON endpoints for arrivals and departures; the CLI filters to today's NZ board when possible
- Wellington embeds the current flight-board JSON in the public flight page; departures can be empty late in the local operating day
- Auckland Airport's public website flight-board surface was investigated, but direct fetches and CloakBrowser/CDP attempts returned Cloudflare challenge/block pages from this environment. The mobile app v5 FIDS API is reachable directly.
- AKL FIDS uses public app Basic auth embedded in the Auckland Airport Android APK. The CLI ships those public app defaults and allows override with `AKL_API_USERNAME` / `AKL_API_PASSWORD` if they rotate.
- No personal API key, account cookie, browser session, or write action is required
- Endpoint shapes can change without notice because these are unofficial public website surfaces
- API and stability notes: `references/api-notes.md`
- CLI entrypoint: `scripts/cli.py`
