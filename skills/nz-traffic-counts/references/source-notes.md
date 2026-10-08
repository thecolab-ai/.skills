# Sources and interpretation

Verified from `akl-catalogue-v4.json` and public HTTP responses on 8 October 2026.
Authentication: none

Last verified: 2026-10-08

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

`meta.latest_data` describes source currency, never the queried record date.
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
