---
name: nz-utility-outages
description: "Query Watercare Auckland water faults and planned shutdowns, Wellington electricity outages, KiwiRail Auckland work notices and the published rail closure calendar. Use for utility interruptions, maintenance windows and nearby outage searches; report Vector and other unavailable source limits explicitly."
license: MIT
compatibility: "Requires Python 3.10+ with system timezone data and network access for live data; standard library only"
metadata:
  thecolab.category: "utilities"
  thecolab.source_owner: "Watercare, Vector, KiwiRail and NZ electricity networks"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api and bounded public HTML/PDF"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.watercare.co.nz/home/faults-and-outages"
  thecolab.allowed_domains: "www.watercare.co.nz, webapi.watercare.co.nz, help.vector.co.nz, www.welectricity.co.nz, www.kiwirail.co.nz, powernet.co.nz, api.integration.countiesenergy.co.nz, app.countiesenergy.co.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Utility Outages

Use `scripts/cli.py` to read public operator notices. Start with `sources` to
check coverage and access. All data commands support `--json`; network requests
have 10 s timeouts. The skill needs no credentials and makes no upstream changes.

```bash
python3 scripts/cli.py sources --json
python3 scripts/cli.py outages --utility watercare --status current --json
python3 scripts/cli.py outages --utility watercare --status planned --bbox 174.5,-37.2,175,-36.5 --format geojson
python3 scripts/cli.py outages --utility wellington --status planned --json
python3 scripts/cli.py outages --utility kiwirail --json
python3 scripts/cli.py rail-closures --from 2026-02-01 --to 2026-04-30 --json
python3 scripts/cli.py near --near 174.76,-36.85 --radius 5 --json
python3 scripts/cli.py near --utility all --near 174.76,-36.85 --radius 5 --format geojson
```

`near` defaults to Watercare, with a 5 km radius. `--utility all` combines
Watercare and Wellington. `outages` also recognises `vector`, `powernet` and
`counties`, returning explicit unsupported/blocked errors for those sources.
See [references/source-notes.md](references/source-notes.md) for the reasons.

## Interpretation

- Every outage, notice or closure uses one record shape: `utility`, `id`, `kind`,
  `status`, `start`, `end`, `area`, `geometry`, `affected_count`, `description`
  and provenance. Missing times, counts and locations remain `null`.
- Watercare unplanned faults are `current` as listed by the operator. Planned
  windows are `planned` before they start, `current` during the published window,
  and `unknown` after the estimated end; an estimate does not prove restoration.
- Wellington recognises cancellation and restoration separately. Dates use
  `Pacific/Auckland` daylight saving, then become UTC. Alternate dates are used
  only when the source's `useAlternateDate` flag is set.
- KiwiRail works can cause neighbourhood disturbance without closing passenger
  services. Each work notice has `passenger_closure_confirmed: false`.
  Undated ongoing work stays undated; no year or coordinates are invented.
- `rail-closures` reads the official colour-coded PDF. Its verified coverage is
  **January–May 2026**, with publication date **2 February 2026**, rather than a
  complete 2026 timetable. `meta.coverage_start` and `meta.coverage_end` always
  describe the fetched version. An empty result outside coverage is not evidence
  that trains run. Closure rows preserve the published schedule as `planned`,
  including historical dates; `source_status` is `published_schedule`.
- Calendar and dated work notice values are inclusive NZ calendar days, not
  precise start/end hours. Partial closures also include reduced frequency;
  the PDF does not identify affected lines. Confirm passenger services with AT.

## Spatial and output contract

`--bbox minLon,minLat,maxLon,maxLat` uses WGS84 longitude then latitude. Filtering
occurs locally and includes point locations on the box boundary. `near` uses
haversine distance to the operator's published point, which is representative
rather than a guaranteed affected-property boundary. Unlocated records are
excluded from spatial matches and counted in `meta.excluded_unlocated`.
KiwiRail has no published coordinates: `outages --utility kiwirail --bbox ...`
returns an unsupported-operation error. Unfiltered GeoJSON may use null geometry.

`--format geojson` implies JSON output and emits a `FeatureCollection` with
`meta` and provenance in feature properties. Other JSON commands return
`{"meta": {...}, "results": [...]}`; mixed sources preserve per-record provenance.
`retrieved_at` is UTC with a trailing `Z`. `latest_data` comes only from source
updates or calendar publication, never the retrieval clock.

Errors return the same JSON envelope with empty `results` and a typed `error`:
2 invalid input, 4 blocked/rate limited, 5 upstream unavailable, 6 changed schema,
7 unsupported operation. Mixed-source queries fail if either feed fails, so an
upstream error cannot masquerade as an empty or incomplete successful search.

## Resources and verification

- [references/source-notes.md](references/source-notes.md): exact endpoints,
  robots/terms findings, schemas and access limits.
- `scripts/rail_calendar.py`: restricted stdlib PDF calendar parser; changed
  legends, colours or incomplete month grids fail with a schema error.
- `scripts/provenance.py`: JSON envelope and spatial argument helpers.
- `scripts/test_contract.py`: deterministic repository and parser contracts.
- `scripts/smoke_test.py`: synthetic fixtures plus bounded, outage-aware live probes.
- `tests/fixtures/`: made-up values in the verified source formats, including
  a synthetic PDF. No operator datasets are bundled.

```bash
python3 scripts/test_contract.py
python3 scripts/smoke_test.py
```
