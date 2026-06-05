---
name: geonet-nz
description: Query GeoNet New Zealand public earthquake, volcano alert, and GeoNet news endpoints through a lightweight no-login CLI. Use when the task involves recent NZ earthquakes, felt/MMI-filtered quakes, earthquake detail by publicID, volcanic alert levels, volcanic activity bulletins, or GeoNet public geohazard updates. Read-only; no authentication required.
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
```

Commands:

- `quakes [--mmi N] [--min-mag N] [--limit N] [--json]` - recent earthquakes from GeoNet's quake feed
- `quake PUBLIC_ID [--json]` - detail lookup for a publicID
- `volcanoes [--json]` - current volcanic alert levels
- `news [--limit N] [--json]` - recent GeoNet news/bulletins

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
