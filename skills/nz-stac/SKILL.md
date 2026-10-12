---
name: nz-stac
description: "Find LINZ elevation, coastal LiDAR, and aerial imagery collections and COG tiles from public NZ STAC catalogues. Use for DEM/DSM, coastal elevation footprints, RGB/infrared footprints, bbox tile searches and elevation point sampling guidance."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "geospatial"
  thecolab.source_owner: "Toitū Te Whenua Land Information New Zealand"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-STAC-HTTPS"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json"
  thecolab.allowed_domains: "nz-elevation.s3.ap-southeast-2.amazonaws.com,nz-imagery.s3.ap-southeast-2.amazonaws.com,nz-coastal.s3.ap-southeast-2.amazonaws.com"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ STAC

Find datasets and Cloud Optimised GeoTIFF (COG) tile URLs in LINZ's public
`nz-elevation`, `nz-imagery`, and `nz-coastal` AWS buckets, hosted in
`ap-southeast-2`. Python 3.10+, stdlib only; no AWS credentials, boto3, or
LINZ Data Service key. Coastal commands return collection metadata and COG
hrefs only. They do not download DEM or DSM rasters.

## Workflow

1. Run `collections` with the bucket kind and optional region. Copy the returned
   `collection` selector (kind plus published path), or use its HTTPS
   `collection.json` URL. `info` returns the upstream STAC id and full metadata.
2. Check capture interval, product and resolution with `info`. DEM represents
   terrain; DSM includes surface features. Use the source capture dates for
   freshness, rather than its processing/update date.
3. Use a small WGS84 bbox to find tiles. `--format geojson` emits a
   FeatureCollection of the actual STAC footprints. Assets are public HTTPS COG
   URLs. The helper fetches bounded JSON metadata only, never raster files.
4. For a terrain point, use an elevation DEM collection with `point`. Coastal
   collections are not accepted there. It returns
   `sampling_status=sampling_required`, `elevation=null`, the tile URL and a
   `gdallocationinfo` one-liner. Run that command with GDAL installed to sample
   remotely by HTTP range reads. Check nodata and the source vertical datum.
   The stdlib helper does not decode compressed GeoTIFFs or report an invented
   elevation. A tile footprint may contain nodata.

## Commands

Run from the repository root, or use an absolute path to `scripts/cli.py`.

```bash
python3 skills/nz-stac/scripts/cli.py collections --kind elevation --region auckland --json
python3 skills/nz-stac/scripts/cli.py collections --kind imagery --region auckland --json
python3 skills/nz-stac/scripts/cli.py collections --kind coastal --region auckland --limit 20 --json
python3 skills/nz-stac/scripts/cli.py info coastal:auckland/mangawhai-to-snells_2025/dem_1m/2193 --json
python3 skills/nz-stac/scripts/cli.py tiles coastal:auckland/mangawhai-to-snells_2025/dem_1m/2193 --bbox 174.59,-36.01,174.60,-36.00 --limit 5 --json
python3 skills/nz-stac/scripts/cli.py info elevation:auckland/auckland-part-1_2024/dem_1m/2193 --json
python3 skills/nz-stac/scripts/cli.py tiles elevation:auckland/auckland-part-1_2024/dsm_1m/2193 --bbox 174.715,-36.905,174.725,-36.895 --json
python3 skills/nz-stac/scripts/cli.py tiles elevation:auckland/auckland-north_2016-2018/dem_1m/2193 --bbox 174.715,-36.905,174.725,-36.895 --format geojson
python3 skills/nz-stac/scripts/cli.py tiles imagery:auckland/auckland_2024_0.075m/rgb/2193 --bbox 174.715,-36.905,174.725,-36.895 --format geojson
python3 skills/nz-stac/scripts/cli.py tiles imagery:auckland/auckland_2024_0.075m/rgbnir/2193 --bbox 174.715,-36.905,174.725,-36.895 --limit 5 --json
python3 skills/nz-stac/scripts/cli.py point --lon 174.72 --lat -36.9 --collection elevation:auckland/auckland-part-1_2024/dem_1m/2193 --json
```

Every data command supports `--json`; `tiles` and `point` also support
`--format geojson`. Human output is the default.

## Bounds and interpretation

- `--bbox` is `minLon,minLat,maxLon,maxLat`. Longitude comes first. Tile search
  supports mainland NZ Topo50 tile names in EPSG:2193; unsupported grids fail
  clearly. Chatham Islands need a different CRS.
- Collections default to 100 records, capped at 200 per request. Use `--offset`
  and `--limit` for another slice. `matched` is the catalogue count after region
  filtering. The coastal catalogue has more collections than the default page,
  so an unfiltered coastal listing is truncated. Listings derive year, resolution
  and product from published names and paths; licence is null until `info` or
  tile metadata supplies it. Hillshade paths stay `unknown` rather than DEM or DSM.
- `point` accepts elevation DEM and DSM collections only. A coastal selector is
  rejected. Use `tiles` for coastal COG hrefs. OpenAerialMap and Copernicus GFM
  are different publishers and are not kinds of this skill.
- Tile results default to 20, capped at 50. At most 100 nearby item JSON files
  are candidates; a larger bbox fails with a request to narrow it. `truncated`
  means at least one additional matching footprint exists. Results include
  `candidates` and `items_inspected`; there is no unbounded item crawl.
- JSON envelopes and records carry `source_url`, `publisher`, `licence`,
  `retrieved_at` (UTC) and `latest_data` (capture end, or the catalogue title's
  stated year range). Unknown metadata stays null.
- `point` returns all discovered touching tiles up to four, with an explicit
  truncation flag. `no_tile` means no intersecting tile in that collection.
  It does not mean the location has no elevation in other collections.

Read [references/source-notes.md](references/source-notes.md) for the static
STAC schema, tile-grid method, exact Auckland selectors and source limits.
Verify the skill with `scripts/test_contract.py` (deterministic fixtures) and
`scripts/smoke_test.py` (bounded live Auckland probes and 16-byte COG ranges).
