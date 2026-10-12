---
name: nz-ridereport
description: "Read keyless Auckland Ride Report aggregate micromobility metrics for one published vehicle and period. Use for quarterly trip totals, speeds, distances and a short daily series. Do not use for personal trips, street-geometry downloads, BikeMaps incident reports, or traffic-counter time series."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Ride Report"
  thecolab.source_type: "commercial"
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
  thecolab.source_url: "https://public.ridereport.com/auckland"
  thecolab.allowed_domains: "public.ridereport.com,api.ridereport.com,public-data-exports-production.s3-us-west-2.amazonaws.com"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Auckland Ride Report

Read the public Auckland micromobility dashboard catalogue and one aggregate
`trip_metrics.json` export. The city is fixed to Auckland. Use `scripts/cli.py`.
Every data command accepts `--json`. Human text is the default.

Read `references/source-notes.md` for the reuse sentence, the hosts, and the
files this skill does not download.

## Commands

```bash
python3 scripts/cli.py dashboard --json
python3 scripts/cli.py metrics --vehicle scooter --period 2026-Q3 --json
python3 scripts/cli.py metrics --vehicle scooter --period 2026-Q3 --series trips --limit 7 --json
```

`dashboard` reads the published vehicle/period catalogue and the Auckland
settings summary: name, population, operators, and optional bounds. It does
not copy operator-cap polygons.

`metrics` accepts only a vehicle and period that the current catalogue lists.
The default result is one aggregate record. `--series` adds one of `trips`,
`duration`, `distance`, `vehicles`, or `utilisation`, keeping at most `--limit`
buckets in source order (1 to 92, default 31). A missing export object is an
empty `results` array with a `no_export` warning.

## Boundaries

- Attribution and a link to `public.ridereport.com` are required by the source.
- No personal trajectories, rider identifiers, or device traces are requested.
- Street-segment geometry and route-aggregation maps are out of scope.
- One command makes at most two requests, each with a 10-second timeout and a
  size cap. Redirects must stay on the allowlisted Auckland URLs.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic contract and parser fixtures
- `scripts/smoke_test.py` — fixture checks and a bounded live probe
- `references/source-notes.md` — source envelope, licence, and error semantics
