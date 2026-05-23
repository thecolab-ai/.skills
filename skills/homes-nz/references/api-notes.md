# Homes NZ API notes

This skill is an unofficial lightweight wrapper around public read-only homes.co.nz endpoints used by the modern web app.

## Source and auth

- Website: `https://homes.co.nz`
- Public gateway: `https://gateway.homes.co.nz`
- Public detail gateway: `https://api-gateway.homes.co.nz`
- Auth model for supported commands: none

No username, password, account cookie, private token, browser session, or JavaScript rendering is required for the implemented read-only operations.

## Endpoint families used

- `GET /address/search?Address={query}` for address, suburb, street, and city typeahead results
- `GET /properties?property_ids={comma_ids}` for property cards, HomesEstimate display values, property attributes, and map URLs
- `GET https://api-gateway.homes.co.nz/details?property_id={id}` for richer public property/council detail
- `GET /properties/sales?property_ids={comma_ids}` for public sale history attached to property ids
- `GET /suburb/estimate_history?id={suburb_id}` for suburb HomesEstimate trend data
- `GET /median_suburb_rent_estimate?id={suburb_id}` for suburb median rental estimate
- `GET /map/items?...` for nearby public property cards around a bounded map viewport
- `GET /homes_estimates/latest_date` for the latest HomesEstimate revision date

The CLI sends browser-like `Accept`, `Referer`, `Origin`, and `User-Agent` headers, but it does not store or send credentials.

## Discovery notes

- The Angular bundle exposes `GATEWAY:{SCHEMA:"https",HOST:"gateway.homes.co.nz"}` and `API_GATEWAY:"https://api-gateway.homes.co.nz"`.
- Address search returns mixed result types. `Type: 4` is an address result, `Type: 3` is a street result, `Type: 2` is a suburb result, and `Type: 1` is a city result.
- Some address results do not include `PropertyID`. The CLI reports those suggestions but cannot fetch property detail until a property id is available.
- **API drift (observed ~mid-2025):** `GET /address/search` began returning `PropertyID: null` for many `Type: 4` results when the query includes a city or suburb qualifier (e.g. "Auckland", "Auckland Central"). Additionally, queries that include both a suburb and city suffix now frequently return only `Type: 1` (city-level) fallback rows, dropping all address-level results entirely. The CLI now applies a two-step recovery: (1) if all returned rows are `Type: 1`, it progressively strips trailing words from the query and retries until address-level rows are returned; (2) for `Type: 4` rows that still have `null PropertyID`, it calls `GET /map/items` with a tight bounding box around the result's lat/long and matches by street number to resolve a `PropertyID`.
- A parallel `GET /typeahead/search` endpoint exists and returns the same response shape; the CLI continues to use `/address/search` as it is equally reliable.
- `GET /property/resolve` was present in the bundle but returned `400` for direct no-login reproduction, so it is not exposed.
- `GET /map/radius/addresses` was present in the bundle but returned `could not parse request body` for direct no-login reproduction, so `nearby` uses `GET /map/items` with a bounding box instead.
- `GET /suburb/estimate_history/{id}` was present in the bundle and returned JSON, but direct live checks produced inconsistent values for known suburbs. The CLI uses the query form, which matched the expected suburb market levels in live verification.
- No no-login suburb sales-volume aggregate was verified. The `suburb` command reports the available suburb property count from typeahead, HomesEstimate trend, and median rent estimate.
- **API drift (observed ~mid-2025, suburb resolution):** `GET /address/search` returns only `Type: 1` (city-level) rows when the query combines a suburb name with a city name (e.g. "Ponsonby Auckland", "Kelburn Wellington"). This broke `resolve_suburb`, which could not find a `SuburbID` in results. The fix applies the same trailing-word-stripping fallback already used by the `address` command: if the full query yields no result with a `SuburbID`, progressively strip trailing words and retry until a `Type: 2` suburb row is returned or a single word remains. `GET /median_suburb_rent_estimate?id={suburb_id}` was also reported as intermittently returning HTTP 500 around the same period but has since recovered; it remains the live rent-estimate endpoint and is verified working as of May 2026.

## Stability and safety

- Treat HomesEstimate/HEV and RentEstimate values as automated estimates, not formal valuations.
- Treat sales histories as public snapshots; records can be corrected, removed, suppressed, or delayed.
- Endpoint shapes and filter names can change without notice because this is not a formally supported public skill API.
- Avoid high-volume scraping and dataset redistribution; use narrow queries and small limits.
- Do not use this skill for claim-home updates, user accounts, favourites, saved searches, agent enquiries, lead forms, property edits, or any POST/PUT/DELETE mutation.
- Do not commit cookies, account data, raw authenticated captures, HAR files, screenshots, JS bundles, or HTML captures.
