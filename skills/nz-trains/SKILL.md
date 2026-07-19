---
name: nz-trains
description: "Query Wellington Metlink train lines through a lightweight read-only CLI using GTFS and GTFS-RT data. Use when the task involves Johnsonville, Kapiti, Hutt Valley, Melling, or Wairarapa Line stations, arrivals, delays, alerts, or live train positions. Requires METLINK_API_KEY."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Metlink"
  thecolab.source_type: "official"
  thecolab.auth: "api-key"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://api.opendata.metlink.org.nz/v1"
  thecolab.allowed_domains: "api.opendata.metlink.org.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# NZ Trains

## Goal

Query live Wellington train data from Metlink GTFS and GTFS-RT endpoints through a small deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks about Wellington Metlink train lines: JVL, KPL, HVL, MEL, or WRL
- A user wants next train arrivals from a Wellington region station
- A user asks about live train delays, cancellations, or vehicle positions
- A user asks about train-specific Metlink service alerts
- A workflow needs machine-readable Wellington train status data

## Do not use this for

- Wellington buses; use `nz-buses`
- Auckland public transport; use `at-transport`
- KiwiRail long-distance services such as Northern Explorer, Coastal Pacific, or TranzAlpine
- Fares, ticketing, journey planning, or historical performance analysis
- Mutating bookings, accounts, cards, alerts, or Metlink data

## Preferred workflow

1. Set `METLINK_API_KEY` in the environment before running data commands
2. Run `scripts/cli.py` with the narrowest subcommand that answers the task
3. Use `lines` for a quick network snapshot
4. Use `arrivals` or `station` for stop-specific next trains
5. Use `delays`, `vehicles`, and `alerts` for operational status
6. Use `--json` for agent chaining, comparisons, or structured reports

## Setup

Requires a Metlink Open Data API key.

```bash
export METLINK_API_KEY=your_key_here
```

The CLI reads `os.environ["METLINK_API_KEY"]`. There is no fallback key.

## CLI

Run with:

```bash
python3 skills/nz-trains/scripts/cli.py <command> [flags]
```

### Commands

- `lines [--json]` - list Wellington train lines with current delay, alert, and vehicle counts
- `line <name> [--json]` - detail for one line; accepts codes like `WRL` or names like `Wairarapa`
- `stations [--line <name>] [--json]` - train stations, optionally filtered to one line
- `station <stop-id-or-name> [--limit N] [--json]` - station detail with next train arrivals
- `arrivals <station> [--limit N] [--json]` - next live train arrivals at a station; accepts stop ID or name
- `delays [--line <name>] [--limit N] [--json]` - current late or cancelled train trips
- `vehicles [--line <name>] [--limit N] [--json]` - live train positions with lat/lon
- `alerts [--line <name>] [--limit N] [--json]` - active train-specific service alerts

Examples:

```bash
python3 skills/nz-trains/scripts/cli.py lines
python3 skills/nz-trains/scripts/cli.py line WRL --json
python3 skills/nz-trains/scripts/cli.py stations --line KPL
python3 skills/nz-trains/scripts/cli.py arrivals WELL --limit 8
python3 skills/nz-trains/scripts/cli.py station Masterton --json
python3 skills/nz-trains/scripts/cli.py delays --line Wairarapa
python3 skills/nz-trains/scripts/cli.py vehicles --line KPL --json
python3 skills/nz-trains/scripts/cli.py alerts --line HVL
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Upstream source: Metlink Open Data API
- API key required - set `METLINK_API_KEY`; never commit keys or `.env` files
- Python stdlib only; no package install, browser automation, account login, or write actions
- Filters routes to GTFS `route_type=2` and the five Wellington train route codes only
- `WELL` is the Wellington Station parent stop ID; numeric city bus stops such as `5000` are not train stations
- Wairarapa Line (`WRL`) covers the long-distance Metlink rail service to Masterton
