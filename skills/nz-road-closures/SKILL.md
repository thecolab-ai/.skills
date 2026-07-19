---
name: nz-road-closures
description: "Query NZTA / Waka Kotahi state-highway road closures, roadworks, incidents, traffic cameras, routes, and regions. Use for NZ state highway conditions. Read-only; no alerts, accounts, or reporting."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "NZ Transport Agency Waka Kotahi"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.journeys.nzta.govt.nz"
  thecolab.allowed_domains: "www.journeys.nzta.govt.nz,www.trafficnz.info"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Road Closures

## Goal

Query live NZTA / Waka Kotahi Journey Planner road-event and traffic-camera data through a small deterministic CLI with human-readable and JSON output, without browser automation, account login, or API keys.

## Use this when

- A user asks for current New Zealand state-highway road closures, roadworks, incidents, hazards, or area warnings
- A user wants NZTA traffic camera details or current camera image URLs
- A user asks for journey conditions across NZTA Journey Planner regions
- A user needs lightweight machine-readable NZTA road-event data
- A workflow needs national state-highway conditions outside Auckland public transport scope

## Do not use this for

- Auckland public transport stops, departures, vehicles, or service alerts; use `at-transport`
- Auckland Transport local-road events unless a separate AT road-events skill/source is added
- Local-road, district-road, or council-only closures not present in NZTA Journey Planner
- Route planning, turn-by-turn directions, tolls, driver licensing, or vehicle account actions
- Reporting incidents, subscribing to My Journeys alerts, or changing any NZTA data
- Historical road-condition claims beyond what the live source currently returns

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `closures` for the national state-highway overview and add `--region` when the user names a region
3. Use `--type closure`, `--type roadworks`, or `--type incident` to reduce noise
4. Use `incident <id>` when an exact NZTA Journey Planner event id is known
5. Use `cameras --region <region>` for traffic camera image URLs and camera status
6. Use `routes` or `regions` to discover Journey Planner route and region names
7. Use `--json` for agent chaining, comparisons, alerts, or structured reports
8. Mention that the upstream source is NZTA / Waka Kotahi Journey Planner and that local roads may require council sources

## CLI

Run with:

```bash
python3 skills/nz-road-closures/scripts/cli.py <command> [flags]
```

### Commands

- `closures [--region REGION] [--type closure|roadworks|incident] [--limit N] [--json]` - current NZTA road closures, works, incidents, hazards, and warnings
- `incident <id> [--json]` - detail for one current NZTA road event
- `cameras [--region REGION] [--limit N] [--json]` - NZTA traffic cameras, including image URL when available
- `routes [--region REGION] [--limit N] [--json]` - known NZTA highway journeys/routes
- `region <region> [--type closure|roadworks|incident] [--limit N] [--json]` - current road events filtered to one Journey Planner region
- `regions [--json]` - Journey Planner region names and ids

Examples:

```bash
python3 skills/nz-road-closures/scripts/cli.py closures --limit 10
python3 skills/nz-road-closures/scripts/cli.py closures --region Waikato --type roadworks --json
python3 skills/nz-road-closures/scripts/cli.py incident 541438 --json
python3 skills/nz-road-closures/scripts/cli.py cameras --region Canterbury --limit 5
python3 skills/nz-road-closures/scripts/cli.py routes --region Wellington --json
python3 skills/nz-road-closures/scripts/cli.py regions
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Upstream source: NZTA / Waka Kotahi Journey Planner and Traffic and Travel APIs
- No API key, username, password, cookie, or browser automation is required
- Default scope is NZTA state highways New Zealand-wide
- The Journey Planner help text says local roads should be checked with the relevant local or regional council when a journey includes local roads
- `at-transport` is public-transport focused and explicitly excludes traffic or road conditions, so this skill owns NZTA state-highway road events
- Treat results as live current snapshots; closures and works can be postponed, cancelled, or changed at short notice
