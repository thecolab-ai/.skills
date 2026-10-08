---
name: nz-arcgis
description: "Discover and query allowlisted New Zealand public-sector and utility ArcGIS services and layers, including Auckland, Christchurch, Dunedin and Hamilton assets, hazards and transport data. Use for service/layer metadata, counts and bounded WGS84 spatial extracts as JSON, GeoJSON or CSV, including PC120 map metadata."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "New Zealand public-sector and utility ArcGIS publishers"
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
  thecolab.source_url: "https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services"
  thecolab.allowed_domains: "apps.dunedin.govt.nz,arcgis.mfe.govt.nz,gis.ccc.govt.nz,gis.gns.cri.nz,gis.wcc.govt.nz,mahere.at.govt.nz,mapping.gw.govt.nz,mapping1.gw.govt.nz,maps.herengaanuku.govt.nz,mapspublic.aklc.govt.nz,mapspublic.aucklandcouncil.govt.nz,seasketch.doc.govt.nz,services-ap1.arcgis.com,services.arcgis.com,services1.arcgis.com,services2.arcgis.com,services3.arcgis.com,services5.arcgis.com,services6.arcgis.com,services9.arcgis.com,tiledimageservices1.arcgis.com,tiles.arcgis.com,wslgis.water.co.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ ArcGIS

Use `scripts/cli.py` to discover public ArcGIS REST services from verified New Zealand publishers, inspect layers and extract bounded spatial records. Python 3.10+, stdlib only; keyless and read-only.

## Workflow

1. Run `orgs` to select a publisher and inspect its verified roots.
2. Use `services ORG` then `layers ORG SERVICE` to discover layer URLs. A service name includes its server type, such as `PJ_Roadworks_MS/FeatureServer`. Enterprise services on another root use their full allowlisted HTTPS URL.
3. For Auckland hackathon data, use `layers --curated akl --problem F1` or read [references/layers-auckland.md](references/layers-auckland.md). Names, A/B grades, problem tags, licences and caveats are machine-readable in [references/layers-auckland.json](references/layers-auckland.json).
   Use `layers --curated nz --publisher dcc` for the wider selection; [references/layers-nz.md](references/layers-nz.md) and [references/layers-nz.json](references/layers-nz.json) document the additional council layers, Flooded NZ and PC120 services. `--publisher` filters either curated selection by organisation code.
4. Run `describe LAYER_URL` before choosing fields or an attribute filter; it includes fields, geometry type, record count and the upstream editing timestamp when published.
   Problem tags: F1 flooding/flow paths; T1 congestion; T2 near-miss safety; T3 incidents/roadworks; W1 construction and demolition materials; W2 reuse/repair/recycling; W3 illegal dumping.

5. Use `count` to size a selection, then `query` with a WGS84 bbox and small limit. Preserve the layer caveats when interpreting an extract.

## Commands

```bash
python3 skills/nz-arcgis/scripts/cli.py orgs --json
python3 skills/nz-arcgis/scripts/cli.py services at --json
python3 skills/nz-arcgis/scripts/cli.py layers at PJ_Roadworks_MS/FeatureServer --json
python3 skills/nz-arcgis/scripts/cli.py layers --curated akl --problem F1 --json
python3 skills/nz-arcgis/scripts/cli.py layers --curated nz --publisher ccc --json
python3 skills/nz-arcgis/scripts/cli.py services hcc --root 0 --max-requests 1 --json
python3 skills/nz-arcgis/scripts/cli.py count https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Search/FeatureServer/0 --json
python3 skills/nz-arcgis/scripts/cli.py describe https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_Precincts/MapServer --json
python3 skills/nz-arcgis/scripts/cli.py query https://gis.ccc.govt.nz/server/rest/services/OpenData/Structure/FeatureServer/2 --bbox 172.635,-43.535,172.64,-43.53 --fields FenceID,Height --limit 5 --format geojson
python3 skills/nz-arcgis/scripts/cli.py query https://services-ap1.arcgis.com/eqbFSejuTufXDr0E/arcgis/rest/services/flooded_nz_gdb_v2_202603181308/FeatureServer/0 --fields objectid,obs_date,impact,obs_depth,obs_depth_v2,historic --limit 5 --json
python3 skills/nz-arcgis/scripts/cli.py search stormwater --org akl --root 0 --max-services 20 --json
python3 skills/nz-arcgis/scripts/cli.py describe https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --json
python3 skills/nz-arcgis/scripts/cli.py count https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --json
python3 skills/nz-arcgis/scripts/cli.py query https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --bbox 174.738,-36.895,174.741,-36.888 --limit 5 --format geojson --json
python3 skills/nz-arcgis/scripts/cli.py query https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/Stormwater_Pipe/FeatureServer/0 --bbox 174.919,-37.024,174.922,-37.021 --fields OBJECTID --limit 5 --format csv
```

