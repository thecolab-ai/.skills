# Sources and interpretation

Verified from `akl-catalogue-v4.json` and public HTTP responses on 8 October 2026.
Authentication: none

Last verified: 2026-10-11

All access is keyless. `sources` exposes the pinned registry; active-mode commands discover
the latest file by default and matching archives with time filters, so discovery failures are explicit.

| Source | Catalogue row | Public endpoint |
|---|---|---|
| AT traffic workbook | C0032 | https://at.govt.nz/media/afhnimq4/at-web-traffic-count-july-2012-to-june-2026.xlsx |
| AT survey points | C0002 | https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/TrafficService/FeatureServer/0 |
| AT cycle download page | S0182 | https://at.govt.nz/cycling-walking/research-monitoring/monthly-cycle-monitoring/ |
| AT daily cycle snapshot | S0207 | https://at.govt.nz/media/zj0lgcmg/at-daily-cycle-count-data-july-2026.xlsx |
| NZTA daily counts table | C0018 | https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/TMS_Telemetry_Sites/FeatureServer/0 |
| NZTA site inventory | C0019 | https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/Assets_SHTrafficMonitoringSites/FeatureServer/0 |
| Pedestrian download page | C0033 | https://www.hotcity.co.nz/city-centre/results-and-statistics/pedestrian-counts |
| Pedestrian snapshot | C0033 | https://www.hotcity.co.nz/sites/20180201.prod.hotcity.co.nz/files/2026-10/All%20pedestrian%20data%20day%20by%20hour%202026%20-%20September.xlsx |

## Reuse

