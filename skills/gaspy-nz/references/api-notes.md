# Gaspy NZ API notes

This skill is an unofficial lightweight wrapper around the public Gaspy NZ statistics feed used by `gaspy.nz`.

## Source and auth

- Website: `https://www.gaspy.nz/`
- Public stats page: `https://www.gaspy.nz/stats.html`
- Public stats script: `https://www.gaspy.nz/assets/stats-page.min.js`
- Public Firebase feed: `https://gaspy-datamine-stats.firebaseio.com/.json`
- Auth model for this skill: none for the implemented read-only public stats requests

No username, password, account cookie, private token, or browser session is required for the implemented read-only operations.

## Endpoint used

- `GET https://gaspy-datamine-stats.firebaseio.com/.json` for public national observed prices, top-five cheapest 91, station count, brand count, Gas Spy count, and recent confirmation count

The CLI sends lightweight browser-ish headers (`accept`, `referer`, `user-agent`) but does not store credentials or cookies.

## Public feed shape

- `datamine.Averages` contains labelled national average prices and 28 day changes for `91`, `95`, `98`, `100`, `Diesel`, and `LPG`
- `datamine.Top91` contains the public top-five cheapest stations for 91 with station name, region, and price
- `datamine.StationCount`, `datamine.BrandCount`, and `datamine.PriceConfirmationsInLast7Days` provide public activity counts
- `datamine.Updated` is the website-facing database update text
- `gaspy.national` contains observed national stats keyed by numeric fuel type id
- `gaspy.timestamp` and `gaspy.usercount` provide a machine timestamp and public Gas Spy count

Fuel ids observed in the public feed:

- `1` - 91
- `2` - diesel
- `3` - 95
- `5` - 98
- `17` - LPG
- `18` - 100
- `21` - unlabelled in the public web feed; the CLI reports this as `type-21`

## Mobile API discovery notes

The Android APK exposes a custom API rooted at `https://gaspy.nz/api/v1/`, including read-looking endpoints such as:

- `/api/v1/Public/init`
- `/api/v1/FuelPrice/searchFuelPricesV2`
- `/api/v1/FuelPrice/searchRemoteFuelPricesV2`
- `/api/v1/FuelPrice/fuelPriceStationDetails`
- `/api/v1/FuelPrice/stationFuelPrices`
- `/api/v1/GeoSearch/autocomplete`
- `/api/v1/GeoSearch/select`

The station search/detail endpoints tested without login returned `Login Required`. The main app Firebase database at `https://gaspy-3baaf.firebaseio.com/.json` returned `Permission denied`. Those surfaces are not used because this skill is read-only, no-login, and tested only against public web-equivalent data.

## Relationship to `fuelclock-nz`

Gaspy is a crowd-sourced/user-reported fuel price source. Users may report pump prices incorrectly, prices can become stale, and some stations may be missing or infrequently confirmed. Gaspy can still be useful because user-reported local prices often surface cheaper options quickly.

Use `fuelclock-nz` instead when the user asks for official retailer-published prices, FuelClock supply status, vessels, geopolitical watch data, or recent NZ fuel headlines. The two skills are complementary, not duplicates.

## Stability and safety

- Treat prices as live crowd-sourced snapshots, not historical facts.
- Do not use this skill to update, confirm, report, or correct prices.
- Do not use authenticated or login-gated Gaspy account/mobile endpoints.
- Avoid high-volume polling; use narrow live queries.
- Do not commit HARs, APKs, extracted APK contents, JS bundles, or HTML dumps.
