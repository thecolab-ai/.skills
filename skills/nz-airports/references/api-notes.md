# NZ Airports API notes

This skill is an unofficial lightweight wrapper around public airport flight-board surfaces. It is read-only and does not support booking, check-in, PNR lookup, account access, or passenger/baggage ownership lookup.

## Source and auth

No username, password, API key, private token, cookie, or browser session is required for the implemented commands.

Implemented airports:

- Christchurch (CHC): `https://www.christchurchairport.nz`
- Queenstown (ZQN): `https://www.queenstownairport.co.nz`
- Wellington (WLG): `https://www.wellingtonairport.co.nz`

Investigated but not implemented:

- Auckland (AKL): `https://www.prod.aucklandairport.co.nz/flights` and `https://corporate.aucklandairport.co.nz/content/aial-traveller/nz/en/flights.html` returned Cloudflare challenge/block pages from direct CLI fetches. CloakBrowser CDP navigation also returned a Cloudflare 403 block in this environment, so no stable no-login CLI endpoint was shipped.

## Endpoint families used

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

Each normalized flight includes:

- `airport`, `airport_name`, `direction`
- `flight_numbers[]`, `primary_flight`
- `airline_code`, `airline_name`
- `origin`, `destination`
- `scheduled`, `estimated`
- `gate`, `status`, `terminal`, `is_domestic`
- `source`, `source_url`

Some fields are source-dependent. Queenstown does not expose gate or airline name in the JSON endpoint. Wellington exposes one flight number per row in the embedded board. Christchurch exposes codeshare flight numbers and airline branding image URLs, but the CLI does not emit image URLs in the normalized record.

## Stability and safety

- Treat results as live public-board snapshots, not historical data.
- Always prefer narrow commands and small limits for routine checks.
- Do not use this skill for booking, check-in, account, payment, passenger, baggage ownership, or mutation workflows.
- Endpoint shapes can change without notice because these are public website implementation details rather than official public APIs.
- Do not commit HAR captures, screenshots, cookies, raw browser profiles, or bulky JavaScript bundles when updating this skill.
