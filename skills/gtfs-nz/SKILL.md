---
name: gtfs-nz
description: "Read NZ public transport GTFS static timetables: feeds, stops, routes, trips, scheduled departures and route geometry. Use for Auckland Transport, Metlink (Wellington), BUSIT (Waikato) and Orbus (Otago) schedule baselines, spatial stop queries and timetable analysis."
license: MIT
compatibility: "Requires Python 3.10+ with Pacific/Auckland timezone data and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "NZ public transport agencies"
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
  thecolab.source_url: "https://gtfs.at.govt.nz/gtfs.zip"
  thecolab.allowed_domains: "gtfs.at.govt.nz,static.opendata.metlink.org.nz,wrcscheduledata.blob.core.windows.net,www.orc.govt.nz"
  thecolab.last_verified: "2026-10-08"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ GTFS static timetables

Use `scripts/cli.py` for keyless NZ timetable baselines: registered feeds, stops,
routes, trips, scheduled departures and route shapes. Python stdlib only.
AT realtime departures, vehicles and alerts belong to `at-transport`, which
requires the user-supplied `AT_API_KEY`. This skill does not query realtime APIs.

## Workflow

1. Run `feeds --json` to check the registry and feed validity dates; add `--refresh` for a live download.
2. Select `--feed at`, `metlink`, `busit` or `orbus`.
3. Look up stops/routes first; use their exact GTFS IDs for departures/trips/shapes.
4. Check `meta.warnings`, `meta.latest_data`, `meta.truncated` and the service date before using
   results. Static departures are schedules, not predictions or proof of operation.

## Commands

Run `python3 skills/gtfs-nz/scripts/cli.py <command> [flags]`.
Every command supports `--json`, `--cache-dir PATH`, and `--max-age SECONDS`
(default 86400). Every command supports `--refresh`; data queries support `--limit N` (default 100,
maximum 10000). All commands reuse fresh ZIPs unless `--refresh` is given. Expired caches are refreshed; a failed refresh is an error.

- `feeds [--feed at|metlink|busit|orbus]`: verified registry, cached or live download status,
  ZIP size, table names and original `feed_info` records. Per-feed failures have
  a status and error; partial failures also add `meta.warnings`. A total outage fails
  with a non-zero exit code. Each available record reports `cached`.
- `stops --feed at [--bbox minLon,minLat,maxLon,maxLat] [--near lon,lat --radius METRES] [--format json|geojson]`:
  WGS84 stop locations; radius defaults to 500 m. Nearby results sort by distance.
  Both spatial filters may be combined. Non-spatial JSON can retain stops without
  coordinates; spatial output excludes those stops.
- `routes --feed at [--type bus|rail|ferry|tram|cable|other]`: original route columns plus `mode`.
  Standard and extended GTFS types map to these modes (including school buses);
  unrecognised types map to `other`. See source notes for the mapping.
- `trips --feed at --route ROUTE`: timetable trips, including service and shape IDs.
  Lists all published trips, not only trips operating today.
- `departures --feed at --stop STOP [--date YYYY-MM-DD] [--time HH:MM[:SS]]`:
  departures from `stop_times` joined to trips, `calendar` and `calendar_dates`.
  Date defaults to today in Pacific/Auckland; time defaults to `00:00` and is an
  inclusive minimum. Results sort by scheduled time. Parent stations include their
  child platforms. Use exact stop IDs or unambiguous stop codes.
- `shapes --feed at --route ROUTE --format geojson [--bbox minLon,minLat,maxLon,maxLat]`:
  one LineString per published shape, sorted by numeric point sequence. A bbox
  selects intersecting shapes and returns their complete geometry; it does not clip.

Routes accept exact `route_id` or an unambiguous `route_short_name`.
IDs can change between feed versions. Negative coordinate strings are easiest
with `--bbox=...` or `--near=...`.

```bash
python3 skills/gtfs-nz/scripts/cli.py feeds --json
python3 skills/gtfs-nz/scripts/cli.py stops --feed at --near 174.768,-36.844 --radius 500 --format geojson --json
python3 skills/gtfs-nz/scripts/cli.py stops --feed metlink --bbox=174.75,-41.30,174.80,-41.25 --json
python3 skills/gtfs-nz/scripts/cli.py routes --feed at --type rail --json
python3 skills/gtfs-nz/scripts/cli.py trips --feed at --route 101-202 --json
python3 skills/gtfs-nz/scripts/cli.py departures --feed at --stop 11814 --date 2026-10-16 --time 08:00 --json
python3 skills/gtfs-nz/scripts/cli.py shapes --feed at --route 101-202 --format geojson --json
```

## Interpretation and output

`--date` is a **GTFS service date**, not a civil-day window. `25:10:00` means
01:10 after that service date and stays attached to that service's calendar.
For early-morning civil-day analysis, query the previous service date with
`--time 24:00` as well as the current one. No UTC timestamps are fabricated across
NZ daylight saving transitions.

JSON successes use `{"meta": {...}, "results": [...]}`. Spatial GeoJSON uses
`type`, `features` and the same `meta` foreign member; `--format geojson` implies
machine-readable output, including errors. Provenance lives under `meta`:
`source_url`, `publisher` and ISO UTC `retrieved_at`, plus `licence` when known.
For the mixed-source `feeds` command, records also carry each source's provenance.
`meta.latest_data` is the stated validity range as an ISO date string (start/end);
`meta.feed_info` retains source dates and version. These are validity dates, not
publication timestamps. BUSIT has no `feed_info.txt`, so `latest_data` is omitted
with a warning and its unknown licence is omitted. Cache hits retain the original
retrieval time. `meta.total` counts all matches; `meta.returned` and
`meta.truncated` describe the output limit. Original GTFS identifiers and most
columns remain strings; spatial stop coordinates become numbers.

Departures exclude stops with `pickup_type=1`. Terminal rows remain visible with
`terminates: true`; these are terminal arrivals, so filter them out for boarding
analysis. Untimed stop_times are counted and warned about rather than interpolated.
Conditional pickup fields remain visible. Frequency-based trips serving the selected
stop on the service date are unsupported (exit 7); unrelated frequency trips add a
warning. No journey planning, realtime conditions or frequency expansion is provided.

## Resources

- Read [references/source-notes.md](references/source-notes.md) for verified
  endpoints, licences, cache/memory limits and fixture provenance.
- `scripts/test_contract.py`: deterministic CLI and GTFS edge-case checks using
  `tests/fixtures/at-sample.zip`, trimmed from the real AT feed.
- `scripts/smoke_test.py`: bounded fixture and live feed/query checks.

Default cache: `$XDG_CACHE_HOME/thecolab-gtfs-nz` (or `~/.cache/thecolab-gtfs-nz`).
Set `GTFS_NZ_CACHE_DIR` or `--cache-dir` to override it. Downloads have a 10 s
socket timeout and a 50 s download deadline, a 128 MiB compressed cap and 1 GiB expanded-size cap; tables are
streamed from the ZIP without extracting files. Errors have actionable messages
and repository exit codes (2 input, 4 access, 5 network, 6 parser/cache, 7 unsupported).
