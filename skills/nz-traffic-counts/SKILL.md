---
name: nz-traffic-counts
description: "Query NZ traffic, cycle and pedestrian count sites and time series, from Auckland Transport, NZTA TMS, Heart of the City, Hamilton, Christchurch, Wellington and Tauranga. Use for historical volumes, active-mode monitoring and nearby count sites."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Auckland Transport; NZ Transport Agency; Heart of the City; Hamilton City Council; Christchurch City Council; Wellington City Council; Tauranga City Council"
  thecolab.source_type: "mixed"
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
  thecolab.source_url: "https://at.govt.nz/about-us/reports-publications/traffic-counts"
  thecolab.allowed_domains: "at.govt.nz,www.hotcity.co.nz,services.arcgis.com,services2.arcgis.com,services1.arcgis.com,cemeteryaws.tauranga.govt.nz,smartview.ccc.govt.nz,gis.wcc.govt.nz,gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ traffic counts

Use the stdlib Python CLI in `scripts/cli.py` for public traffic surveys, cycle
counts and pedestrian camera observations. Start with `sources`, choose a source,
then obtain the exact site identifier with `sites` before querying `counts`.

```bash
python3 scripts/cli.py sources --json
python3 scripts/cli.py sources --source wellington-sensors --json
python3 scripts/cli.py sites --source hamilton-traffic --limit 2 --json
python3 scripts/cli.py counts --source hamilton-traffic --site 2893 --from 2023-01-01 --to 2023-12-31 --json
python3 scripts/cli.py counts --source christchurch-cycle --site 100045582 --format geojson
python3 scripts/cli.py nearest --source wellington-sensors --near 174.7754,-41.3199 --limit 2 --format geojson
python3 scripts/cli.py counts --source wellington-sensors --site 48346 --from 2026-09-01 --to 2026-09-01 --json
python3 scripts/cli.py sites --source at-adt --bbox 174.74,-36.87,174.79,-36.83 --format geojson --json
python3 scripts/cli.py counts --source at-adt --site 23788:522 --json
python3 scripts/cli.py sites --source at-traffic --limit 5 --json
python3 scripts/cli.py counts --source at-traffic --site 6f28d534b38283b7 --from 2012-01-01 --to 2026-06-30 --json
python3 scripts/cli.py counts --source at-cycle-daily --site "Albany Highway Cyclist" --from 2026-07-01 --to 2026-07-31 --json
python3 scripts/cli.py counts --source at-cycle-monthly --site "Albany Highway Cyclist" --json
python3 scripts/cli.py sites --source nzta-tms --bbox 174.5,-37.2,175,-36.6 --json
python3 scripts/cli.py counts --source nzta-tms --site 00200444 --from 2018-01-01 --to 2018-01-01 --json
python3 scripts/cli.py counts --source hotcity --site "107 Quay Street" --from 2026-09-01 --to 2026-09-01 --json
python3 scripts/cli.py nearest --near 174.76,-36.85 --source at-adt --radius-km 1 --limit 3 --json
```

- `at-traffic`: the entire-network workbook's July 2012–June 2026 worksheet,
  including any earlier survey dates carried in that worksheet. Site IDs hash
  the exact area, road, carriageway endpoints, location and direction labels.
- `at-adt`: AT ArcGIS historic surveys. Site IDs are `carriageway:location`.
  Site listing uses `latest=Yes`; inspect each survey date because this flag
  can refer to a very old count. The current layer holds one survey per site.
- `at-cycle-daily`: published daily counter observations. Discovers the latest monthly file;
  date filters select matching monthly XLSX files on AT's download page.
- `at-cycle-monthly`: sums those daily observations by site and calendar month,
  retaining observed, published and missing-day counts. Date filters select
  overlapping months; totals include the whole published month, even when
  `--from`/`--to` falls within it. Missing values remain missing.
- `nzta-tms`: spatial site inventory joined operationally to the daily-count
  table through the site reference, preserving leading zeros. Inventory also
  contains virtual and inactive sites that may have no daily observations.
  Counts default to the last 30 days; explicit dates are preferable. Returns
  lane, direction and vehicle-class rows separately, preserving duplicates.
