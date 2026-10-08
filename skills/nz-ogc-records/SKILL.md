---
name: nz-ogc-records
description: "Search NZ public OGC API Records and CKAN catalogues for datasets, distribution URLs, licences and update metadata. Use to discover Auckland Council, Auckland Transport, Waka Kotahi, NIWA and data.govt.nz datasets before querying their linked services."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Auckland Council; Auckland Transport; NZ Transport Agency Waka Kotahi; NIWA; data.govt.nz"
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
  thecolab.source_url: "https://data-aucklandcouncil.opendata.arcgis.com/api/search/v1/collections/dataset/items"
  thecolab.allowed_domains: "data-aucklandcouncil.opendata.arcgis.com,data-atgis.opendata.arcgis.com,opendata-nzta.opendata.arcgis.com,data-niwa.opendata.arcgis.com,catalogue.data.govt.nz,www.arcgis.com"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ OGC Records

Search NZ catalogue metadata with the stdlib Python CLI in `scripts/cli.py`.
Use this to find datasets and distribution URLs before querying the data service.

## Commands

```bash
python3 skills/nz-ogc-records/scripts/cli.py catalogues --json
python3 skills/nz-ogc-records/scripts/cli.py search flood --catalogue auckland-council --limit 5 --json
python3 skills/nz-ogc-records/scripts/cli.py search traffic --catalogue waka-kotahi --bbox 174.4,-37.2,175.3,-36.4 --limit 5 --format geojson
python3 skills/nz-ogc-records/scripts/cli.py get auckland-transport eeb0839fbd594c9e87189df5c84c2543 --json
```

- `catalogues` probes all five endpoints and reports availability and upstream
  matched counts. An unavailable endpoint is a status row, not a crash.
- `search TEXT` searches all catalogues by default. Repeat `--catalogue` to
  select several. Names: `auckland-council`, `auckland-transport`, `waka-kotahi`,
  `niwa`, `data-govt-nz`. `--limit` is **per catalogue**, from 1 to 100.
  The CLI returns one bounded page per catalogue and exposes `next_urls` without
  following them. Upstream matching/ranking may include related terms.
- `get CATALOGUE RECORD_ID` accepts the record's `id` from search. Hub can resolve
  an item ID to a layer ID with a suffix such as `_0`; retain the returned ID.
- `--bbox minLon,minLat,maxLon,maxLat` filters catalogue coverage in WGS84.
  Use increasing bounds; split antimeridian searches into two boxes. Extents
  can be broad or absent and do not establish local data coverage. CKAN bbox
  search is unverified and returns `unsupported_bbox` rather than ignoring it.
- Search and get accept `--format geojson`; geometries describe **metadata
  coverage**, not dataset features. Records without geometry have `null` geometry.

## Workflow and interpretation

1. Check `catalogues` when selecting a source. At verification on 8 October
   2026 the four OGC catalogues were available; data.govt.nz's keyless CKAN
   endpoint returned a bot challenge and was unavailable from this network.
2. Search relevant catalogues, inspect `catalogues`, `partial`, and `warnings`,
   and use returned IDs with `get` to review the record.
3. Check each record's `licence`, `licence_info`, attribution, description and
   dates. NIWA includes non-commercial licences. `updated_at` is a catalogue
   modification date; `latest_data` stays null unless the source explicitly
   provides it. Do not label old survey data current because metadata changed.
4. Hand FeatureServer/MapServer URLs in `distribution_urls` to `nz-arcgis` when
   available. ImageServer URLs require a raster-capable client. File downloads
   can be large; review their format before downloading.

JSON envelopes, catalogue statuses, records and distributions carry `source_url`,
`publisher`, `licence`, `retrieved_at` (UTC), and `latest_data`. Unknown licence and
latest data are null. Mixed-source envelopes have null licence/latest data; use
record values. No keys or sign-in are used. Linked distributions are surfaced,
not fetched or checked for their own availability or authentication requirements.
Search may succeed with partial results; all unavailable catalogues produce a
non-zero search exit. Empty results from available sources are valid.

Read [references/source-notes.md](references/source-notes.md) for endpoint,
fixture and parser details. Run `scripts/test_contract.py` for deterministic
checks and `scripts/smoke_test.py` for bounded live verification.
