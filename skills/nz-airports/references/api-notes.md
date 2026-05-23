# NZ Airports API notes

This skill is an unofficial lightweight wrapper around public airport flight-board surfaces and the adsb.lol community ADS-B feed for Auckland. It is read-only and does not support booking, check-in, PNR lookup, account access, or passenger/baggage ownership lookup.

## Source and auth

No personal username, password, API key, private token, cookie, or browser session is required for the implemented commands.

AKL FIDS uses Auckland Airport mobile app v5 Basic auth. The default credentials are the public app credentials embedded in the Auckland Airport Android APK v8.2.2, not a user credential. They can be overridden with:

- `AKL_API_USERNAME`
- `AKL_API_PASSWORD`

Implemented airports:

- Auckland (AKL) scheduled FIDS default: `https://h2g.aucklandairport.co.nz`
- Auckland (AKL) live ADS-B optional source: `https://api.adsb.lol`
- Christchurch (CHC): `https://www.christchurchairport.nz`
- Queenstown (ZQN): `https://www.queenstownairport.co.nz`
- Wellington (WLG): `https://www.wellingtonairport.co.nz`

Investigated with alternate implementation:

- Auckland Airport's public website flight-board API and pages, including `https://www.prod.aucklandairport.co.nz/flights`, `https://corporate.aucklandairport.co.nz/content/aial-traveller/nz/en/flights.html`, and `https://www.aucklandairport.co.nz/content/aial/api/v1/flights`, returned Cloudflare challenge/block pages from direct CLI fetches. CloakBrowser CDP navigation also returned a Cloudflare 403 block in this environment. AKL scheduled data is therefore implemented through the mobile app v5 FIDS API instead.

## Endpoint families used

### Auckland Airport scheduled FIDS via mobile app v5 API

Base endpoint:

```text
GET https://h2g.aucklandairport.co.nz/api/{arrivals|departures}?range={domestic|international}&date={YYYY-MM-DD}
```

The CLI calls all four combinations for today's `Pacific/Auckland` date:

- `arrivals?range=domestic`
- `arrivals?range=international`
- `departures?range=domestic`
- `departures?range=international`

Auth and headers:

- HTTP Basic auth with public mobile-app credentials embedded in the APK.
- Defaults can be overridden with `AKL_API_USERNAME` and `AKL_API_PASSWORD`.
- `Content-Type: application/vnd.api+json`
- `App-Version: android|8.2.2`

Response shape:

- top-level `data[]`
- each row has `type`, `id`, and `attributes`
- `attributes` includes `range`, `iataCode`, `origin`, `destination`, `codeshares`, `time`, `state`
- departures include `checkin.zone`, `checkin.status`, `boarding.gate`, `boarding.status`
- arrivals include `landing.baggageNumber`, `landing.status`

Normalized AKL FIDS fields include:

- `flight_id`
- `flight_numbers[]`, including codeshares
- `primary_flight`, `airline_code`
- `origin`, `origin_airport_code`, `destination`, `destination_airport_code`
- `scheduled`, `estimated`, `actual` formatted in `Pacific/Auckland`
- `scheduled_utc`, `estimated_utc`, `actual_utc`
- `gate`, `checkin_zone`, `checkin_status`, `boarding_status`
- `baggage_carousel`, `landing_status`
- `status`, `status_code`, `terminal`, `is_domestic`

### Auckland Airport via adsb.lol live ADS-B

Endpoint:

```text
GET https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radiusNm}
```

Current AKL parameters:

- `lat=-37.008`
- `lon=174.785`
- `radiusNm=30`

Operational notes:

- Radius is in nautical miles. The adsb.lol endpoint supports larger radii up to roughly 250 nm, but this skill keeps AKL at 30 nm to reduce payload size and stay focused on local airport activity.
- No username, password, cookie, token, or API key is required.
- The CLI sends `User-Agent: nz-airports-cli/1.0`.
- The ADS-B request timeout is 6 seconds.
- The aircraft list is capped before classification to avoid processing unexpectedly large responses.
- There are no retry loops; if adsb.lol is unavailable, malformed, or empty, AKL returns an empty board with a source note rather than a stack trace.
- This implementation is based on Adam Holt's working `cyclone.vaianu` Supabase function at `supabase/functions/airports-live/index.ts`.

Response shape:

- top-level object with `ac[]`
- each aircraft may include `hex`, `flight`, `r` (registration), `t` (aircraft type), `alt_baro` (number or `ground`), `gs` (ground speed in knots), `baro_rate` (vertical rate in ft/min), `lat`, `lon`, `dst` (distance from query point in nautical miles), and other ADS-B fields

Classification logic:

