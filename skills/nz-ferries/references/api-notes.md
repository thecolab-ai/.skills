# NZ Ferries API notes

This skill is an unofficial lightweight wrapper around public ferry operator website surfaces. It is read-only and does not support booking, payment, login, account, ticket, refund, or booking-management actions.

## Source and auth

No username, password, API key, private token, account cookie, browser session, or payment credential is required for the implemented operations.

Implemented live surfaces:

- SeaLink: `https://www.sealink.co.nz`
- Interislander: `https://www.interislander.co.nz`
- Bluebridge: `https://www.bluebridge.co.nz`

Documented but not duplicated:

- Fullers360: `https://www.fullers.co.nz`
- Auckland Transport ferry GTFS/GTFS-RT: use the existing `at-transport` skill for AT Metro live ferry positions/departures. AT routes include GTFS `route_type=4` ferries.

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

## Fullers360 and AT boundary

Fullers360 is intentionally not implemented as a live Auckland Metro ferry tracker in this skill.

Reasons:

- The existing `at-transport` skill already covers Auckland Transport GTFS static routes and GTFS-RT real-time feeds. AT's route list includes ferry `route_type=4` routes, including Fullers/AT Metro routes such as Devonport, Half Moon Bay, Hobsonville, Bayswater, Birkenhead, Pine Harbour, Rangitoto-related services, and others.
- `nz-ferries` should not duplicate AT Metro live vehicle positions or stop departures.
- Direct Fullers360 timetable query pages with `from`/`to` parameters and customer-update pages returned hCaptcha/PerfDrive validation pages from this CLI environment. The route directory page without query parameters was reachable.

Use `at-transport` for Auckland Metro ferry live departures, alerts, vehicle positions, stops, and route data. Use Fullers360 web/app for any Fullers tourism timetable surfaces that are not exposed through AT.

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
