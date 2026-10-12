---
name: flamingo-gbfs
description: "Read Flamingo public Auckland GBFS 3.0 feeds for the feed list, system licence, and current vehicle positions. Use for keyless scooter locations and range in metres. Do not use for trip histories, trajectories, Ride Report aggregates, or GTFS timetables."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Flamingo"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "60s"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://data.rideflamingo.com/gbfs/3/auckland/gbfs.json"
  thecolab.allowed_domains: "data.rideflamingo.com"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Flamingo Auckland GBFS

Read the public Auckland GBFS 3.0 files on `data.rideflamingo.com`. Use
`scripts/cli.py`. Every data command accepts `--json`. Human text is the default.

`vehicles` returns the current `vehicle_status` snapshot only. It does not
return trips, routes, or rental deep links. Wait for the feed `ttl` before
requesting that same file again. Read `references/source-notes.md` for the
verified licence, timestamps, and bounds.

## Commands

```bash
python3 scripts/cli.py discovery --json
python3 scripts/cli.py system --json
python3 scripts/cli.py vehicles --limit 20 --json
python3 scripts/cli.py vehicles --bbox 174.6,-37.0,174.9,-36.7 --limit 5 --format geojson
```

`discovery` lists feeds whose URLs stay on the Auckland GBFS path. `system`
reads `license_id` from `system_information`. `vehicles` reads current
positions. `--bbox` keeps points inside the box after that single download.
`--limit` is 1 to 100. `--format geojson` emits a WGS84 FeatureCollection.

## Boundaries

- One command performs one GET, or reuses a response still inside its feed ttl.
- Vehicle range stays in metres. Timestamps keep the source offset.
- The discovery file's `last_updated` is not the vehicle snapshot time.
- Ride Report, GTFS, station files, alerts, and geofences are out of scope.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic contract and parser fixtures
- `scripts/smoke_test.py` — fixture checks and a bounded live probe
- `references/source-notes.md` — licence, ttl, and field rules
