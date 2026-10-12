# Source access and schemas

Authentication: none

Last verified: 2026-10-08

Verified 8 October 2026. Exact source URLs were found through
`nz-data-catalogue search outage`, `search watercare faults`, `search rail closure`
and `search planned works`, then fetched from their public endpoints. The adapter
uses the repository's stdlib `nzfetch` helper with 10 s timeouts. Bare requests
can return HTTP 403 where browser-shaped public HTTP headers succeed. No token,
API key, browser automation, login or account operation is used.

## Supported sources

| Catalogue | Publisher | Public endpoint |
|---|---|---|
| S0262 | Watercare Services Limited | <https://webapi.watercare.co.nz/faults-outages/content> |
| S2574 | Wellington Electricity Lines Limited | <https://www.welectricity.co.nz/outages/getalloutages> |
| S0271 | KiwiRail | <https://www.kiwirail.co.nz/our-network/our-regions/amp/upcoming-work/> |
| S0270 | KiwiRail | <https://www.kiwirail.co.nz/assets/Uploads/Our-network/Our-regions/Auckland-Metro-Rail/BOL-Calendar-for-website_new.pdf> |

Watercare's [public map](https://www.watercare.co.nz/home/faults-and-outages)
robots.txt allows all paths. The API host's robots.txt is unavailable (403),
while the documented public JSON GET succeeds. This adapter consumes that
first-party feed rather than scraping hidden paths. Wellington's robots.txt
returns 404. KiwiRail disallows `/admin` and `/Security/`; neither is accessed.
No dataset-specific open licence was identified for Watercare or Wellington;
licence is omitted rather than substituting the skill's MIT code licence.
KiwiRail's copyright notice is preserved, without claiming open reuse rights.

### Watercare

The response is an array with `id`, `name`, `description`, `type` (`planned` or
`unplanned`), `address`, `start_time`, `estimated_resolution_time`, `createdAt`,
`updatedAt`, `location.coordinates.lat/lng`, `documentId`, `publishedAt`, and
`water_tanker_on_site`. UTC timestamps contain `Z`. The normalised `latest_data`
is the record's source-stated `updatedAt`, retaining original precision.
`estimated_resolution_time` is an estimate, not restoration confirmation.
No numerical affected count is published; address ranges are not counted.
The location is a point, not an outage boundary.

### Wellington Electricity

JSON is served with `text/html` content type, so the adapter reads text then
parses JSON; HTML challenge/error pages fail rather than returning no outages.
The object has arrays `plannedOutages` and `unplannedOutages`.

Planned fields: `id`, `type`, `status`, `timeBasedStatus`, `outageStartDateTime`,
`outageEndDateTime`, `customersAffected`, `reasonForOutage`, `useAlternateDate`,
`alternateStartDateTime`, `alternateEndDateTime`, `suburbsText`, `location.lat/lng`.
Unplanned fields: `timeOfFault`, `lastUpdatedCustomersAffected`, `lastUpdatedTime`,
`lastUpdatedEta`, `lastUpdatedComments`, plus the common identifiers and location.
The `areas` array contains representative streets, not boundaries.

Naive dates are interpreted as NZ local time using `Pacific/Auckland` and
normalised to UTC. `latest_data` preserves the source's literal `lastUpdatedTime`
when present (a local NZ timestamp). Closed records are resolved, cancelled
records cancelled; past estimated windows without confirmation are unknown.
The feed includes historical/recent rows; use `--status` to select current/planned.

### KiwiRail works

Only headings and paragraphs within `<main>` are parsed. Short-term and ongoing
work sections are recognised explicitly. Continuation paragraphs form one
notice; other page background and navigation are excluded. Dated notices need
both two full day/month values and one unambiguous year in the notice or its
linked document filename. No year is inferred from retrieval time. Otherwise
start/end are null and the original notice is preserved. Dates are inclusive.
A rail bridge noise information notice is `rail_notice` with unknown status,
not a confirmed outage. Notice IDs follow current document order and may change
when the page is edited. The page has no source update timestamp, so no
`latest_data` is supplied for work notices.

The page refers to a Metro Maintenance Plan timetable, but no timetable rows
were present in the verified HTML. This skill does not invent those rows or
interpret video content. All works have null geometry and affected count.

### Rail PDF calendar

The verified one-page PDF is labelled “2026 Rail Closures” but contains January,
February, March, April and May only, dated 2/02/2026. The PDF explains that dates
can change and concern AT metro services; freight may retain partial access.

The restricted PDF reader follows the page's explicit content-stream references,
decodes bounded Flate streams, reads positioned literal day/month text, and joins
each day to its filled CMYK rectangle. It verifies both legend labels, recognised
colours, one publication date, complete day grids and contiguous month coverage.
It supports the verified full closure grey and partial closure blue/tint. It
rejects encryption, multiple pages, transformed rectangles, unknown colours,
incomplete grids and changed source layouts as schema failure. It is not a
universal PDF reader. Poppler was used only to cross-check live verification;
runtime and synthetic fixtures require only Python stdlib.

Each coloured date is one record. `kind` distinguishes `full_network_closure`
from `partial_closure_or_reduced_frequency`. There are no precise service hours
or line extents to infer. `latest_data` is the calendar's printed publication
date, not its PDF file metadata or today's date. Coverage travels in `meta` even
for empty date filters. Inspect AT's [train line status](https://at.govt.nz/bus-train-ferry/train-services/train-line-status)
for passenger service details; the adapter does not fetch AT.

## Explicitly skipped sources

- **S0273 Vector Outage Centre**: <https://help.vector.co.nz/> returns a public
  client-rendered application shell with no outage records. `/robots.txt` returns
  the same application shell. Its publicly linked application code contains
  relative outage paths and depends on external runtime API configuration; an
  absolute, keyless data endpoint was not established. No confirmed keyless feed
  is supplied by the catalogue. No configuration, tokens or protected APIs are read. `outages
  --utility vector` returns code 7 with the official manual-map link in `meta`.
- **S2573 Counties Energy**: <https://app.countiesenergy.co.nz/> robots retrieval
  was blocked (403); the catalogue's
  <https://api.integration.countiesenergy.co.nz/user/v1.0/outages> probe was also
  403. Catalogue terms note written permission to reproduce content. Fetching is
  disabled (code 4); no authentication or challenge bypass is attempted.
- **S2575 PowerNet**: <https://powernet.co.nz/wp-json/pnl/v2/future> returned public
  structured planned outages, but [Terms of Use](https://powernet.co.nz/terms-of-use/)
  sections 2.2 and 3.2 require written consent for content use/reproduction except
  as permitted by law. The adapter is disabled (code 7). Public reachability does
  not establish permission. No PowerNet ICP identifiers or data are bundled.
- **S0260 Vector network projects**: the catalogue lists an ArcGIS project layer,
  which describes forward electricity/gas works rather than outage incidents.
  The host's robots check was blocked. No project fetch adapter is added here;
  coordinate with `nz-arcgis` for access/terms verification.
- **S2576 Transpower annual transmission outage plan** is an XLSX forward plan,
  distinct from consumer distribution interruptions. It is outside the current
  adapters; source licence/access and stdlib workbook parsing need their own review.

Sources lists are a local verified registry, with `retrieval_kind` identifying
that mode and `verified_on` identifying the access assessment date. Registry
retrieval timestamps do not claim a fresh live outage fetch.
