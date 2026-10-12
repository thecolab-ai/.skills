# Verified sources and definitions

Authentication: none

Last verified: 2026-10-08

Verified 8 October 2026. Discovery came from `nz-data-catalogue` records S0183,
S0269/S0180, S0547, S0522 and S0668. URLs below returned HTTP 200 unless stated.
The CLI discovers download links from the official pages rather than inventing
future filenames. Newest links appear first on the verified pages.

## Auckland Transport

Landing page: https://at.govt.nz/about-us/reports-publications/at-metro-patronage-report/

- Daily mode totals: https://at.govt.nz/media/doulq40v/auckland-transport-bus-train-ferry-boardings-by-day-to-27-september.xlsx
  (`Data`, 89 days, 1 July–27 September 2026; 26,278 bytes).
- Monthly mode and route counts: https://at.govt.nz/media/0hzhp545/auckland-transport-monthly-bus-train-ferry-boardings-to-august-2026.xlsx
  (`Monthly by Mode`, `Monthly by Route`, July–August 2026; 73,365 bytes).
- Monthly punctuality and reliability: https://at.govt.nz/media/azidohev/auckland-transport-monthly-punctuality-and-reliability-to-august-2026.xlsx
  (`Punctuality`, `Reliability`, July–August 2026; 114,886 bytes).

Monthly route headers contain Excel month-start serial dates through June 2027,
but future measurement cells are empty. Only populated observations determine
`latest_data`. Total and subtotal rows are excluded from route outputs to prevent
double counting. Leading zeroes and letter route identifiers remain strings.
Older linked fiscal-year files are searched for date-filtered AT requests, at
most four files per command. July 2023 is the current earliest linked fiscal year.
More distant requests may yield partial or empty coverage; check metadata.

Daily boardings include HOP, contactless payments, rail line transfers and manual
adjustments but exclude special events and train group travel. Monthly totals
include invalid travel, special events and train group travel. `ADJUST` and
`Unknown` are published route categories, not physical routes. Boardings do not
measure onboard loads, unique travellers or complete origin/destination trips.

Punctuality measures operated trips departing the first stop within -0:59 to
+4:59 minutes of schedule and reaching the last stop no later than +4:59. Ferry
punctuality uses only the first stop due to data acquisition limits. Reliability
measures scheduled trips operated. These are aggregates without contractual
exemptions and cannot establish an individual trip's delay.

The catalogue labels AT downloads CC BY 4.0, but the live workbook/landing page
did not establish a workbook-specific CC licence. The CLI therefore records the
verified website copyright terms, not an inferred CC licence:
https://at.govt.nz/about-us/about-this-site/terms-conditions/copyright-statement
These permit a personal, non-commercial download and accurate, attributed,
non-misleading reproduction. Confirm any broader reuse with AT.

## Parking restriction and explicit inventory fallback

Requested short-term endpoint (not fetched):
https://at.govt.nz/umbraco/surface/parkingavailabilitysurface/ParkingAvailabilityResult?carparkIds=civic%2C+victoria+st&categories=short-term

https://at.govt.nz/robots.txt returned `Disallow: /umbraco/`. The `carparks`
command reports this restriction, and `sources` checks the robots file without
querying the disallowed endpoint. If policy changes, a maintainer must verify
permission and the actual HTML fragment before enabling its parser.

Explicit `carparks --inventory` endpoint:
https://services2.arcgis.com/JkPEgZJGxhSjYOo0/arcgis/rest/services/ParkingService/FeatureServer/1/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json

This returned 138 facilities, only two with populated `AVAILABLESPACES` fields
(Henderson Library and McCrae Way), not the requested Civic and Victoria Street
short-term vacancies. Null availability means unreported, not full. Geometry is
requested in WGS84; bbox filtering uses inclusive point containment locally.
The response is checked for `exceededTransferLimit` to prevent silently partial
results. The inventory has no vacancy observation timestamp. Layer edit times
are not vacancy observation dates and are not emitted as `latest_data`.
Its layer metadata has an empty copyright field; the CLI omits an unverified
licence for this fallback rather than applying website or catalogue terms.

## Metlink daily bus performance

Page: https://www.metlink.org.nz/about-us/performance-of-our-network

CSV: https://www.metlink.org.nz/assets/Policies-and-reports/Performance-of-our-network/Performance-Metrics/metlink-daily-bus-performance-2025-06-30-to-2026-09-27.csv

Definitions: https://www.metlink.org.nz/assets/Policies-and-reports/Performance-of-our-network/Performance-Metrics/metlink-bus-performance-csv-readme.txt

The verified CSV has 30,360 route/day records, 86 distinct routes and 36 columns,
covering 30 June 2025–27 September 2026 (4,172,788 bytes). The CLI preserves its
column names and casts numeric values; blank numeric cells become null. Rates
and punctuality/reliability values are fractions; mean departure time variance
is seconds. `license_capacity` is the upstream column spelling.

Capacity is summed across vehicles operating scheduled trips, not a single
vehicle's capacity. Patronage counts boardings; documentation describes Snapper,
and the current page notes Stripe EMV inclusion for Airport Express in current
files (excluded from historic files). Peak boarding times are 06:30–09:00 and
15:00–18:00 on non-public-holiday weekdays; peak service metrics classify trips
by scheduled start time. Metlink punctuality uses first-stop departure within
1m15s early or 5m15s late, with sighted trips as denominator. AT and Metlink
percentages are therefore not directly interchangeable.

No reuse licence was stated on the linked data page. Licence is omitted from
Metlink provenance. The public robots.txt path returned a not-found message,
with no applicable disallow rule observed. No authentication or browser used.

## Implementation and output

XLSX parsing uses `zipfile` and `xml.etree.ElementTree`, relationship-based sheet
selection, shared and inline strings, cached formula values and both Excel date
epochs. It does not calculate formulas. Invalid schemas, numeric values and
Excel errors fail with exit 6 rather than reporting an empty successful dataset.

`meta` contains source URL, publisher, original UTC retrieval time, applicable
known reuse terms, and latest populated reporting period. AT and Metlink data
rows also carry provenance, allowing older workbook records to retain their own
source URLs and timestamps. `latest_data` describes the whole downloaded file,
not necessarily the selected route or date. `coverage_from` is the earliest
populated period in the consulted files. `queried_sources` lists those files.

Cache entries are URL-keyed, expire after at most 86,400 seconds, and are bounded
to 16 files. Expired data are never substituted for a failed refresh. JSON
errors use codes 2 (input), 4 (blocked/rate-limited), 5 (network/local cache) and
6 (schema). Rate-limit errors preserve `Retry-After` when available.
