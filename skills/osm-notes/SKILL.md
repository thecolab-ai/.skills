---
name: osm-notes
description: "Read OpenStreetMap map notes inside a small WGS84 bounding box. Use when the task needs open or recently closed OSM notes, note text, status, and coordinates for a place such as central Auckland. Read-only GET of the notes API. Do not use for Overpass places, geocoding, or creating, commenting on, closing, or reopening notes."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "OpenStreetMap contributors"
  thecolab.source_type: "community"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://api.openstreetmap.org/api/0.6/notes.json"
  thecolab.allowed_domains: "api.openstreetmap.org,www.openstreetmap.org"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# OSM notes

Read public OpenStreetMap map notes for one small area. The command is a single read-only GET. It does not create, comment on, close, or reopen notes.

Use `scripts/cli.py`. Details of the upstream parameters, licence, and omitted account fields are in `references/source-notes.md` and `references/api-notes.md`.

## Use this when

- You need OSM notes, their status, coordinates, and comment text inside a small box.
- The place is a neighbourhood-scale area, such as central Auckland.

## Do not use this when

- You need shops, amenities, or other map objects. Use `osm-nz` and the Overpass API.
- You need geocoding. This skill does not call Nominatim or Photon.
- You want to write to a note. There is no create, comment, close, or reopen command.

## Command

```bash
python3 scripts/cli.py notes --bbox 174.76,-36.86,174.78,-36.84 --limit 2 --json
```

`--bbox` is `minLon,minLat,maxLon,maxLat` in WGS84. Each side must be at most 0.05 degrees. For a box that starts with a negative longitude, use `--bbox=-180,-90,-179.96,-89.96`.

`--limit` is 1 to 20. The default is 10. `--closed-days` defaults to 0, which asks for open notes only. Values 1 to 7 also include notes closed within that many days. The API applies that filter. This skill does not request every historical closed note.

`--format geojson` prints a GeoJSON FeatureCollection with the same provenance `meta`. `--json` prints the `meta` / `results` envelope. Account identifiers from the upstream payload are omitted. Comment text is the note author's words.

Offline checks can replay a file stored inside this skill:

```bash
python3 scripts/cli.py notes --bbox 174.76,-36.86,174.78,-36.84 --limit 2 --fixture tests/fixtures/notes-positive.json --json
```

Run `scripts/test_contract.py` and `scripts/smoke_test.py` after changing the parser.
