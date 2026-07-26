---
name: gns-hazards-nz
description: "Use when a task needs source-derived New Zealand active-fault features, ArcGIS layer metadata, latest modelled shaking contours, or versioned GeoNet ShakingLayers event files and contour GeoJSON. Provides read-only GNS Science and GeoNet discovery, count, ID, paging, metadata, and spatial-query primitives without authentication."
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
  thecolab.source_url: "https://shakinglayers.geonet.org.nz/api/v1/events"
  thecolab.allowed_domains: "gis.gns.cri.nz, shakinglayers.geonet.org.nz"
  thecolab.last_verified: "2026-07-26"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# GNS Hazards NZ

## Goal

Query GNS Science's ArcGIS hazard layers and GeoNet's versioned ShakingLayers
archive through a deterministic, read-only, standard-library CLI.

## Use this when

- A task needs NZ active fault traces, recurrence intervals, slip rates,
  fault avoidance zones, or fault awareness areas as GeoJSON
- A task needs the ArcGIS latest modelled shaking view, or a specific event and
  published ShakingLayers version with explicit units and provenance
- A task needs source metadata, a count/ID query, paging, or geometry controls

## Do not use this for

- General earthquake catalogues, felt reports, or volcano alerts (use `geonet-nz`)
- Regional council hazard overlays such as liquefaction or tsunami zones
  (use `wcc-arcgis-nz` for the Wellington region)
- Any write, upload, or account action

## Commands

```bash
python3 skills/gns-hazards-nz/scripts/cli.py layers --service faults
python3 skills/gns-hazards-nz/scripts/cli.py describe faults --layer-id 0 --json
python3 skills/gns-hazards-nz/scripts/cli.py faults --bbox "174.6,-41.5,175.1,-41.0" --limit 20 --json
python3 skills/gns-hazards-nz/scripts/cli.py faults --layer-id 7 --count --json
python3 skills/gns-hazards-nz/scripts/cli.py shaking --measure mmi --min-contour 6 --json
python3 skills/gns-hazards-nz/scripts/cli.py events --year 2023 --json
python3 skills/gns-hazards-nz/scripts/cli.py versions 771645 --json
python3 skills/gns-hazards-nz/scripts/cli.py event-files 771645 --version latest --json
python3 skills/gns-hazards-nz/scripts/cli.py event-data 771645 --measure pga --version latest --json
```

- `layers [--service faults|shaking] [--json]` — layer ids and names of each service
- `describe faults|shaking [--layer-id N] [--json]` — normalized ArcGIS fields, aliases, descriptions/units when supplied, extent, spatial reference, capabilities, geometry type, object ID field, and record limit
- `faults [--layer-id N] [--where SQL] [--bbox minLon,minLat,maxLon,maxLat] [--fields F1,F2] [query controls] [--json]` — Active Faults Database features (layer 0 = 1:250k traces; 6 = high-res traces; 7 = avoidance zones; 8 = awareness areas)
- `shaking [--measure mmi|pga|pgv|psa0.3|psa1.0|psa3.0] [--min-contour X] [--bbox ...] [query controls] [--json]` — latest modelled ShakingLayers view
- `events [--year YYYY] [--json]` — published archive event IDs (recent events when no year is supplied)
- `versions EVENT_ID [--json]` — published/retracted versions with version path, issue time, status, and run type
- `event-files EVENT_ID [--version latest|VERSIONPATH] [--json]` — version metadata, file names/URLs, and measures derived from the published contour files
- `event-data EVENT_ID --measure MEASURE [--version latest|VERSIONPATH] [--json]` — the selected contour GeoJSON with a `provenance` object

ArcGIS query controls are `--count`, `--ids-only`, `--no-geometry`,
`--offset N`, `--order-by FIELDS`, `--geometry-precision N`, and
`--max-allowable-offset X`. Count and IDs-only modes are mutually exclusive.
Ordinary queries keep the existing feature payload; count and ID modes return
small normalized JSON envelopes.

## Notes

- ArcGIS attribution: CC BY 4.0 — attribute GNS Science. GeoNet archive
  attribution: CC BY 3.0 New Zealand — attribute GeoNet.
- Archive contour units: MMI = Modified Mercalli Intensity; PGA and PSA = `g`;
  PGV = `cm/s`. Available measures come from each version's actual files.
- The ArcGIS `shaking` service is a convenient latest modelled view. It is not
  measured-only data or a permanent hazard map; the upstream system may
  incorporate recorded observations where applicable.
- Use `event-data` when event ID, resolved version, file name, units, and exact
  source URL must be preserved.
- High-resolution traces and avoidance zones are populated progressively by
  region; absence of features is not evidence of no fault hazard
- `truncated: true` means the server transfer limit was hit — narrow with
  `--where`/`--bbox`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Source schemas, units, provenance, citation, and failure modes:
  `references/source-notes.md`
