---
name: nz-point-clouds
description: "Find New Zealand airborne LiDAR point-cloud collections on OpenTopography and list bounded public file URLs and sizes. Use for catalogue search, dataset licence, capture interval, and LAZ tile discovery. Do not use for LINZ DEM or DSM rasters, imagery tiles, elevation sampling, or point-cloud downloads."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "geospatial"
  thecolab.source_owner: "OpenTopography"
  thecolab.source_type: "mixed"
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
  thecolab.source_url: "https://portal.opentopography.org/API/otCatalog"
  thecolab.allowed_domains: "portal.opentopography.org,opentopography.s3.sdsc.edu"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ point clouds

Search OpenTopography for New Zealand airborne LiDAR point-cloud collections
and, when the dataset states CC BY 4.0, list a short page of public file URLs
and sizes. Python 3.10+, stdlib plus the repository fetch helper. No access
key and no point-cloud download.

`nz-stac` reads LINZ elevation and imagery Cloud Optimised GeoTIFFs. This
skill does not sample elevation, merge DEM and DSM products, or fetch LAZ
bodies. `linz-data-service` reads the LINZ Data Service catalogue and public
feature layers, not these bulk point-cloud keys.

Use `scripts/cli.py`. Every data command accepts `--json`. Human text is the
default. `collections` and `info` also accept `--format geojson`. Read
`references/source-notes.md` for the request bounds, licence gate, and errors.

## Commands

```bash
python3 skills/nz-point-clouds/scripts/cli.py collections --bbox 174.4,-37.3,175.1,-36.5 --limit 5 --json
python3 skills/nz-point-clouds/scripts/cli.py info OTLAS.042025.2193.1 --json
python3 skills/nz-point-clouds/scripts/cli.py info OTLAS.042025.2193.1 --format geojson
python3 skills/nz-point-clouds/scripts/cli.py files OTLAS.042025.2193.1 --limit 5 --json
```

`collections` requires a WGS84 `--bbox` inside longitude 165 to 179.5 and
latitude -48 to -33. It calls the point-cloud catalogue only. The catalogue
does not state a licence, so the result omits one.

`info` reads one dataset page and reports the stated licence, capture
interval, citation, and boundary box. A dataset whose page says the licence
is not provided is still returned. It is not treated as CC BY 4.0.

`files` lists at most 50 keys from that dataset's public prefix. It runs only
after `info` metadata states `CC-BY-4.0`. Any other stated licence, including
`Not-Provided`, stops before the file list. Pass `--page` with the previous
`next_page` value to read another slice. `--suffix laz` filters the current
page; it does not search the whole collection.

## Boundaries

- One catalogue or dataset command makes one request. `files` makes two: the
  dataset page, then one list page.
- Responses are capped at 512 KiB for the catalogue and 256 KiB for a dataset
  page or list page. Each request times out after 10 seconds.
- File results are HTTPS URLs and byte sizes. There is no download command.
- Attribute OpenTopography and the dataset citation when you use the data.
  The citation is on the `info` result.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic contract and parser fixtures
- `scripts/smoke_test.py` — fixture checks and a bounded live probe
- `references/source-notes.md` — source envelope, licence gate, and error semantics
