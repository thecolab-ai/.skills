---
name: niwa-rivers-nz
description: "Query NIWA River Maps hydrology predictions, hourly station metadata, regional flood product coverage and Fish Passage surveys without keys. Use for NZ river flow and flood context, with explicit limits on account-gated observations and rasters."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Earth Sciences New Zealand (NIWA)"
  thecolab.source_type: "official"
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
  thecolab.source_url: "https://data.niwa.co.nz/products/hydro-data-hourly"
  thecolab.allowed_domains: "data.niwa.co.nz,shiny.niwa.co.nz,geoserver.niwa.co.nz,d17fc0a885.execute-api.ap-southeast-2.amazonaws.com"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NIWA Rivers NZ

Use `scripts/cli.py` for NIWA freshwater source discovery, hourly series metadata,
River Maps hydrology predictions, regional flood product coverage and public
Fish Passage surveys.
Python 3.10+; stdlib only; no keys, accounts or browser required by the CLI.

```bash
python3 skills/niwa-rivers-nz/scripts/cli.py sources --json
python3 skills/niwa-rivers-nz/scripts/cli.py stations --json
python3 skills/niwa-rivers-nz/scripts/cli.py stations --region Canterbury --bbox 170,-44,174,-42 --format geojson
python3 skills/niwa-rivers-nz/scripts/cli.py flow --station 90612 --from 2026-03-01 --to 2026-03-02 --json
python3 skills/niwa-rivers-nz/scripts/cli.py rivers --near 174.7,-36.9 --json
python3 skills/niwa-rivers-nz/scripts/cli.py flood-hazard --region Auckland --bbox 174.6,-37,174.9,-36.7 --format geojson
python3 skills/niwa-rivers-nz/scripts/cli.py fish-passage --bbox 174.6,-37,174.9,-36.7 --limit 5 --json
```

- `sources` returns a maintained source directory with access status and provenance.
- `stations` reads all public hourly station/parameter product listings, paging
  up to 10 pages. Each result is a series listing, so a station may occur more
  than once. `station` is the numeric ID accepted by `flow`. Dates describe
  available series coverage; they do not imply a real-time feed.
- `flow` exits **4** with a structured access error: the advertised DataHub
  file API requires customer authentication. It accepts no credentials.
- `rivers` is opt-in: invoke it explicitly to query River Maps' public Shiny interface, then rank reaches by
  distance to the requested point. Default `--metric "Mean Flow"`, `--limit 5`.
  Seven hydrology metrics are listed by `rivers --help`. `--radius-km` (0.1–10,
  default 5) sets the half-size of a local search box; `--bbox` overrides it.
  Returns the app's rounded map values, units and metric description. Metrics
  are static model estimates, not observed flow or forecasts.
- `flood-hazard` returns regional **product metadata and coverage footprints**.
  GeoJSON polygons are product coverage bounding boxes, not inundation extents.
  Depth and depth–velocity rasters require account/licence access and raster tools.
- `fish-passage` fetches keyless WFS survey points. `--limit` is 1–1000;
  `--offset` pages the matched records. Inspect `meta.truncated` and
  `meta.number_matched`; surveys are not a complete structure inventory.

Spatial commands accept WGS84 `--bbox minLon,minLat,maxLon,maxLat` and
`--format geojson` (implies JSON). Station and flood catalogue filtering is local:
point containment / coverage-box intersection. Station `--region` uses point-in-
polygon membership in NIWA's generalised regional council boundary layer.
River Maps uses an upstream map view plus local geometry-box intersection
and approximate point-to-line distances. The app's stream-order visibility
threshold is returned in `meta.visibility`; nearby results may omit small
streams. Fish Passage bbox intersection occurs upstream using explicit
longitude/latitude CRS84. Negative-leading boxes use `--bbox=-180,-90,180,90`.

JSON returns `meta` and an array `results`; GeoJSON returns a `FeatureCollection`
with `meta`. Product records carry their page URL, publisher, licence,
retrieval time and source-stated series end or catalogue update timestamp.
Errors return one JSON envelope and stable exit codes, never an empty success.

Read [references/source-notes.md](references/source-notes.md) for source schemas,
licences and access evidence. Run `scripts/test_contract.py` for deterministic
checks and `scripts/smoke_test.py` for bounded live probes. River Maps checks a 50-second deadline
between requests; polls time out after up to 30 seconds and retry once on timeout
within that deadline. Other calls time out after 10 seconds (session close:
2 seconds). Shared HTTP retries may extend elapsed time.

Use `lawa-nz` for observed council/LAWA river information, `gwrc-hilltop-nz`
for Wellington Hilltop observations and `niwa-coastal-nz` for NIWA coastal
ArcGIS data. Use `nz-arcgis` for supported council hazard polygons. This skill
keeps those existing connectors separate.
