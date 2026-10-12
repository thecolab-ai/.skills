---
name: qld-traffic-incidents
description: "Read current Queensland traffic incidents from the official OpenDataSoft dataset queensland-traffic-incidents. Use for Queensland road closures, hazards, roadworks and other published traffic incidents when a bounded, keyless record window is enough."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Queensland"
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
  thecolab.source_url: "https://queensland.opendatasoft.com/api/explore/v2.1/catalog/datasets/queensland-traffic-incidents"
  thecolab.allowed_domains: "queensland.opendatasoft.com"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Queensland traffic incidents

Read a bounded window of current incidents from the Queensland OpenDataSoft
dataset `queensland-traffic-incidents`. The CLI is `scripts/cli.py`. Field
notes, licence evidence and error behaviour are in `references/source-notes.md`.

## Use this when

- The task needs current Queensland road closures, hazards or other published traffic incidents
- A caller wants a small JSON or GeoJSON window, not a full export
- The dataset must stay on `queensland.opendatasoft.com`

This skill does not read Brisbane intersection counts, New Zealand highway
feeds, or `api.qldtraffic.qld.gov.au`. Some published points fall outside
Queensland. Those rows are kept with the source coordinates.

## Command

```bash
python3 scripts/cli.py incidents --limit 1 --json
python3 scripts/cli.py incidents --limit 5 --category Hazard --bbox 152.9,-28.3,153.2,-28.0
python3 scripts/cli.py incidents --limit 5 --format geojson
```

`--limit` is required and must be from 1 to 20. Results are the newest
`last_updated` rows that match the filters. `meta.total_count` is the upstream
match count. The command does not page the rest of the dataset.

`--bbox` is `minLon,minLat,maxLon,maxLat`. For a box whose first longitude is
negative, use `--bbox=-180,-90,180,90`. The filter is an upstream point-in-box
test on `geo_point_2d`, not a test of the road line.

`--format geojson` prints a GeoJSON FeatureCollection. `--json` prints the
`meta` / `results` envelope. Both include the dataset licence when the source
states it. An empty match is an empty `results` array or an empty feature list.

Check `scripts/test_contract.py` and `scripts/smoke_test.py` after changes.
The live smoke requests one incident only.