- `hotcity`: yearly hourly XLSX files; discovers the latest yearly download.
  Date filters discover the relevant yearly downloads. Site IDs are exact
  column labels, including spelling and line breaks. The 2026 workbook has
  24 camera series after three additions to the earlier network.

The four city sources also support `--bbox`, `nearest` and GeoJSON, including
spatial `counts` output. Filtering is upstream ArcGIS envelope intersection
(`esriSpatialRelIntersects`), except Christchurch point containment applied locally.
Wellington GeoJSON preserves countlines; nearest measures their vertex-mean centres.
Nearest searches within `--radius-km` (default 10 km), using straight-line
WGS84 distance; an empty result means no site in that radius. A supplied bbox
further defines the search area. Workbook `sites --format geojson` emits null
geometries, since those downloads do not supply coordinates.

- `hamilton-traffic`: annual `Year2000`–`Year2023` fields, preserving nulls.
  Site IDs use ArcGIS OBJECTID; `site_number` preserves the council label.
  Leading zeros are the same numeric id. `Direction=Both` and compass-direction
  rows are separate series; do not add them. Date filters use overlap with the
  whole year; `date` retains year precision. `latest_data` is the newest
  `YearYYYY` field on the returned records, not a survey day and not `--limit`.
- `tauranga-traffic`: latest survey ADT per UUID site, with heavy-vehicle percentage.
  Survey dates can be decades old even though the layer is refreshed. The
  published direction label is kept; do not add site rows together.
- `christchurch-cycle`: counter snapshot keyed by `oid`. The network total
  feature is omitted. `direction=one` and `direction=both` are separate
  non-additive series (12 one and 29 both on 2026-10-11). No observation date
  or period is supplied; date filters fail explicitly.
- `wellington-sensors`: monthly public CSV exports discovered from the S3 file
  listing, latest month by default. Counts remain separate by hour, class and
  direction and are ordered by date, hour, site, direction and class before
  `--limit`. Queries may span at most three published months (64 MiB each);
  missing months fail explicitly. Numeric ids ignore leading zeros. An id
  absent from both the mapped inventory and the small public countline metadata
  file is rejected before a monthly download. Historical metadata sites absent
  from the inventory retain null geometry. `wcc-arcgis-nz` reads the same
  mobility exports for general Wellington geospatial queries.

Hamilton pedestrian API S2745 is currently unavailable (timeout/HTTP 502); no
unverified response parser is bundled. No Dunedin-specific counter was found in
the assessed catalogue. NZTA inventory remains available nationally.

Every data command supports `--json`, emitting `meta` and `results`; errors add
an `error` object with code, type and message. GeoJSON carries `meta` as a foreign
member. Metadata includes UTC retrieval times, source-stated licences and source
currency (`latest_data`); record `date` is its observation date.
For Tauranga and Wellington, `meta.latest_data` is the latest survey or observation
date among rows that match the query, calculated before `--limit`. It is not the
retrieval time or an object LastModified timestamp. Undated responses
(including the source registry and Wellington inventory) return null with a note.
Hamilton `latest_data` is the newest `YearYYYY` field on the returned site records.
Each record references its exact query/download URL; workbook provenance appears
once in `meta.downloads`. Source listing is a verified registry,
not a health probe. Null counts are never converted to zero. Repeated NZTA daily
keys are flagged with a warning; review UTC timestamps before any aggregation.

Downloads and API queries cache inside `nz-traffic-counts-v1/` under this skill's ignored `.cache/` directory
for 24 hours. Set `--max-age SECONDS`, `--cache-dir PATH`, or `--max-age 0` to
refresh. Cache hits preserve the original retrieval time. `--limit` bounds
output (default 100); `--max-records` bounds ArcGIS retrieval (default 10,000, maximum 50,000),
with explicit truncation warnings. Requests use 10-second network timeouts and
32 MiB download caps (64 MiB for Wellington monthly CSVs). Never fetch the NZTA 1.7 GB quarter-hourly ZIP.

Read [references/source-notes.md](references/source-notes.md) for catalogue URLs,
reuse limits, archive coverage and interpretation. XLSX parsing uses `zipfile`
and `xml.etree.ElementTree`, with no openpyxl or installed dependencies.
Run `scripts/test_contract.py` for deterministic CLI and parser checks using
`tests/fixtures/`, or `scripts/smoke_test.py` for bounded live source probes.
