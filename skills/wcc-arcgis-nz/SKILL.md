---
name: wcc-arcgis-nz
description: "Search and query Wellington City Council and Greater Wellington Regional Council ArcGIS open data through a lightweight no-login CLI: org-scoped dataset search, FeatureServer/MapServer layer listing and GeoJSON queries with attribute and bounding-box filters, and Pōneke Travel Insights transport sensor countline locations and counts. Use when the task involves Wellington open geospatial data such as flood or coastal hazard layers, road network, community facilities, or pedestrian/vehicle movement counts. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Wellington City Council"
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
  thecolab.source_url: "https://data-wcc.opendata.arcgis.com/"
  thecolab.allowed_domains: "data-wcc.opendata.arcgis.com,data-gwrc.opendata.arcgis.com,www.arcgis.com,hub.arcgis.com,services1.arcgis.com,services2.arcgis.com,gis.wcc.govt.nz,mapping.gw.govt.nz,gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# WCC ArcGIS NZ

## Goal

Search and query Wellington City Council and Greater Wellington Regional Council
ArcGIS open data — flood/coastal hazard overlays, road network, community
facilities, and the Pōneke Travel Insights transport sensors — through a
deterministic read-only CLI with human and JSON output.

## Use this when

- A task needs Wellington-region open geospatial layers (flood hazard, coastal
  inundation, roads, facilities, district plan overlays) as GeoJSON
- A task needs to discover what datasets WCC or GWRC publish (`--portal gwrc`)
- A task needs pedestrian/cyclist/vehicle count locations or recent counts from
  WCC's VivaCity transport sensors

## Do not use this for

- NZTA state-highway data (use `nz-road-closures` or `nzta-crash-data-nz`)
- LINZ national datasets (use `linz-data-service`)
- Real-time transit vehicle positions (use `nz-buses` / `nz-trains`)
- Any write, upload, or account action

## Commands

```bash
python3 skills/wcc-arcgis-nz/scripts/cli.py search "flood hazard" --limit 5
python3 skills/wcc-arcgis-nz/scripts/cli.py search river --portal gwrc --type "Feature Service" --json
python3 skills/wcc-arcgis-nz/scripts/cli.py layers 8292f1b6b6144a73ae2bc81fd795f067
python3 skills/wcc-arcgis-nz/scripts/cli.py query 8292f1b6b6144a73ae2bc81fd795f067 --bbox "174.75,-41.35,174.82,-41.27" --limit 20 --json
python3 skills/wcc-arcgis-nz/scripts/cli.py sensors --search cuba --json
python3 skills/wcc-arcgis-nz/scripts/cli.py sensors-latest --limit 20 --json
```

- `search KEYWORD [--portal wcc|gwrc] [--type TYPE] [--limit N] [--json]` — org-scoped catalogue search, newest first
- `layers ITEM_OR_URL [--json]` — layers/tables of a Feature/Map service
- `query LAYER [--layer-id N] [--where SQL] [--bbox minLon,minLat,maxLon,maxLat] [--fields F1,F2] [--limit N] [--json]` — GeoJSON features; LAYER is an item id, service URL, or layer URL
- `sensors [--search TEXT] [--limit N] [--json]` — transport sensor countlines with coordinates and data spans
- `sensors-latest [--month YYYY-MM] [--search TEXT] [--limit N] [--json]` — counts per countline and transport class for the newest published day, with a monthly daily average for baseline comparison

## Notes

- Licence: CC BY 4.0 — attribute "Wellington City Council" (or GWRC for `--portal gwrc` data)
- Searches are scoped to each council's ArcGIS organisation; hub-wide search APIs
  return a global catalogue and are deliberately not used
- Layer queries only go to council/Esri hosts; other hosts are refused explicitly
- `sensors-latest` downloads the month's count file (~12 MB) — WCC refreshes it at
  least monthly and in practice daily; expect the newest day to be about one day old
- Query responses cap at the server's transfer limit (2000); a `truncated` flag says
  when to narrow with `--where`/`--bbox`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Endpoint discovery, org IDs, and S3 layout: `references/source-notes.md`
