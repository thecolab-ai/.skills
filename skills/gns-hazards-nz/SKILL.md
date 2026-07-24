---
name: gns-hazards-nz
description: "Query GNS Science public ArcGIS hazard services through a lightweight no-login CLI: the NZ Active Faults Database (fault traces, recurrence intervals, slip rates, avoidance zones) and live ShakingLayers ground-motion contours (MMI, PGA, PGV) generated after significant earthquakes. Use when the task involves NZ active fault locations, fault hazard attributes, or measured ground-shaking extents from recent earthquakes. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "GNS Science"
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
  thecolab.source_url: "https://gis.gns.cri.nz/server/rest/services"
  thecolab.allowed_domains: "gis.gns.cri.nz"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# GNS Hazards NZ

## Goal

Query GNS Science's public ArcGIS hazard services — the NZ Active Faults
Database and per-event ShakingLayers ground-motion contours — through a
deterministic read-only CLI with human and JSON output.

## Use this when

- A task needs NZ active fault traces, recurrence intervals, slip rates,
  fault avoidance zones, or fault awareness areas as GeoJSON
- A task needs measured ground-shaking contours (MMI, PGA, PGV, PSA) from the
  most recently published significant NZ earthquake

## Do not use this for

- Earthquake event lists, felt reports, or volcano alerts (use `geonet-nz`)
- Regional council hazard overlays such as liquefaction or tsunami zones
  (use `wcc-arcgis-nz` for the Wellington region)
- Any write, upload, or account action

## Commands

```bash
python3 skills/gns-hazards-nz/scripts/cli.py layers --service faults
python3 skills/gns-hazards-nz/scripts/cli.py faults --bbox "174.6,-41.5,175.1,-41.0" --limit 20 --json
python3 skills/gns-hazards-nz/scripts/cli.py faults --layer-id 7 --limit 10 --json
python3 skills/gns-hazards-nz/scripts/cli.py shaking --measure mmi --min-contour 6 --json
```

- `layers [--service faults|shaking] [--json]` — layer ids and names of each service
- `faults [--layer-id N] [--where SQL] [--bbox minLon,minLat,maxLon,maxLat] [--fields F1,F2] [--limit N] [--json]` — Active Faults Database GeoJSON (layer 0 = 1:250k traces; 6 = high-res traces; 7 = avoidance zones; 8 = awareness areas)
- `shaking [--measure mmi|pga|pgv|psa0.3|psa1.0|psa3.0] [--min-contour X] [--bbox ...] [--limit N] [--json]` — ground-motion contours for the latest published ShakingLayers event

## Notes

- Licence: CC BY 4.0 — attribute GNS Science
- ShakingLayers features carry only contour values, no event id: the service
  holds the most recently published event model, and the CLI says so in every
  payload — do not treat it as a permanent hazard map
- High-resolution traces and avoidance zones are populated progressively by
  region; absence of features is not evidence of no fault hazard
- `truncated: true` means the server transfer limit was hit — narrow with
  `--where`/`--bbox`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Service layouts, citation, and failure modes: `references/source-notes.md`
