---
name: nz-buses
description: "Query Wellington-region Metlink bus data through a lightweight read-only CLI for stops, routes, arrivals, service alerts, and vehicle positions. Use for Wellington buses only; do not use for Wellington trains, ferries, cable car, or Auckland Transport."
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
  thecolab.allowed_domains: "api.opendata.metlink.org.nz,opendata.metlink.org.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "gated"
  thecolab.maintainer: "@adam91holt"
---

# NZ Buses

## Goal

Query live Wellington-region bus data through a small deterministic CLI with human-readable and JSON output.

Metlink Wellington is the v1 source. This skill intentionally filters the shared Metlink GTFS and GTFS-Realtime feeds to bus routes only.

## Use this when

- A user asks about Wellington region Metlink buses
- A user asks for live Metlink bus arrivals from a known stop
- A user wants to search Wellington region stops or routes
- A user asks about Metlink bus service alerts or live bus vehicle positions
- A workflow needs lightweight machine-readable Wellington bus data

## Do not use this for

- Auckland buses, trains, or ferries; use `at-transport` instead
- Wellington trains or other rail-specific tasks; use a train-specific skill if available
- Wellington ferries or cable car; they are separate modes and are not covered here
- Journey planning, route directions, fares, tickets, or account actions
- Historical timetable claims or punctuality analysis unless another dataset provides history
- High-volume mirroring of Metlink data

## Preferred workflow

1. Confirm the request is for Wellington-region Metlink buses
2. Run `scripts/cli.py` with the narrowest subcommand that answers the task
3. Use `stops --query` or `stops --near` to find stop IDs before calling `arrivals`
4. Use `routes` or `route <number>` to discover route IDs before route-filtered vehicle lookups
5. Use `--json` for agent chaining, comparisons, or structured reports
6. Mention that results are live Metlink snapshots and require a Metlink Open Data API key

## CLI

Set a free Metlink Open Data API key first:

```bash
export METLINK_API_KEY="..."
```

Run with:

```bash
python3 skills/nz-buses/scripts/cli.py <command> [flags]
```

### Commands

- `routes [--query text] [--limit N] [--json]` - list/search Metlink bus routes
- `route <route> [--limit N] [--json]` - show one bus route and its stops
- `stops [--query text] [--near location-or-lat-lon] [--limit N] [--json]` - search Metlink bus stops
- `stop <stop-id> [--limit N] [--json]` - show stop details with live bus arrivals
- `arrivals <stop-id> [--limit N] [--json]` - live bus arrivals for a Metlink stop
- `vehicles [--route route] [--limit N] [--json]` - live Metlink bus vehicle positions
- `alerts [--limit N] [--json]` - active Metlink bus service alerts

Examples:

```bash
python3 skills/nz-buses/scripts/cli.py routes --limit 10
python3 skills/nz-buses/scripts/cli.py route 1 --limit 12
python3 skills/nz-buses/scripts/cli.py stops --near Lambton --limit 5
python3 skills/nz-buses/scripts/cli.py stop 5011 --limit 5
python3 skills/nz-buses/scripts/cli.py arrivals 5011 --json
python3 skills/nz-buses/scripts/cli.py vehicles --route 83 --limit 10 --json
python3 skills/nz-buses/scripts/cli.py alerts --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Read-only only: no journey planning, booking, ticketing, account, or mutation actions
- Python stdlib only; no package install or browser automation is required for normal use
- Metlink requests use `METLINK_API_KEY` and fail with a clear message when it is missing
- Do not hardcode or commit Metlink API keys; use the `METLINK_API_KEY` environment variable only
- Bus filtering includes standard GTFS bus `route_type=3` and Metlink school bus `route_type=712`; rail `2`, ferry `4`, and cable car `5` are excluded
- The Metlink API returns live snapshots; stops, trips, delays, alerts, and vehicles can change quickly
- Canterbury Metro, ORC Bus, BayBus, and other non-Auckland bus networks are follow-ups, not v1 commands
