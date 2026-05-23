# NZ Ferries API notes

This skill is an unofficial lightweight wrapper around public ferry operator website surfaces. It is read-only and does not support booking, payment, login, account, ticket, refund, or booking-management actions.

## Source and auth

No operator username, operator password, private token, account cookie, browser session, booking credential, or payment credential is required for the implemented operations.

Fullers/AT Metro service alerts use Auckland Transport's public API gateway with the same public subscription key pattern already used by the `at-transport` skill. Override it with `AT_API_KEY` if needed. Fullers scheduled sailings use the unauthenticated public static GTFS zip at `https://gtfs.at.govt.nz/gtfs.zip`.

Implemented live surfaces:

- SeaLink: `https://www.sealink.co.nz`
- Interislander: `https://www.interislander.co.nz`
- Bluebridge: `https://www.bluebridge.co.nz`
- Fullers360/AT Metro scheduled ferry sailings: `https://gtfs.at.govt.nz/gtfs.zip`
- Fullers360/AT Metro ferry service alerts: `https://api.at.govt.nz/realtime/legacy/servicealerts`

Reverse-engineered but not used directly by the shipped CLI:

- Fullers360: `https://www.fullers.co.nz`
- Fullers360 mobile app shell/API: `https://pim-mobile.fullers.co.nz`

Still delegated to `at-transport`:

- AT Metro ferry vehicle positions and full stop-departure workflows. AT routes include GTFS `route_type=4` ferries.

## Endpoint families used

### SeaLink schedules, fares, and availability

Bootstrap page:

```text
GET https://www.sealink.co.nz/ferry-schedules
```

The CLI first fetches the page with a cookie jar. Direct API calls without the page cookie returned empty schedule slots during testing, while the same request after page bootstrap returned public sailings.

Supporting public JSON:

```text
GET https://www.sealink.co.nz/api/system/terminalLocations
GET https://www.sealink.co.nz/api/booking/GetProductCategoryMatrix
GET https://www.sealink.co.nz/api/system/getTerminalProductMatrix
```

Schedule endpoint:

```text
POST https://www.sealink.co.nz/api/booking/getAvailableBookingSlots
Content-Type: application/json
X-Requested-With: XMLHttpRequest
Referer: https://www.sealink.co.nz/ferry-schedules
```

Payload shape:

```json
{
  "code": "AKLKPV",
  "date": "2026-05-24",
  "includeUnavailDates": false,
  "days": 1,
  "fareTypes": [
    {"code": "RETCAR+DR", "name": "Car + Driver", "quantity": 1, "type": "F"},
    {"code": "ADULT", "name": "Adult", "quantity": 1, "type": "F"}
  ],
  "promotion": ""
}
```

Observed route category codes:

- `AKLKPV`: Auckland destination code `AKL` to Waiheke `WHK`
- `KPAKLV`: Waiheke `WHK` to Auckland `AKL`
- `TOGBIV`: Auckland `AKL` to Great Barrier Island `GBI`
- `FRGBIV`: Great Barrier Island `GBI` to Auckland `AKL`

Terminal product prefixes from `getTerminalProductMatrix` filter route-specific slots:

- `HK`: Half Moon Bay to Kennedy Point
- `WK`: Auckland City/Hamer St to Kennedy Point
- Other terminal pairs are discovered from the live terminal matrix rather than hard-coded where possible.

Response shape:

- top-level `formattedDate`, `dateText`, `slots[]`
- each slot includes `departureLocation`, `arrivalLocation`, `departureTime`, `arrivalTime`, `ferryName`, `productCode`, `farePrice`, `fareTypes[]`, `limitedVehicleArea`, `pax`, `availabilityString`, and `status`

The CLI normalizes fare snapshots into a small `fare_summary` map and does not emit the full booking object.

### SeaLink alerts

Page:

```text
GET https://www.sealink.co.nz/travel-alerts
```

The page renders alert/reminder cards in `alert-reminder` blocks with title, body, kind, and updated date. The CLI parses those public cards.

### Interislander timetable

Page:

```text
GET https://www.interislander.co.nz/plan/ferry-timetable
```

Direct requests need a browser-like `User-Agent`; otherwise the environment observed `403 Forbidden`.

The page publishes daily departure times in an HTML table:

- Wellington to Picton
- Picton to Wellington

The page states the crossing takes about 3.5 hours. The CLI therefore estimates arrival times by adding 3 hours 30 minutes because the timetable table does not include arrival times.

### Interislander service alerts

Component page:

```text
GET https://www.interislander.co.nz/plan/service-alerts
```

Public JSON used by the page:

```text
GET https://www.interislander.co.nz/api/v1/disruption
X-Requested-With: XMLHttpRequest
Referer: https://www.interislander.co.nz/plan/service-alerts
```

Response shape:

- array of disruptions
- fields include `id`, `title`, `summary`, `content`, `start`, `end`, `last_edited`, `no_banner`, and `version`

HTML fields in `summary`/`content` are stripped for CLI output.

### Bluebridge timetable

Page:

```text
GET https://www.bluebridge.co.nz/timetable/
```

The public page renders seasonal timetable tables for:

- Wellington to Picton
- Picton to Wellington

The CLI parses the HTML tables and filters date ranges and day restrictions from the published notes, including:

- `Sailing not available on weekends`
- `Sailing is not available on Saturdays`
- `Sailing is not available on Sundays`

For notes such as `Sailing not available on Saturdays and some Sundays`, the CLI excludes Saturdays and keeps Sundays with the note because the page does not encode which Sundays are excluded.