AT's [traffic count page](https://at.govt.nz/about-us/reports-publications/traffic-counts)
says workbook data is for individual use and cannot be republished without AT's
approval. This skill records that condition rather than labelling the workbook
CC BY. The bundled traffic workbook fixture contains **headers only**, with no
survey observations; live probes exercise the count parser. AT ArcGIS counts,
AT cycle counts and NZTA daily counts carry CC BY 4.0 in the catalogue. The AT
[TrafficService portal item](https://www.arcgis.com/home/item.html?id=a204ffd92f7546e898402e064bda6609)
explicitly states CC BY 4.0 in `licenseInfo` (verified 2026-10-08); this is separate
from the workbook terms. The cycle page explicitly states CC BY 4.0. Heart of
the City's pedestrian-counts page states CC BY 4.0 and requires attribution to
Heart of the City. Unknown licences are omitted from provenance metadata.

## Formats

- AT traffic workbook (7,083,446 bytes verified): uses the named recent worksheet,
  whose first two rows are title and headers. Actual survey rows can predate the
  worksheet's July 2012 label. The separate "Prior to July 2012" worksheet is
  omitted with a warning when `--from` precedes 2012-07-01. Exact duplicate rows
  in counts are preserved, marked `duplicate_row: true` and warned about.
  Do not equate ADT to a count on the survey start
  date: these are five-day and seven-day survey averages, with directional rows.
  Site IDs distinguish exact labels and direction; spelling changes create new
  IDs and are not silently joined to the ArcGIS road network.
- AT points: `carr_way_no`, `location`, `count_date`, `adt`, `latest`, `road_name`.
  Queries ask ArcGIS to project geometry from NZTM into EPSG:4326. Site listing
  keeps the most recent row per carriageway/location. `latest=Yes` describes the
  source's record choice, not currency; many sites have decades-old surveys.
  The current layer holds one survey per carriageway/location, all flagged Yes.
  Raw percentage, peak and survey fields remain available in `raw`.
- AT July 2026 cycle workbook: `A3=Time`, with 83 counter columns and 31 daily rows.
  Some 2024 files use `A3=Date`
  with the same column layout. August/September 2024 have helper columns A–F,
  `G=Date` and counter columns H onwards. These verified layouts are supported. The July 2020 file uses textual dates
  such as `Wednesday, 1 July 2020`, which are also parsed. July 2024 has an invalid `z` cell in
  Archibald Park Cyclists on 2024-07-15. `Pending` cells become null with a
  placeholder warning. Other requested non-numeric cycle cells become null with
  `invalid_count_raw` and a warning naming the workbook, site and date. Monthly
  sums retain those dates and raw values in `invalid_count_days`. Unrelated
  invalid cells are omitted from currency/site-date calculations with a warning.
  September 2024 also contains an extra 2024-08-31 row. Outside-month rows carry
  `date_outside_file_month: true` and a warning. When the selected nominal-month
  workbook supplies the same site/date and value, omit the extra row; conflicting
  values are preserved and flagged `duplicate_row` on both rows. If the nominal
  workbook lacks the observation, retain it. Outside-month partial groups omit
  `missing_days`; daily output is sorted by date then source URL.
  The landing page's 26-site headline is a reporting subset, not the number of
  columns. Missing cells stay null. Monthly CLI totals are derived from daily
  downloads, not the headline network total, and report observed/missing days.
  Discovery recognises full month names and token abbreviations (including
  `feb` and `sept`) in cycle XLSX filenames. Expected months are clamped to the earliest discovered monthly XLSX
  and the latest published/verified month. Missing supported downloads produce an explicit month list. Annual,
  multi-month, concatenated month/year names (such as `jan2020akld...`) and CSV
  layouts are unsupported. Empty archive selections report the earliest and
  latest published supported period. The latest monthly download is
  discovered for no-date queries; `CYCLE` is only a last-known snapshot.
- NZTA daily counts are a **table without geometry**, even though the service is
  called `TMS_Telemetry_Sites`. Fields: `SiteRef`, `siteID`, `startDate`,
  `siteDescription`, `laneNumber`, `flowDirection`, `classWeight`, `trafficCount`.
  Spatial inventory uses `siteref`; references preserve leading zeros. Its catalogue
  states 2025 as latest data, which site results retain separately from the 2026
  daily-count table. It includes
  virtual sites and non-continuous counters; inventory presence does not prove
  daily observations exist. Query bounds use UTC timestamp literals corresponding
  to NZ-local dates. Source timestamps include both UTC midnight and prior-day
  noon conventions: each result keeps its original UTC timestamp and raw fields.
  NZST-midnight (12:00Z) duplicates span 2017-12-31 through 2023-11-04,
  with about 1.6 million source rows in this convention (reviewer's source audit).
  The 2018 sample was also verified live. Repeated local-date/lane/direction/class
  keys have differing timestamps. `trafficCount` is a double and may be fractional
  (for example 5585.5 at site 05100015 on 2022-05-30). The CLI flags duplicate
  keys and does not sum them.
  Never substitute the 1.7 GB quarter-hourly archive for a daily query.
- Heart of the City: `A=Date`, `B=Time`, remaining columns are camera series.
  The 2026 file has 24 series, with three new Commercial Bay cameras. Two
  directional columns can describe one physical location. Some names contain
  line breaks or source spelling errors; copy exact IDs from `sites` JSON.
  Calendar rows extend beyond the publication month with blank observations:
  discard dates after the last in-year numeric observation. The no-date default
  discovers the newest annual link; `HOT` is a documented last-known September
  2026 URL. Placeholder strings (`-`, `–`, `n/a`, `na`, blank) become null with
  a substitution warning; other non-numeric counts fail. Older workbooks contain
  dates outside their filename year: preserve the supplied date, mark emitted
  rows `date_outside_file_year: true`, and warn with counts and dates. Never
  silently change the year. Only in-year numeric observations set source currency.

## Bounds and fixtures

Every HTTP request has a 10-second timeout and 32 MiB cap; expanded workbook
members are capped at 256 MiB. XLSX uses workbook relationships, sparse cell
references, inline/shared rich strings and the 1900/1904 date epoch. Formula
cells use published cached values; formulas are never evaluated.

ArcGIS pages have at most 1,000 records. `--max-records` bounds traversal with
explicit warnings. Nearest fails if this bound truncates candidates, preserving
ranking correctness. Spatial inventory and counts are separate requests; each
record references its query URL. Date-ordered pagination preserves a contiguous
returned period when capped; warnings state that period and possible
incompleteness. No geocoding or guessed coordinates are used.

Downloads cache by URL, preserve original retrieval timestamps, expire after
`--max-age`, and do not fall back to stale cached data on network errors. The
24-workbook discovery bound limits large archive requests; narrow the period to
continue. Counts build records only for the requested site and period.
Site listing retains
only header labels and first/last observation dates, merging the earliest and
latest non-null dates across every selected workbook. Its `date` is the last
observation. Workbook rows stream from
XML; no full series for every counter is retained. An output `--limit` does not
limit discovery. Cache writes are optional: failures warn and use downloaded data;
pruning touches only SHA-256 cache names in `nz-traffic-counts-v1/`.

`meta.latest_data` describes source currency except for Tauranga and Wellington,
where it is the maximum survey/observation date among rows that match the site,
date, spatial and nearest filters. That maximum is taken before `--limit`.
Responses without dated matched rows return `latest_data: null` with an
explanatory note, including source-registry and Wellington inventory responses.
A download entry can still carry the newest date in that file. Layer refresh
timestamps, retrieval time and object LastModified do not set this value.
Hamilton query `latest_data` is the newest `YearYYYY` field present on the
returned site records. It is a published field year, not a survey day, and a
date filter or `--limit` does not reduce it. The verified layer fields end at
`Year2023`.
ArcGIS counts use the verified registry value (AT 2026-06-23, NZTA 2026); NZTA
inventory retains its stated 2025 year. Workbooks use the maximum numeric date
in each yearly file's nominal year (or across a monthly file), across all sites
and independent of query bounds.
`meta.downloads` records each source file/query retrieval separately.
Workbook schema errors identify the failing filename and URL in the message,
with that URL and the attempted operation time in error provenance.
Discovery ends at today's NZ-local date when only `--from` is supplied. With
only `--to`, cycle starts at that month's first day, hotcity at that year's
first day, and NZTA 30 days before `--to`. Resolved reversed dates fail with code 2.

`tests/fixtures/` holds trimmed source responses: CC BY AT/NZTA ArcGIS records,
cycle and CC BY 4.0 Heart of the City pedestrian worksheet cells (attribute Heart
of the City), a captured public cycle download link list, and traffic workbook
headers only. Additional edge-case workbooks are inline synthetic sheets.
Trimmed XLSX packages preserve actual cell values while removing unused workbook
metadata and converting retained shared strings to inline strings. Contract
and smoke scripts both execute `scripts/parser_tests.py`; the latter separately
reports live failures or network skips.

## Additional cities (lane M10, verified 2026-10-08)

| Source | Catalogue | Endpoint |
|---|---|---|
| Hamilton traffic | S1098 | https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/Hamilton%20City%20Traffic%20Counts/FeatureServer/0 |
| Tauranga latest traffic | S1373 | https://cemeteryaws.tauranga.govt.nz/server/rest/services/Mapi_Transportation/MapServer/17 |
| Christchurch cycle snapshot | S2160 | https://smartview.ccc.govt.nz/app/router/map_features.php?feat=ecocounter |
| Wellington countlines | S1096 / S2741 | https://gis.wcc.govt.nz/arcgis/rest/services/Transportation/Transport_Sensors/FeatureServer/0 |
| Wellington public monthly exports | S1096 / S2741 | https://gis-snowflake-opendata-public-wcc-arcgis-prod.s3.ap-southeast-2.amazonaws.com/ |

Hamilton has 765 points and annual `Year2000`–`Year2023` fields. `site_id` is
OBJECTID, since the council's `Site_Number` label need not identify a unique
feature. A leading-zero form such as `02893` is the same numeric id. Annual
values retain year precision and null values. Zero is a published value. A
negative annual value is not a missing-value sentinel and fails schema
validation; null remains null. Date filtering uses year overlap, without
inventing a survey day or treating the value as a whole-year volume. Verified
direction labels are `Both` (543), `North` (69), `South` (67), `East` (43) and
`West` (43). `series_role` is `both_directions` or `single_direction` only for
those exact labels. Do not add a Both row to a compass-direction row, and do
not treat Both as their sum. Null point coordinates are omitted, with a
warning; the site remains in the result and is excluded from nearest. Raw
fields preserve direction and location descriptions.

Tauranga has 969 points with UUID `id`, `road_id`, `ADT`, `PcHeavy`, `count_date`
and `SDE_Load_Date`. The CLI preserves survey dates, ADT and heavy-vehicle share.
A load timestamp is not an observation date; currency is the newest survey date
among matched rows before `--limit`, not the catalogue's layer-refresh year.
Some latest surveys are decades old. Every verified row uses direction
`Both lanes` (`series_role=both_lanes`). That label is not split into lanes,
and rows are not added together. Negative ADT or heavy-vehicle values fail
schema validation. Null point coordinates are omitted with a warning rather
than a traceback. Copyright terms do not establish a Creative Commons licence.
The catalogue's flume-results caveat on S1373 is unrelated to the live traffic
schema and is not repeated.

Christchurch supplies 42 GeoJSON features with `oid`, `name`, string or numeric
`count`, `direction`, `installed_on` and `hide`. One feature is the network
total (`total` true and `oid` `total`) and has a display coordinate. It is
omitted from site, nearest and count results. The other 41 are counter series:
29 have `direction=both` and 12 have `direction=one` (verified 2026-10-11).
They are not all directional series. `series_role` records that published
label and nothing else. Do not add a both-direction series to a
single-direction series. Names such as "total cyclists" stay separate rows;
the name is not evidence that the CLI should sum other series. The installation
date is not the count observation date. There is no timestamp or period, so
`latest_data` and `date` are omitted and date filters fail. No data reuse
licence is stated. Public GeoJSON access requires no Eco-Counter key. Negative
counts fail schema validation.

Wellington has 408 mapped countlines (polylines, queried with `outSR=4326`).
GeoJSON preserves those lines; nearest uses the mean of the published vertices,
not a point-to-line distance. CSV joining uses numeric `COUNTLINE_ID`: `048346`
and `48346` are the same site. The public S3 ListObjectsV2 listing is filtered
to the observed monthly key structure; annual and all-history exports are
excluded. No-date counts discover the latest published month (October 2026 at
verification). Date filters select at most three monthly files, and missing
months or truncated listings fail explicitly. Only the requested site's
observations are retained. Matched rows are sorted by date, hour, site,
direction and class before `--limit`. Upstream CSV order is not stable.
`meta.latest_data` is the newest date among those matched rows before the
limit. Each CSV's `meta.downloads` entry retains the maximum date across the
entire downloaded CSV, including other sites. Neither value is LastModified.
Every monthly download has a 64 MiB cap and 10-second HTTP timeout; the rest
retain 32 MiB caps. S3 monthly CSVs use a stdlib streaming reader with a fixed
host/path, disabled redirects and Content-Length completion checks, since
nzfetch cannot raise its 32 MiB wire ceiling. CSV schema:
`COUNTLINE_ID,COUNTLINE_DATE,COUNTLINE_HOUR,DIRECTION_COUNT,COUNTLINE_TRANSPORT_CLASS,DIRECTION`.
Blank `DIRECTION_COUNT` stays null. A negative count is not a documented
missing sentinel and fails schema validation. A missing or non-integer hour,
or a CSV field over the parser field-size cap, is `schema_failure` (exit 6)
and names the monthly download URL. Hourly records preserve mode and direction
and never fill gaps. An empty date match says the site exists and that no rows
matched; it is not an unknown-site error.

Public countline metadata is
`transport_sensors/countline_meta_info/csv/countline_meta_info.csv` (411 rows
on 2026-10-11; about 68 KiB). Columns include `COUNTLINE_ID`, `NAME`,
`PRIMARY_TRANSPORT_CLASS`, line endpoints, `DIRECTION_IN`, `DIRECTION_OUT`,
`EARLIEST` and `LATEST`. This skill uses that file as the bounded id inventory
when the mapped FeatureServer does not contain the id, so an unknown numeric
id is rejected before a monthly CSV of about 15–49 MiB. It does not copy names
into count records. A metadata id absent from the current map is still read
from the monthly export and keeps null geometry. `wcc-arcgis-nz` deliberately
reads these same S3 mobility exports for general Wellington City Council and
Greater Wellington geospatial queries. This skill is the traffic and
active-mode count adapter. WCC metadata states open urban mobility use and
directs other uses to WCC; no named CC licence is asserted. Nearby sensors can
count the same person twice.

Robots checks found no applicable disallow directives on these public data hosts
(missing robots files, HTML fallbacks, or ArcGIS's invalid-URL response). Access
uses the public APIs and published exports; no dashboard scraping is required.

### Investigated but unavailable or outside this adapter

- **Hamilton pedestrians S2745**: exact documented endpoint
  https://api.hcc.govt.nz/OpenData/get_Pedestrian_count?Page=1&Start_Date=2020-10-01&End_Date=2020-10-02
  timed out, then returned HTTP 502 `NoResponse` on two requests (also tested
  2026-10-01 to 2026-10-02). No response fields could be verified. Deferred,
  rather than bundling a guessed parser. Robots returned 404. Council catalogue
  terms request attribution and a derivative notice; availability is uncertain.
- **Dunedin**: no pedestrian/cycle/traffic-counter dataset found in the assessed
  catalogue using the requested terms and city searches. National `nzta-tms`
  remains usable for regional road counters. No city source has been invented.
- **Christchurch traffic S2163/S2164**: public council dashboard pages previously
  returned 403 again on verification; they expose no direct data endpoint in the catalogue. The
  S2092/S2094 Google Drive archives contain individually named survey workbooks
  and raw MetroCount files; automated discovery and those formats are outside
  this bounded counter adapter. The two exact catalogue download URLs returned
  HTTP 200 (796,404 and 214,408 bytes); they are not blocked or key-gated. Power BI S2093 supplies no documented count API.

New `hamilton-traffic.json`, `tauranga-traffic.json`, `christchurch-cycle.json`,
`wellington-lines.json`, `wellington-counts.csv` and `wellington-list.xml` fixtures
contain invented IDs, names, counts and coordinates in verified response shapes.
Existing fixtures are unchanged. `scripts/city_tests.py` runs through both the
contract and smoke entrypoints and covers city parsing, provenance and errors.
