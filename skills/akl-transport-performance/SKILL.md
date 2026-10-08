---
name: akl-transport-performance
description: "Query Auckland Transport patronage by mode and route, monthly punctuality and reliability, live city car park spaces, and Metlink daily bus performance. Use for keyless public transport and parking performance comparisons."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Auckland Transport; Greater Wellington Regional Council / Metlink"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://at.govt.nz/about-us/reports-publications/at-metro-patronage-report/"
  thecolab.allowed_domains: "at.govt.nz,www.metlink.org.nz,services2.arcgis.com"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Auckland transport performance

Use `scripts/cli.py` for keyless public transport demand and service performance.
Use `at-transport` for live GTFS departures and vehicle positions; that API needs
an AT key and is outside this skill.

```bash
python3 skills/akl-transport-performance/scripts/cli.py sources --json
python3 skills/akl-transport-performance/scripts/cli.py patronage --mode bus --from 2026-09-01 --to 2026-09-27 --json
python3 skills/akl-transport-performance/scripts/cli.py patronage --mode train --frequency monthly --json
python3 skills/akl-transport-performance/scripts/cli.py patronage --mode bus --route 101 --from 2026-08 --to 2026-08 --json
python3 skills/akl-transport-performance/scripts/cli.py punctuality --route 101 --month 2026-08 --json
python3 skills/akl-transport-performance/scripts/cli.py metlink --route 1 --date 2026-09-27 --json
python3 skills/akl-transport-performance/scripts/cli.py carparks --json
python3 skills/akl-transport-performance/scripts/cli.py carparks --inventory --bbox 174.6,-36.95,174.8,-36.8 --format geojson
```

- `sources` checks live downloads and parses them, reporting each source's health,
  observation count, provenance and coverage. An individual outage is a degraded
  source record rather than an empty successful dataset.
- `patronage` defaults to daily mode totals, or monthly route counts with
  `--route`. Use `--frequency monthly` for monthly mode totals. Routes match exact
  identifiers, case-insensitively. Dates are inclusive; monthly counts match any
  overlap with the requested interval and remain monthly, never daily estimates.
- `punctuality` returns both punctuality and reliability as fractions from 0 to 1,
  joined by mode, route and month. Missing measurements remain null.
- `metlink` returns daily Wellington bus demand, capacity and service measures.
  `--date` takes YYYY-MM-DD. These are a Wellington comparison, not Auckland data.
- `carparks` currently returns a structured blocked error (exit 4): AT robots.txt
  disallows `/umbraco/`, including the city short-term vacancy endpoint. It never
  requests that path. `--inventory` explicitly selects the public ArcGIS facility
  inventory. Its sparse `available_spaces` fields have no observation timestamp;
  do not present them as live city vacancies. Bounding boxes apply locally by
  point containment in WGS84; GeoJSON uses longitude then latitude.

Without date filters, AT commands use the newest linked workbook. Patronage date
bounds and `punctuality --month` search up to four linked AT fiscal-year workbooks,
newest first. Inspect `meta.coverage_from` and `meta.latest_data`; requested dates
outside that coverage may return no matches. Metlink uses its current linked daily
CSV, not the much larger historic archive.

Downloads use a bounded 24-hour cache under the skill's `.cache/` directory.
`--max-age 0` forces a refresh for patronage, punctuality and Metlink; `sources`
and parking inventory always query live. Cached results retain the download's
original UTC retrieval timestamp. Every network request has a 10-second timeout.
Errors are structured JSON with stable exit codes when `--json` is supplied.

Read [references/source-notes.md](references/source-notes.md) for source URLs,
reuse terms, measure definitions and coverage limits. Run
`scripts/test_contract.py` for deterministic checks and `scripts/smoke_test.py`
for synthetic fixtures plus live probes. The `tests/fixtures/` workbooks and CSV
contain made-up values in the verified upstream schemas.
