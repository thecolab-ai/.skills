---
name: linz-data-service
description: "Search and inspect LINZ Data Service public Koordinates catalogue layers, tables, services, licences, tags, and download/view capabilities through no-login JSON endpoints. Use when the task involves Toitū Te Whenua LINZ datasets such as addresses, parcels, imagery, hydrography, roads, property, or geospatial layers. Query keyless primary-parcel and building-outline polygons from the public LINZ ArcGIS mirror. Read-only; no API key needed."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Toitū Te Whenua LINZ"
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
  thecolab.source_url: "https://data.linz.govt.nz/services/api/v1/"
  thecolab.allowed_domains: "data.linz.govt.nz,services.arcgis.com"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# LINZ Data Service

## Goal

Find and inspect public LINZ Data Service catalogue records and advertised services and query public mirror features without logging in.

## CLI

```bash
python3 skills/linz-data-service/scripts/cli.py search address --json
python3 skills/linz-data-service/scripts/cli.py layer 123113 --json
python3 skills/linz-data-service/scripts/cli.py services 123113
python3 skills/linz-data-service/scripts/cli.py feature-layers --json
python3 skills/linz-data-service/scripts/cli.py features primary-parcels --bbox 174.735,-36.905,174.745,-36.875 --limit 5 --format geojson
python3 skills/linz-data-service/scripts/cli.py features building-outlines --bbox 174.735,-36.905,174.745,-36.875 --limit 5 --json
```

Commands:

- `search QUERY [--limit N] [--json]` - search public LDS layers
- `layer ID [--json]` - layer metadata, licence, tags, permissions, description
- `services ID [--json]` - advertised OGC/Koordinates service templates and auth requirements

- `feature-layers [--json]` - verified mirror availability and data edit times
- `features primary-parcels|building-outlines --bbox minLon,minLat,maxLon,maxLat [--limit N] [--format geojson] [--json]` - WGS84 polygons intersecting a bbox

Feature queries use the keyless `services.arcgis.com/xdsHIIxuCWByZiCB` mirror.
Bboxes are at most 1 degree wide/high. Defaults return 100 features; the limit
is capped at 2000, with bounded paging, a matching count and a `truncated` flag.
Intersecting polygons keep their original boundaries; they are not clipped.
`--format geojson` emits a FeatureCollection; `--json` emits a record envelope.
Each feature and envelope includes source URL, LINZ publisher, CC BY 4.0 licence,
UTC retrieval time and `latest_data` (mirror edit time, not imagery capture date).
Network calls time out after 10 seconds and feature responses are capped at 8 MiB.

**NZ Parcels is unavailable in the verified public mirror (8 October 2026).**
`features parcels` fails explicitly with exit code 7. Current primary parcels
are available but exclude non-primary, historic and pending parcels. Use
`layer 51571 --json` for NZ Parcels catalogue metadata; no key-based query is used.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

Metadata/search is no-auth. Some download/query service URLs advertise API-key variants; the skill reports those boundaries rather than bypassing them.
