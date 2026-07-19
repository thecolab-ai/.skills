---
name: safeswim-nz
description: "Query SafeSwim NZ public swimming-location water quality, swimming conditions, wastewater overflow alerts, and hour-by-hour forecast data through a no-login REST API. Use when the task involves SafeSwim-supported NZ beach/lake swimming safety, water quality (GREEN/AMBER/RED/RED+/BLACK), lifeguard/patrol status, safety hazards, facilities, or per-location forecasts. Read-only."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Safeswim"
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
  thecolab.source_url: "https://safeswim.org.nz/api"
  thecolab.allowed_domains: "safeswim.org.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# SafeSwim NZ

## Goal

Query live SafeSwim NZ swimming-location water-quality and swimming-condition data with a deterministic CLI and JSON output.

## Use this when

- A user asks whether it's safe to swim at a SafeSwim-supported NZ beach, lake, or swimming spot today
- A user wants water quality status (GREEN/AMBER/RED/RED+/BLACK) for SafeSwim locations
- A user asks about wastewater overflow alerts or swimming hazards
- A user wants hour-by-hour swimming forecasts (water temp, wind, UV, tide height)
- A user needs nearby SafeSwim locations, optionally filtered by warning severity
- A workflow needs machine-readable swimming-location safety data

## Do not use this for

- General freshwater monitoring outside SafeSwim coverage; use `lawa-nz` for broader river/lake sites
- Tide predictions alone; use `nz-tides-surf` for LINZ tide tables
- Surf conditions; use `nz-tides-surf` for SwellMap surf data
- Swimming spots outside the SafeSwim API coverage area
- Historical water-quality records beyond what the live API returns
- Safety-critical decisions without also checking local signage and conditions

## Preferred workflow

1. Run `scripts/cli.py list` to discover SafeSwim locations, optionally filtered by search text
2. Use `detail <slug>` for a specific location with hour-by-hour forecast data
3. Use `nearby <lat> <lon>` to find SafeSwim locations close to a coordinate
4. Use `--min-risk RED` when the user wants warning-level or worse locations, not safe-swim recommendations
5. Use `--json` for agent chaining, alerts, or structured reports
6. Mention that SafeSwim data is live and can change rapidly after rainfall events

## CLI

Run with:

```bash
python3 skills/safeswim-nz/scripts/cli.py <command> [flags]
```

### Commands

- `list [--search TEXT] [--limit N] [--json]` — list SafeSwim locations with quality status and patrol info
- `detail <slug> [--json]` — full detail for a location: forecasts, tags, alerts, facilities
- `nearby <lat> <lon> [--radius N] [--min-risk GREEN|AMBER|RED|RED+|BLACK] [--limit N] [--json]` — SafeSwim locations near a coordinate ordered by distance; `--min-quality` is accepted as a compatibility alias

Examples:

```bash
python3 skills/safeswim-nz/scripts/cli.py list --search takapuna --limit 5
python3 skills/safeswim-nz/scripts/cli.py detail takapuna --json
python3 skills/safeswim-nz/scripts/cli.py nearby -36.8485 174.7633 --radius 10 --min-risk RED
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

- No API key, username, password, cookie, or browser automation is required
- The SafeSwim API is public and read-only at `safeswim.org.nz/api`
- Water quality can change rapidly after rainfall — treat results as current snapshots
- GREEN = lower risk, AMBER = caution, RED/RED+ = unsafe, BLACK = wastewater overflow
- Not all locations provide the full forecast array; some data arrays may be sparse
- SafeSwim covers only locations returned by the live API; it is not an all-NZ waterway catalogue
- The CLI fetches the full location list once and filters in-process; repeated hits within a second reuse the cached fetch
