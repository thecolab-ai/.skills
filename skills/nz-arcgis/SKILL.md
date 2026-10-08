---
name: nz-arcgis
description: "Discover and query allowlisted New Zealand public-sector ArcGIS services and layers, including Auckland flood, stormwater, roadworks and transport data. Use for layer metadata, counts and bounded WGS84 spatial extracts as JSON, GeoJSON or CSV."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "New Zealand public-sector ArcGIS publishers"
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
  thecolab.source_url: "https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services"
  thecolab.allowed_domains: "arcgis.mfe.govt.nz,gis.ccc.govt.nz,gis.gns.cri.nz,gis.wcc.govt.nz,mahere.at.govt.nz,mapping.gw.govt.nz,mapping1.gw.govt.nz,maps.herengaanuku.govt.nz,mapspublic.aklc.govt.nz,mapspublic.aucklandcouncil.govt.nz,seasketch.doc.govt.nz,services-ap1.arcgis.com,services.arcgis.com,services1.arcgis.com,services2.arcgis.com,services3.arcgis.com,services5.arcgis.com,services6.arcgis.com,services9.arcgis.com,tiledimageservices1.arcgis.com,wslgis.water.co.nz"
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
4. Run `describe LAYER_URL` before choosing fields or an attribute filter; it includes fields, geometry type, record count and the upstream editing timestamp when published.
5. Use `count` to size a selection, then `query` with a WGS84 bbox and small limit. Preserve the layer caveats when interpreting an extract.

## Commands

```bash
python3 skills/nz-arcgis/scripts/cli.py orgs --json
python3 skills/nz-arcgis/scripts/cli.py services at --json
python3 skills/nz-arcgis/scripts/cli.py layers at PJ_Roadworks_MS/FeatureServer --json
python3 skills/nz-arcgis/scripts/cli.py layers --curated akl --problem F1 --json
python3 skills/nz-arcgis/scripts/cli.py search stormwater --org akl --root 0 --max-services 20 --json
python3 skills/nz-arcgis/scripts/cli.py describe https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --json
python3 skills/nz-arcgis/scripts/cli.py count https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --json
python3 skills/nz-arcgis/scripts/cli.py query https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/PJ_Roadworks_MS/FeatureServer/0 --bbox 174.60,-37.05,174.95,-36.70 --limit 5 --format geojson --json
python3 skills/nz-arcgis/scripts/cli.py query https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/Stormwater_Pipe/FeatureServer/0 --bbox 174.60,-37.05,174.95,-36.70 --fields OBJECTID --limit 5 --format csv
```

- Every command accepts `--json`. JSON and GeoJSON result envelopes include `source_url`, `publisher`, `licence` (null when unknown), UTC `retrieved_at` and `latest_data` when editingInfo.lastEditDate exists. Attribute dates are source observations; an editing timestamp is not an observation date.
- `query` accepts `--where` (default `1=1`), `--fields` (default `*`), `--bbox minLon,minLat,maxLon,maxLat`, `--limit` (default 100, maximum 10,000) and `--format json|geojson|csv`. Geometry output uses WGS84. CSV is an attribute extract with provenance columns; `--json --format csv` wraps the CSV string in a JSON envelope with counts and truncation status.
- Paging uses resultOffset and resultRecordCount, ordered by the object ID when published (automatically added to restricted field selections), at most 1,000 records per request and 20 pages. Servers without pagination support return one page with conservative `truncated` status. Narrow bbox/where filters when truncated; exact-limit results are conservatively marked truncated.
- `services` and `search` traverse at most two folder levels, with `--max-requests` (default 40, maximum 50) and optional `--root INDEX`. Unvisited directories and token-gated folders/services are returned explicitly; gated discovery entries mark coverage truncated. Discovery includes FeatureServer, MapServer and ImageServer; feature query/count/describe require a numeric FeatureServer or MapServer layer.
- `search TEXT --org ORG` searches all discovered service names plus layer names from at most `--max-services` services (default 20, maximum 50), prioritising service-name matches. It reports scanned services and `truncated` when coverage is incomplete. Raise the bound or choose another root to widen discovery.
- The client accepts only exact registry hosts and REST prefixes, including exact ArcGIS Online tenant IDs. Redirects, credentials, ports, arbitrary operations, query-string URLs and unsafe paths are refused before following them. Strip a copied `?f=json` from layer URLs.
- No tokens, login, edits, exports of imagery, spatial analysis or real-time flood predictions. AT roadwork status and dates can disagree: filter dates explicitly using the published field names.

## References and checks

Read [references/source-notes.md](references/source-notes.md) for verification results, excluded routes and bounds. [references/orgs.json](references/orgs.json) is the runtime allowlist; [references/verification.json](references/verification.json) records live root checks, including failures. [references/curation-exclusions.json](references/curation-exclusions.json) records omitted catalogue feature layers.

Run `scripts/test_contract.py` for deterministic contracts and captured response assertions, and `scripts/smoke_test.py` for bounded live counts and five-feature bbox queries on AT roadworks and Council stormwater pipes. Maintainers can rebuild the curated files using `python3 skills/nz-arcgis/scripts/curate_layers.py PATH_TO_CATALOGUE_JSON`; it probes candidate metadata live and records failures.
