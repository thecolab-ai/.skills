---
name: brisbane-intersection-traffic
description: "Read keyless Brisbane City Council real-time intersection lane volume, occupancy and traffic-signal locations from data.brisbane.qld.gov.au. Use for SCATS traffic signal controller site readings, lane flow, degree of saturation, or signal point locations. Not Queensland-wide incidents, flood, bikeway or other Brisbane datasets."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Brisbane City Council"
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
  thecolab.source_url: "https://data.brisbane.qld.gov.au/"
  thecolab.allowed_domains: "data.brisbane.qld.gov.au"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Brisbane intersection traffic

Read two Brisbane City Council open datasets from the public explore API.
`volumes` is real-time lane volume and occupancy at council-operated
signalised intersections. `signals` is the council signal-location reference.
Both are keyless. The commands do not cover Queensland incidents, flood,
bikeway, stormwater, or the separate intersection-location reference dataset.

## Commands

Run from the repo root. Python 3.10+, standard library only.

```bash
python3 skills/brisbane-intersection-traffic/scripts/cli.py volumes --limit 1 --json
python3 skills/brisbane-intersection-traffic/scripts/cli.py volumes --limit 5 --tsc 757 --lane SA-267 --json
python3 skills/brisbane-intersection-traffic/scripts/cli.py signals --limit 1 --json
python3 skills/brisbane-intersection-traffic/scripts/cli.py signals --limit 5 --bbox 153.15,-27.45,153.17,-27.43 --format geojson
```

`--limit` is required and accepts 1 to 20. There is no offset or export
command. `--timeout` accepts 1 to 15 seconds and defaults to 15. `--tsc` is
the traffic signal controller site id shared by both datasets. `--lane` is
the volume approach id, such as `SA-267`.

`--bbox` is `minLon,minLat,maxLon,maxLat` in WGS84. It is accepted only on
`signals`. The filter is applied upstream: a signal is returned when its
published point lies inside the box. The CLI does not cross the antimeridian.
`--format geojson` emits a FeatureCollection and does not need `--json`.
Errors stay in the JSON error envelope.

`--json` prints `meta` and `results`. `meta.total_count` is the source count
for the query. `meta.latest_data` on `volumes` is the newest source
`recorded` timestamp among the returned rows. The request asks the source
for `recorded` descending order. `signals` has no per-record timestamp, so
that command omits `latest_data`.

Null detector slots stay null. Numeric-looking volume fields stay strings
when the source sends strings. Field units and the separate dataset licences
are in `references/source-notes.md`.

## Errors

Invalid limits, identifiers and boxes fail before any network call. An empty
`results` array with `total_count` 0 is a real empty result. Non-JSON,
truncated JSON, and a changed record schema fail. HTTP 429 keeps
`Retry-After` when the source sends it. HTTP 503, timeouts, and other
upstream failures are errors. A redirect off `data.brisbane.qld.gov.au` is
rejected. The CLI has no URL argument.