- Every command accepts `--json`: `{"meta": {...}, "results": [...]}`. GeoJSON has a `meta` foreign member. Provenance includes source URL, publisher, UTC retrieval time, licence when known and `latest_data` when editingInfo.lastEditDate exists. Cached catalogue timestamps are retained. Unknown licence notes are separate from reuse terms. Errors use stdout with empty results and standard error code/type/message; human errors use stderr.
- `query` accepts `--where` (default `1=1`), `--fields` (default `*`), WGS84 `--bbox`, `--limit` (default 100, maximum 10,000) and `--format json|geojson|csv`. Geometry uses WGS84; bbox filtering uses upstream intersects. Tables reject `--bbox`; use `--where` for attribute filtering. CSV requests no geometry, includes provenance columns and prefixes formula-like strings with an apostrophe. `--json --format csv` returns one CSV record in `results` with counts and truncation status.
- Queries first select object IDs with the same filter, sort them and fetch at most 200 IDs per batch. ID selection is bounded by a 32 MiB response and the command’s aggregate byte/deadline limits, independently of the feature limit. `matched_count` reports the size of the returned ID selection; server-truncated ID selections also set `incomplete`. Missing returned IDs mark `incomplete` and `truncated`, with `missing_object_ids_count`. Without an OID, offset paging cross-checks the count and warns that ordering is unavailable.
- `describe`, `count` and `query` accept `--timeout SECONDS` (1–60, default 10). Enterprise MapServer layers need small bboxes; narrow the example bbox further or raise the timeout when needed. Commands have a 55-second deadline (within the common runner’s 60-second cap) and 64 MiB aggregate response bound; partial query/discovery results report truncation reasons.
- `services` and `search` traverse at most two folder levels, with `--max-requests` (default 40, maximum 50) and optional `--root INDEX`. Unvisited directories and failed folders/services are returned explicitly; failed discovery entries mark coverage truncated. Discovery includes FeatureServer, MapServer and ImageServer. `describe` also accepts service URLs for metadata, including tiles-only PC120 maps; `count` and `query` require numeric FeatureServer/MapServer layers. Service extents retain their declared source CRS and are metadata, not GeoJSON.
- `search TEXT --org ORG` searches all discovered service names plus layer names from at most `--max-services` services (default 20, maximum 50), prioritising service-name matches. It reports scanned services and `truncated` when coverage is incomplete. Raise the bound or choose another root to widen discovery.
- The client accepts only exact registry hosts and REST prefixes, including exact ArcGIS Online tenant IDs. Redirects, credentials, ports, arbitrary operations, query-string URLs and unsafe paths are refused before following them. Strip a copied `?f=json` from layer URLs.
- No tokens, login, edits, exports of imagery, spatial analysis or real-time flood predictions. AT roadwork status and dates can disagree: filter dates explicitly using the published field names.
- Dunedin/Hamilton road assets and Hamilton renewals are not closure feeds: catalogue roadworks/closure rows are HTML notices outside this skill. Flooded NZ is self-reported, has no stated reuse licence and includes contact fields: select the observation fields shown above. Only that Council service is allowlisted within its contractor's ArcGIS tenant. DEM/DSM identify support is deferred because the tiled image host's robots.txt disallows automated paths; do not crawl its metadata, tiles or identify routes.

## References and checks

Read [references/source-notes.md](references/source-notes.md) for verification results, excluded routes and bounds. [references/orgs.json](references/orgs.json) is the runtime allowlist; [references/verification.json](references/verification.json) records live root checks, including failures. [references/curation-exclusions.json](references/curation-exclusions.json) records omitted catalogue feature layers.

Run `scripts/test_contract.py` for deterministic contracts and response assertions, and `scripts/smoke_test.py` for bounded live probes. Maintainers can rebuild the Auckland files using `python3 skills/nz-arcgis/scripts/curate_layers.py skills/nz-data-catalogue/data/catalogue.json.gz`; add `--reuse-verification` to retain bundled probe timestamps. Rebuild the additional selection with `python3 skills/nz-arcgis/scripts/curate_more_layers.py skills/nz-data-catalogue/data/catalogue.json.gz`; it verifies metadata/counts and records failures in [references/more-layer-exclusions.json](references/more-layer-exclusions.json).