### Bluebridge service alerts

Page:

```text
GET https://www.bluebridge.co.nz/service-alerts/
```

The CLI parses public headings and paragraphs from the service-alert page. During implementation testing it contained fare/fuel and roadworks notices rather than a structured JSON feed.

## Fullers360 schedules and alerts

The shipped Fullers implementation uses Auckland Transport public GTFS static schedules plus AT GTFS-RT service alerts. This covers the common Auckland ferry questions that need timetable data, including:

- `sailings auckland-devonport --operator fullers`
- `sailings auckland-waiheke --operator fullers`
- `next auckland-devonport --operator fullers`
- `alerts --operator fullers`

Static schedule zip:

```text
GET https://gtfs.at.govt.nz/gtfs.zip
```

The CLI reads these GTFS files from the zip:

- `agency.txt`
- `routes.txt`
- `stops.txt`
- `calendar.txt`
- `calendar_dates.txt`
- `trips.txt`
- `stop_times.txt`

It filters active services for the requested local `Pacific/Auckland` date, selects mapped ferry `route_id` values, and then extracts the first matching from-stop to later to-stop leg within each trip. GTFS times greater than `24:00:00` are normalized onto the next local day.

Mapped Fullers/metro ferry route IDs:

- `DEV-209`: Downtown to Devonport
- `MTIA-209`: Downtown to Waiheke/Matiatia
- `HMB-209`: Downtown to Half Moon Bay
- `HOBS-209`: Downtown to Hobsonville Point and Beach Haven
- `RANG-209`: Downtown/Devonport to Rangitoto
- `BAYS-240`: Downtown to Bayswater
- `BIRK-240`: Downtown to Birkenhead/Northcote/Bayswater
- `PINE-210`: Downtown to Pine Harbour
- `WSTH-211`: Downtown to West Harbour

Some Auckland ferry services requested under the user-facing Fullers coverage are represented in AT GTFS under non-`FGL` agency IDs because they are contracted metro ferry services. The normalized CLI operator remains `fullers360` for this route family, while JSON keeps the raw `gtfs_agency_id`, `gtfs_agency_name`, and `gtfs_route_id` for traceability.

Service alerts:

```text
GET https://api.at.govt.nz/realtime/legacy/servicealerts
Ocp-Apim-Subscription-Key: <AT_API_KEY>
```

The CLI filters GTFS-RT alert `informed_entity.route_id` values to the Fullers/metro ferry route IDs above and keeps alerts active now or overlapping the current NZ local day. The default key is the public AT developer key already used in the `at-transport` skill; override with `AT_API_KEY` if the gateway rotates.

### Fullers app/site discovery

The Fullers360 Android app reverse-engineering path was attempted first because mobile apps often expose less-guarded APIs.

Current app:

- Package: `nz.co.fullers.fullers360`
- App shell: `https://pim-mobile.fullers.co.nz/mobile-app/`
- Mobile API base observed in the web bundle: `https://pim-mobile.fullers.co.nz/`

Observed mobile endpoints:

```text
GET  api/public/app/version
GET  api/public/app
GET  api/public/app/content?id=<id>
GET  api/public/products
GET  api/public/products?from=<from>&to=<to>
GET  api/public/timetables/<from>/<to>
POST api/public/device
DELETE api/public/device
```

The APK includes a public Basic authorization header for the app's device-registration calls:

```text
Authorization: Basic YXBpLXVzZXI6RlVWeVpMUGtlcVlV
```

That decodes to a public app credential pattern used by the APK for `api/public/device`; it did not make the timetable/product endpoints usable from direct stdlib requests and is not used by the shipped CLI.

Website timetable discovery:

```text
GET https://www.fullers.co.nz/timetables-and-fares/?from=<from>&to=<to>&date=<MM/DD/YYYY>
X-Requested-With: XMLHttpRequest
```

The website `timetable-widget.js` requests this URL and parses the `.js.timetable-fares` fragment. CloakBrowser could load some fragments in a full browser context, but direct CLI requests to Fullers app/site endpoints returned Radware/hCaptcha/PerfDrive validation. Because the skill must remain stdlib-only and not depend on browser automation, those endpoints are documented as discovery context rather than shipped as a data source.

Use `at-transport` for Auckland Metro ferry vehicle positions and full stop-departure workflows. Use this skill for the normalized Fullers/AT Metro scheduled sailings and service alerts listed above.

## Normalized CLI schema

Each normalized sailing includes:

- `operator`, `operator_name`
- `route`, `route_name`, `date`
- `departure_location`, `arrival_location`
- `departure_time`, `arrival_time`
- `departure_datetime`, `arrival_datetime` in `Pacific/Auckland`
- `vessel`
- source-specific fields such as `product_code`, `availability`, `passenger_spaces`, `fare_summary`, `note`, and `source_url`

Each alert includes:

- `operator`, `operator_name`
- `kind`
- `title`
- `summary`
- `updated`
- `source_url`

## Stability and safety

- Treat schedule, fare, and availability data as a live public snapshot, not a guarantee.
- Booking availability can change after the query and may differ for residents, account holders, promotions, vehicle dimensions, pets, dangerous goods, or freight.
- Do not add booking, payment, login, account, ticket, refund, or mutation commands.
- Avoid high-volume scraping. Use narrow routes/dates and small `next` limits.
- Do not commit HAR captures, cookies, raw HTML dumps, screenshots, browser profiles, or JavaScript bundles when updating this skill.
