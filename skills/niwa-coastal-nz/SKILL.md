---
name: niwa-coastal-nz
description: "Search and query NIWA (National Institute of Water and Atmospheric Research) public ArcGIS open data through a lightweight no-login CLI: org-scoped dataset search plus GeoJSON layer queries for the Coastal Sensitivity Index (erosion and inundation), beach exposure, coastal landform and hinterland classification, and other national coastal and climate layers. Use when the task involves NZ coastal hazard sensitivity, coastal classification, or NIWA open geospatial datasets. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "NIWA"
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
  thecolab.source_url: "https://data-niwa.opendata.arcgis.com/"
  thecolab.allowed_domains: "data-niwa.opendata.arcgis.com,www.arcgis.com,hub.arcgis.com,services.arcgis.com,services3.arcgis.com,gis.niwa.co.nz"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NIWA Coastal NZ

## Goal

Search and query NIWA's public ArcGIS open data — the national Coastal
Sensitivity Index, beach exposure, and coastal classification layers among
~1,400 open items — through a deterministic read-only CLI with human and JSON
output.

## Use this when

- A task needs national coastal hazard sensitivity layers (CSI erosion, CSI
  inundation), beach exposure, coastal landform type, or hinterland
  characteristics as GeoJSON
- A task needs to discover what datasets NIWA publishes openly

## Do not use this for

- Weather forecasts or marine conditions (use `metservice-nz`)
- Tide predictions (use `nz-tides-surf`)
- Sea-level rise projections per coastal site (use `searise-nz`)
- Regional council hazard layers (use `wcc-arcgis-nz` for Wellington)
- Any write, upload, or account action

## Commands

```bash
python3 skills/niwa-coastal-nz/scripts/cli.py search "coastal sensitivity" --limit 5
python3 skills/niwa-coastal-nz/scripts/cli.py layers c894b53b102f4f9db55278f7572ca4f6
python3 skills/niwa-coastal-nz/scripts/cli.py query c894b53b102f4f9db55278f7572ca4f6 --bbox "174.5,-41.5,175.2,-40.9" --limit 20 --json
```

- `search KEYWORD [--type TYPE] [--limit N] [--json]` — org-scoped catalogue search, newest first
- `layers ITEM_OR_URL [--json]` — layers/tables of a verified NIWA Feature/Map service
- `query LAYER [--layer-id N] [--where SQL] [--bbox minLon,minLat,maxLon,maxLat] [--fields F1,F2] [--limit N] [--json]` — GeoJSON features; LAYER is a verified NIWA item id, HTTPS service URL, or HTTPS layer URL

## Notes

- Licence: CC BY 4.0 — attribute NIWA (item pages carry the canonical statement)
- Searches are scoped to NIWA's ArcGIS organisation (`fp1tibNcN9mbExhG`);
  hub-wide search APIs return a global catalogue and are deliberately not used
- Layer queries require HTTPS and either a NIWA-owned host
  (`gis.niwa.co.nz`) or an Esri service path under the NIWA tenant; anything
  else is refused (exit 7)
- Useful verified items: CSI erosion `c894b53b102f4f9db55278f7572ca4f6`;
  the COAST folder on `gis.niwa.co.nz/server/rest/services` carries the
  coastal classification MapServers
- `truncated: true` means the server transfer limit was hit — narrow with
  `--where`/`--bbox`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Org id discovery, host survey, and licence notes: `references/source-notes.md`