- `alt_baro == "ground"` -> `ground`
- `alt_baro < 6000` and `baro_rate < -200` -> `arrival`
- `alt_baro < 6000` and `baro_rate > 200` -> `departure`
- `alt_baro < 6000` with no strong climb/descent -> `arrival`, because low and level traffic near the field is likely on final approach
- `alt_baro >= 6000`, missing altitude, or otherwise unclassified high traffic -> `overhead`

The `arrivals --airport AKL --source adsb` and `departures --airport AKL --source adsb` commands return aircraft classified as `arrival` or `departure` respectively. Ground and overhead aircraft are counted in JSON metadata but are not returned by those board commands.

Normalized AKL fields include:

- `callsign` from `flight`, falling back to uppercase `hex`
- `hex`, `registration`, `aircraft_type`
- `classification`
- `altitude_ft`, `altitude_baro`
- `distance_nm`
- `ground_speed_kt`
- `vertical_rate_fpm`
- `lat`, `lon`
- `raw_adsb` with the returned ADS-B row for JSON consumers

AKL `--source adsb` is live aircraft-position data, not a scheduled FIDS board. It answers "which aircraft are physically near Auckland Airport now?" rather than "what has the airline published on the airport board?"

### Christchurch Airport

Base endpoint:

```text
GET https://www.christchurchairport.nz/api/flights?maxFlights=&flightDirection={Arrive|Depart}&flightType={Domestic|International}
```

The CLI calls all four combinations:

- `flightDirection=Arrive&flightType=Domestic`
- `flightDirection=Arrive&flightType=International`
- `flightDirection=Depart&flightType=Domestic`
- `flightDirection=Depart&flightType=International`

Response shape:

- top-level `lastUpdated`, `flightType`, `flightDirection`
- `flights[]` with `airlineCode`, `airlineName`, `flightNumbers[]`, `airports[]`, `scheduled`, `estimateActual`, `gate`, `status`, `statusColour`, `imageUrl`

Observed update wording on the public page says information is updated every ten minutes by airlines. The JSON response includes `lastUpdated`.

### Queenstown Airport

Endpoints:

```text
GET https://www.queenstownairport.co.nz/api/flights/arrivals
GET https://www.queenstownairport.co.nz/api/flights/departures
```

Response shape:

- array of flight rows
- each row includes `flightList[]`, `from`, `destination`, `schTime`, `schDate`, `estTime`, `estDate`, `status`, `orderByDate`, `isDomestic`, `flightType`

The endpoint returns multiple dates. The CLI filters to today's `Pacific/Auckland` date when rows exist for that date, otherwise it returns the source rows as-is.

### Wellington Airport

Page endpoint:

```text
GET https://www.wellingtonairport.co.nz/flights/?direction={A|D}
```

The current board is embedded in:

```html
<script type="application/json" data-flights>...</script>
```

Embedded JSON shape:

- top-level `is_arrivals`, `last_updated`, `day`, `flights[]`
- `flights[]` with `place`, `scheduled`, `estimated`, `carrier_name`, `carrier_code`, `zone`, `flight_number`, `gate`, `status_text`

The board can legitimately be empty for departures late in the local operating day.

## Normalized CLI schema

Each normalized AKL/CHC/ZQN/WLG scheduled-board flight includes:

- `airport`, `airport_name`, `direction`
- `flight_numbers[]`, `primary_flight`
- `airline_code`, `airline_name`
- `origin`, `destination`
- `scheduled`, `estimated`
- `gate`, `status`, `terminal`, `is_domestic`
- `source`, `source_url`

Some fields are source-dependent. Auckland exposes check-in zone, boarding gate, baggage carousel, and codeshares through the mobile app API. Queenstown does not expose gate or airline name in the JSON endpoint. Wellington exposes one flight number per row in the embedded board. Christchurch exposes codeshare flight numbers and airline branding image URLs, but the CLI does not emit image URLs in the normalized record.

AKL ADS-B rows use a different live-position schema. They include callsign, aircraft type, registration, altitude, distance from the airport query point, ground speed, vertical rate, location, classification, and `raw_adsb`. They do not include scheduled/estimated board times, gate, terminal, airline-published status text, origin, or destination.

## Stability and safety

- Treat CHC/ZQN/WLG results as live public-board snapshots, not historical data.
- Treat default AKL results as live public-board snapshots.
- Treat AKL `--source adsb` results as live ADS-B aircraft-position snapshots, not a scheduled airport board.
- Always prefer narrow commands and small limits for routine checks.
- Do not use this skill for booking, check-in, account, payment, passenger, baggage ownership, or mutation workflows.
- Endpoint shapes can change without notice because these are public website implementation details rather than official public APIs.
- Do not commit HAR captures, screenshots, cookies, raw browser profiles, or bulky JavaScript bundles when updating this skill.
