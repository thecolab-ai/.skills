---
name: akl-ontrack
description: "Read AKLOnTrack's public Auckland train observation archive. Use for daily stop-by-stop lateness, cancellations and skipped stops from data.aklontrack.com, not the live Auckland Transport API or a GTFS timetable."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "AKLOnTrack"
  thecolab.source_type: "community"
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
  thecolab.source_url: "https://aklontrack.com/data"
  thecolab.allowed_domains: "data.aklontrack.com,aklontrack.com"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# AKLOnTrack observations

Read-only client for the public observation archive at `data.aklontrack.com`.
It lists catalogue dates and fetches one day file named by that catalogue.
It does not call the live Auckland Transport API, GTFS timetable zips, trip-outcome
files, monthly CSV bundles, or the station-name reference.

## Commands

Run from the repository root. Python 3.10+, standard library only. Each network
call times out after 15 seconds. `--json` prints a provenance envelope.

```bash
python3 skills/akl-ontrack/scripts/cli.py index --limit 20 --json
python3 skills/akl-ontrack/scripts/cli.py day 2026-07-23 --limit 20 --json
python3 skills/akl-ontrack/scripts/cli.py day --latest --limit 20 --json
```

`index` returns observation dates, byte sizes, row counts, trip counts, sha256
and `written_at`, newest first. The default returns every catalogue date, up to
a hard bound of 800. `--limit` accepts 1–500.

`day` takes one `YYYY-MM-DD` date or `--latest`. `--latest` selects the newest
index day whose row count is greater than zero and whose file is within the
byte cap, then fetches that file only. A date that is not in the index is an
error. An indexed day with zero stop rows returns an empty `results` array.

Stop observations keep the publisher's units: `arrival_delay` and
`departure_delay` are seconds late (negative means early); `arrival` and
`departure` are seconds from `t0`, Auckland midnight at the start of
`service_date`. `arrival_time` and `departure_time` are that instant in
`Pacific/Auckland`. If the day file omits a time field or sends JSON null, the
result uses null and does not substitute zero. `state` 0 is stopped, 1 cancelled,
2 skipped, 3 no report.
`trip_rel` and `stop_rel` stay as Auckland Transport sent them. Empty `trip_id`
stays empty. The default window is 20 observations; `--limit` is 1–500 and
`--offset` is 0–20000.

The day file's byte length and sha256 must match the index, and the index `rows` value must match the number of stop rows.
A licence object other than CC BY 4.0, a non-JSON body, an off-host redirect,
HTTP 429 or HTTP 503 is an error, not an empty timetable.

## Tests

`scripts/test_contract.py` is offline. `scripts/smoke_test.py` replays fixtures
and then performs one live `day --latest` call (the index plus that one day).
Details and the column layout are in `references/source-notes.md`.
