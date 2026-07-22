---
name: geonet-nz
description: "Query GeoNet New Zealand public earthquake, volcano alert, GeoNet news, and Tilde sensor endpoints through a lightweight no-login CLI. Use when the task involves recent NZ earthquakes, felt/MMI-filtered quakes, earthquake detail by publicID, volcanic alert levels, volcanic activity bulletins, GeoNet public geohazard updates, coastal tsunami gauge water heights, or DART deep-ocean buoy readings. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "GeoNet"
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
  thecolab.source_url: "https://api.geonet.org.nz/"
  thecolab.allowed_domains: "api.geonet.org.nz,tilde.geonet.org.nz"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# GeoNet NZ

## Goal

Query public GeoNet geohazard feeds with deterministic CLI commands and JSON output.

## CLI

```bash
python3 skills/geonet-nz/scripts/cli.py quakes --mmi 3 --limit 10
python3 skills/geonet-nz/scripts/cli.py quake 2026p386918 --json
python3 skills/geonet-nz/scripts/cli.py volcanoes --json
python3 skills/geonet-nz/scripts/cli.py news --limit 5
python3 skills/geonet-nz/scripts/cli.py tilde-stations coastal
python3 skills/geonet-nz/scripts/cli.py tilde-latest coastal WLGT --window 30m --json
```

Commands:

- `quakes [--mmi N] [--min-mag N] [--limit N] [--json]` - recent earthquakes from GeoNet's quake feed
- `quake PUBLIC_ID [--json]` - detail lookup for a publicID
- `volcanoes [--json]` - current volcanic alert levels
- `news [--limit N] [--json]` - recent GeoNet news/bulletins
- `tilde-domains [--json]` - Tilde sensor data domains (coastal tsunami gauges, DART buoys, envirosensor, geomag, gnss, ...)
- `tilde-stations DOMAIN [--json]` - stations with coordinates and series names for one Tilde domain
- `tilde-latest DOMAIN STATION [--name NAME] [--window 30m|6h|1d|2d|7d|30d] [--json]` - latest reading plus window min/max; picks the freshest series when `--name` is omitted

Notes: Tilde readings are UTC. DART buoys report `water-height` only during tsunami
events; routine reporting is 15-minute `water-height`/pressure summaries, and an
offline buoy is reported with its last-transmission time rather than an empty success.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
