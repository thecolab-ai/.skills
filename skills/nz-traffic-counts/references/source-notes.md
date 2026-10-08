# Sources and interpretation

Verified from `akl-catalogue-v4.json` and public HTTP responses on 8 October 2026.
Authentication: none

Last verified: 2026-10-08

All access is keyless. `sources` exposes the pinned registry; time filters trigger
archive discovery for active-mode downloads, so discovery failures are explicit.

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
AT cycle counts and NZTA daily counts carry CC BY 4.0 in the catalogue. The cycle
page explicitly states CC BY 4.0. The pedestrian source does not state a licence
in the catalogue; output uses `licence: null` rather than assuming one.

## Formats

- AT traffic workbook (7,083,446 bytes verified): uses the named recent worksheet,
  whose first two rows are title and headers. Actual survey rows can predate the
  worksheet's July 2012 label. Do not equate ADT to a count on the survey start
  date: these are five-day and seven-day survey averages, with directional rows.
  Site IDs distinguish exact labels and direction; spelling changes create new
  IDs and are not silently joined to the ArcGIS road network.
- AT points: `carr_way_no`, `location`, `count_date`, `adt`, `latest`, `road_name`.
  Queries ask ArcGIS to project geometry from NZTM into EPSG:4326. Site listing
  keeps the most recent row per carriageway/location. `latest=Yes` describes the
  source's record choice, not currency; many sites have decades-old surveys.
  Raw percentage, peak and survey fields remain available in `raw`.
- AT July 2026 cycle workbook: `A3=Time`, with 83 counter columns and 31 daily rows.
  The landing page's 26-site headline is a reporting subset, not the number of
  columns. Missing cells stay null. Monthly CLI totals are derived from daily
  downloads, not the headline network total, and report observed/missing days.
  All seven 2026 download links are discovered from the page; January and July
  were exercised live. Date discovery currently recognises full month names in
  daily-cycle XLSX filenames. Old abbreviated filenames, CSV archives and
  separate multi-year workbook layouts are not supported by this parser.
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
  In the verified 2018 sample, duplicated local-date/lane/direction/class keys
  exist with differing timestamps. The CLI flags them and does not sum them.
  Never substitute the 1.7 GB quarter-hourly archive for a daily query.
- Heart of the City: `A=Date`, `B=Time`, remaining columns are camera series.
  The 2026 file has 24 series, with three new Commercial Bay cameras. Two
  directional columns can describe one physical location. Some names contain
  line breaks or source spelling errors; copy exact IDs from `sites` JSON.
  Calendar rows extend beyond the publication month with blank observations:
  discard dates after the last numeric observation and report September 2026
  as latest data. 2025 and 2026 yearly files were exercised live. The page offers
  2012–2026 annual downloads; older layouts have not all been verified.

## Bounds and fixtures

Every HTTP request has a 10-second timeout and 32 MiB cap; expanded workbook
members are capped at 256 MiB. XLSX uses workbook relationships, sparse cell
references, inline/shared rich strings and the 1900/1904 date epoch. Formula
cells use published cached values; formulas are never evaluated.

ArcGIS pages have at most 1,000 records. `--max-records` bounds traversal with
explicit warnings. Nearest fails if this bound truncates candidates, preserving
ranking correctness. Spatial inventory and counts are separate requests; each
record carries its own query URL. No geocoding or guessed coordinates are used.

Downloads cache by URL, preserve original retrieval timestamps, expire after
`--max-age`, and do not fall back to stale cached data on network errors. The
24-workbook discovery bound limits large archive requests; narrow the period to
continue. An output `--limit` does not limit workbook parsing or discovery.

`tests/fixtures/` holds trimmed source responses: CC BY AT/NZTA ArcGIS records,
cycle and pedestrian worksheet cells, and traffic workbook headers only.
Trimmed XLSX packages preserve actual cell values while removing unused workbook
metadata and converting retained shared strings to inline strings. Contract
and smoke scripts both execute `scripts/parser_tests.py`; the latter separately
reports live failures or network skips.
