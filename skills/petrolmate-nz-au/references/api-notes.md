# PetrolMate API notes

This skill is an unofficial lightweight wrapper around the public PetrolMate API used by petrolmate.com.au.

## Source and auth

- Website: `https://petrolmate.com.au/`
- API base: `https://petrolmate.com.au/api/`
- Auth model: none — all endpoints are public and unauthenticated

No API key, account, or browser session is required.

## Endpoints used

### `GET /api/stations/nearby`

Find stations near a coordinate.

Parameters:
- `lat` (float) — latitude
- `lng` (float) — longitude
- `radius` (int, 100–50000) — search radius in meters
- `fuel_type` (str) — e.g. `ULP`, `DIESEL`, `PULP95`
- `limit` (int, max 100) — max results

Response fields per station:
- `name`, `brand`, `address`, `suburb`, `state`, `postcode`
- `latitude`, `longitude`
- `price` (cents), `fuel_code`, `fuel_name`
- `distance_meters`, `hours_old`, `source`
- `timestamp`, `confidence_score`, `members_only`

### `GET /api/geoip`

Approximate location from IP (Cloudflare). Returns `city`, `country`, `latitude`, `longitude`.

### `GET /api/geocode/search`

Geocode an address. Parameter: `q` (query string). Returns `display_name`, `lat`, `lon`.

## Data sources

- **AU:** State government FuelCheck data — NSW, QLD, VIC, SA, TAS
- **NZ:** Community-sourced Gaspy data

Not all fuel types available in all states:
- NSW: ULP, E10, LPG, E85 only
- VIC/QLD/NZ: all 9 fuel types (ULP, E10, PULP95, PULP98, PREMIUM, DIESEL, PDIESEL, LPG, E85)

## Fuel type codes

| Code | Label |
|------|-------|
| ULP | Unleaded 91 |
| E10 | E10 (Ethanol 10%) |
| PULP95 | Premium 95 |
| PULP98 | Premium 98 |
| PREMIUM | Premium (95+98) |
| DIESEL | Diesel |
| PDIESEL | Premium Diesel |
| LPG | LPG/Autogas |
| E85 | E85 (Ethanol 85%) |

API field `fuel_name` uses labels like "Unleaded Petrol", "Premium Unleaded 95", and "Diesel" — the CLI maps these to short codes.

## Relationship to other fuel skills

- **PetrolMate** aggregates official (AU FuelCheck) and crowd-sourced (NZ Gaspy) data into one API. AU data is typically more reliable than NZ data.
- **gaspy-nz** provides national crowd-sourced averages and cheapest-91 tables from the Gaspy public feed. It does not do location-based station search without login.
- **fuelclock-nz** provides official retailer-published prices, supply status, vessel tracking, and geopolitical watch data.
- **petrolspy-nz** provides location-based crowd-sourced station search via PetrolSpy's public API.

These four skills are complementary — use the one that matches the task.

## Stability and safety

- NZ Gaspy data is crowd-sourced and can be 1–2 days stale; always check `hours_old`
- AU FuelCheck data is official and typically updated within hours
- Prices are in cents; divide by 100 for dollars
- No third-party dependencies — Python stdlib only
- Rate limits unknown but not observed in normal use
