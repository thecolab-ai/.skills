---
name: akl-rainfall
description: "Query Auckland Council rainfall gauges and river or stream levels and flows. Use for Auckland monitoring sites, observed rainfall or water-level time series, and latest rainfall with spatial filters."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Auckland Council"
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
  thecolab.source_url: "https://environmentauckland.org.nz/"
  thecolab.allowed_domains: "environmentauckland.org.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Auckland rainfall and rivers

Use the stdlib Python CLI in `scripts/cli.py` to query Auckland Council's
Environment Auckland AQUARIUS WebPortal. Site discovery and JSON exports work
without a login, API key, cookies or browser.

## Workflow

1. Find gauges with `sites`, selecting rainfall, river/stream level or flow.
2. Copy the site's `site` identifier into `series` and choose a date window.
3. Use `latest` for each rainfall gauge's most recent non-null increment within
   the last 72 hours. Inspect observation time, age and quality before using it.

```bash
python3 skills/akl-rainfall/scripts/cli.py sites --parameter rainfall --json
python3 skills/akl-rainfall/scripts/cli.py sites --parameter level --bbox '174.8,-37.1,175.0,-36.9' --format geojson --json
python3 skills/akl-rainfall/scripts/cli.py series --site 649940 --parameter rainfall --from 2026-10-07 --to 2026-10-08 --interval hour --json
python3 skills/akl-rainfall/scripts/cli.py series --site 43803 --parameter level --from 2026-10-07 --to 2026-10-08 --json
python3 skills/akl-rainfall/scripts/cli.py series --site 43803 --parameter flow --from 2026-10-07 --to 2026-10-08 --interval day --json
python3 skills/akl-rainfall/scripts/cli.py latest --parameter rainfall --bbox '174.88,-36.99,174.89,-36.97' --json
```

## Commands and output

- `sites [--parameter rainfall|level|flow] [--bbox minLon,minLat,maxLon,maxLat]`
  lists monitoring sites, coordinates and available dataset identifiers. With
  no parameter it returns the union of those three parameters. Includes old
  gauges; inspect `end_of_record` (the Council's advertised record bound).
  bbox filtering is local, inclusive point containment on site coordinates;
  sites without coordinates are excluded. Bounds must strictly increase.
- `series --site ID --parameter rainfall|level|flow --from ISO --to ISO
  [--interval hour|day] [--max-points N]` returns source observations or upstream aggregates.
  Exact site names also work; identifiers avoid ambiguity. Windows are inclusive,
  at most 31 days, and boundaries must have minute precision. A date means midnight.
  Raw output (no `--interval`) has `--max-points` (default and maximum 5,000);
  excess fails with code 2. Set a smaller positive limit to bound output further.
  Use `--interval hour|day` or a shorter window to reduce the output.
- `latest --parameter rainfall [--bbox minLon,minLat,maxLon,maxLat]` returns
  the most recent non-null recorded increment per gauge within 72 hours, with
  `age_hours` and `stale` (over 24 hours). Reports gauges outside the lookback and
  gauges without values separately. This is an increment, not a 24-hour total.

Every command accepts `--json`, returning `{"meta": {...}, "results": [...]}`.
Shared `meta` includes `source_url`, `publisher`, `licence`, `retrieved_at`, and
`latest_data` when published, plus counts, warnings and query details. Errors
return the same `meta`, empty `results`, and `error` with code, type and message.
Spatial commands also accept `--format json|geojson`; either implies machine
output. GeoJSON uses WGS84 longitude, latitude order and top-level `meta`.
Latest gauges retain their individual export `source_url`; other shared
provenance appears once in `meta`. Retrieval times are UTC; data times are
**fixed NZST (UTC+12)** even in summer. Do not interpret naive input as
daylight-saving Auckland time.

Dataset records use `start_of_record`/`end_of_record` for coverage; sites report
`end_of_record`. Series `meta.latest_data` is the advertised end of that dataset's record; it can be
newer than the requested historical window.
Latest metadata reports the newest returned observation. POST `source_url` is
the bare public endpoint; `meta.request`/`meta.catalogue_requests` record its
method and form separately. GET export URLs retain replayable query parameters.

With `--interval`, rainfall is the total over the preceding interval; level/flow
are averages. Aggregate `time` is the interval end. Use `period_start` and
`period_end` for day attribution; days run midnight–midnight NZST (01:00–01:00
NZDT in summer). Retain `grade_code`, `grade_name`, approvals, qualifiers and
interpolation fields. Missing source values (`"NaN"`) become `null`, with
`missing: true` and the original `source_missing_marker`. Never treat them as zero.
An empty valid time window remains an empty result; malformed exports fail.
A window outside the dataset's advertised record includes a metadata warning;
an empty series is not evidence of no rain.

## Limits and attribution

- Data is for the sole use of the recipient. Do not redistribute or republish
  raw extracts without agreement; attribute **Auckland Council** in any output.
  Data may be measured or synthesised and is not for safety decisions. See the
  [portal terms](https://environmentauckland.org.nz/Disclaimer), including indemnity.
  The skill's MIT licence covers its code; no open data licence was found.
- Some stations are operated by ESNZ/NIWA and distributed through the Council
  portal. Check the station owner and its terms before reuse.
- Gauges are provisional and may be old, missing or unverified. These are gauge
  measurements, not street flood depths or official warnings.
- No radar imagery or forecasts. Historical coverage varies. Council says additional
  parameters and historical data can be requested through its contact dashboard.
- Each network call uses a 10-second timeout. Latest downloads use one request per active
  gauge and at most four concurrent requests; one failed request fails the command.
  No credentials, caches or external dependencies are required.

## Resources and checks

See `references/source-notes.md` for verified endpoints, source terms and schema
details. Hand-written synthetic parser fixtures are in `tests/fixtures/`;
`fixtures.json` marks their fictional contents and the source shapes they mirror.

```bash
python3 scripts/validate_skill.py skills/akl-rainfall --strict
python3 skills/akl-rainfall/scripts/test_contract.py
python3 scripts/run_smoke_tests.py akl-rainfall
```

`scripts/test_contract.py` checks synthetic parsers and the shared CLI contract.
`scripts/smoke_test.py` checks fixtures before bounded live sites, rainfall, level,
flow and latest probes. Network outages are skips; parser failures are failures.
