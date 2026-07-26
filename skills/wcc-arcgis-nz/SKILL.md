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
  thecolab.allowed_domains: "data-wcc.opendata.arcgis.com,data-gwrc.opendata.arcgis.com,www.arcgis.com,hub.arcgis.com,services.arcgis.com,services1.arcgis.com,services2.arcgis.com,gis.wcc.govt.nz,giswebprd.gw.govt.nz,mapping.gw.govt.nz,mapping1.gw.govt.nz,maps.gw.govt.nz,gis.wellingtonwater.co.nz,gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com"
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
- A task needs ArcGIS item/layer metadata, a raw count or object-ID page, or a
  raw MapServer point identify for agent-side composition
- A task needs pedestrian/cyclist/vehicle count locations or recent counts from
  WCC's VivaCity transport sensors

## Do not use this for

- NZTA state-highway data (use `nz-road-closures` or `nzta-crash-data-nz`)
- LINZ national datasets (use `linz-data-service`)
- Real-time transit vehicle positions (use `nz-buses` / `nz-trains`)
- Any write, upload, or account action

## Commands

```bash
python3 skills/wcc-arcgis-nz/scripts/cli.py search "flood hazard" --limit 5 --start 1
python3 skills/wcc-arcgis-nz/scripts/cli.py search river --portal gwrc --type "Feature Service" --start 11 --json
python3 skills/wcc-arcgis-nz/scripts/cli.py item 8292f1b6b6144a73ae2bc81fd795f067 --json
python3 skills/wcc-arcgis-nz/scripts/cli.py layers 8292f1b6b6144a73ae2bc81fd795f067
python3 skills/wcc-arcgis-nz/scripts/cli.py describe https://mapping1.gw.govt.nz/arcgis/rest/services/GW/Emergencies_P/MapServer --layer-id 10 --json
python3 skills/wcc-arcgis-nz/scripts/cli.py query 8292f1b6b6144a73ae2bc81fd795f067 --bbox "174.75,-41.35,174.82,-41.27" --limit 20 --json
python3 skills/wcc-arcgis-nz/scripts/cli.py query https://services1.arcgis.com/CPYspmTk3abe6d7i/arcgis/rest/services/dp_ihp_recommended_flood_hazard_overlays/FeatureServer/51 --count --json
python3 skills/wcc-arcgis-nz/scripts/cli.py identify https://gis.wellingtonwater.co.nz/server1/rest/services/Modelling/WCC100yrCC2025FloodDepths_FB/MapServer --point 174.78,-41.29 --layer-id 0 --no-geometry --json
python3 skills/wcc-arcgis-nz/scripts/cli.py sensors --search cuba --json
python3 skills/wcc-arcgis-nz/scripts/cli.py sensors-latest --limit 20 --json
```

- `search KEYWORD [--portal wcc|gwrc] [--type TYPE] [--limit N] [--start N] [--json]` — org-scoped catalogue search, newest first; use `next_start` for the next upstream page
- `item ITEM_ID [--json]` — normalized catalogue metadata including ownership, organisation, access, licence, description, tags, timestamps, size, and the raw item URL; `service_url` is set only for Feature/Map Service items
- `layers ITEM_OR_URL [--json]` — layers/tables of a verified WCC/GWRC Feature/Map service
- `describe SERVICE [--layer-id N] [--json]` — normalized service/layer metadata: fields, aliases, types, descriptions/units when published, extent, spatial reference, capabilities, geometry type, object-ID field, and record limit
- `query LAYER [--layer-id N] [--where SQL] [--bbox minLon,minLat,maxLon,maxLat] [--fields F1,F2] [--limit N] [--count|--ids-only] [--no-geometry] [--offset N] [--order-by EXPR] [--geometry-precision N] [--max-allowable-offset N] [--json]` — GeoJSON features or a normalized count/object-ID envelope
- `identify SERVICE --point LON,LAT [--layer-id N] [--tolerance N] [--no-geometry] [--json]` — raw MapServer identify results for selected/all layers
- `sensors [--search TEXT] [--limit N] [--json]` — transport sensor countlines with coordinates and data spans
- `sensors-latest [--month YYYY-MM] [--search TEXT] [--limit N] [--json]` — counts per countline and transport class for the newest published day, with a monthly daily average and explicit stale/missing observations

## Notes

- Licence: CC BY 4.0 — attribute "Wellington City Council" (or GWRC for `--portal gwrc` data;
  Wellington Water for `gis.wellingtonwater.co.nz` flood model layers)
- GWRC hazard and climate layers (sea level rise, storm surge, regional flood hazard,
  `Emergencies_P` landslide/liquefaction/tsunami, `Modelled_Climate_Change`) live on
  `mapping1.gw.govt.nz`; Wellington Water stormwater flood depth models live on
  `gis.wellingtonwater.co.nz` — both are accepted by `layers`/`query`
- Searches are scoped to each council's ArcGIS organisation; hub-wide search APIs
  return a global catalogue and are deliberately not used
- Layer queries require HTTPS, exact declared hosts, and a verified WCC/GWRC ArcGIS
  organisation id; unrelated global ArcGIS items, malformed service paths, and
  redirect host changes are refused
- Ordinary `query` output stays GeoJSON-shaped. `--count` and `--ids-only` are
  mutually exclusive and return JSON envelopes. Paging and precision controls
  map directly to ArcGIS REST without adding scientific interpretation.
- `--fields` accepts `*` or comma-separated field identifiers. `--order-by`
  accepts comma-separated field identifiers with optional `ASC`/`DESC`.
  Qualified names may use valid non-empty dotted segments; SQL punctuation,
  empty segments, and malformed directions are rejected before network access.
- `identify` is a raw MapServer identify primitive, not a hazard assessment,
  safety recommendation, or conclusion. Points and bounding boxes are WGS84;
  non-finite and out-of-range coordinates are refused before network access.
- Invalid arguments, type errors, mutually exclusive modes, blocked sources,
  and malformed upstream responses use a structured JSON error on stderr.
- `sensors-latest` downloads the month's count file (~12 MB) — WCC refreshes it at
  least monthly and in practice daily; expect the newest day to be about one day old
- A missing countline/class row is not assumed to mean zero traffic:
  `latest_date_count` is `null`, `stale` is true, and `latest_observed_date` plus the
  metadata's `LATEST` date are returned for auditability
- Query responses cap at the server's transfer limit (2000); a `truncated` flag says
  when to narrow with `--where`/`--bbox`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Endpoint discovery, org IDs, and S3 layout: `references/source-notes.md`
