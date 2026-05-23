# NZ Buses API notes

This skill is a lightweight read-only wrapper around Metlink Open Data for Wellington-region buses. Auckland is intentionally out of scope because `at-transport` already covers Auckland Transport buses, trains, ferries, alerts, routes, stops, and vehicle positions.

## Source and auth

- Developer portal: `https://opendata.metlink.org.nz/`
- API base: `https://api.opendata.metlink.org.nz/v1/`
- Auth model: free Metlink Open Data API key sent as `x-api-key`
- CLI env var: `METLINK_API_KEY`

To obtain a key:

1. Open `https://opendata.metlink.org.nz/`
2. Sign up or sign in through the Metlink Open Data Developer Portal
3. Open the dashboard/API key page
4. Copy the key and export it as `METLINK_API_KEY`

If `METLINK_API_KEY` is missing, the CLI exits before making a request with a message telling the user how to set it. Do not commit API keys, screenshots containing keys, browser captures, or portal cookies.

## Endpoint families used

- `GET /v1/gtfs/stops` for static Metlink stops
- `GET /v1/gtfs/stops?trip_id={trip_id}` for stops on a known trip, if needed later
- `GET /v1/gtfs/stops?route_id={route_id}` for stops on a known route
- `GET /v1/gtfs/routes` for static routes
- `GET /v1/gtfs/routes?stop_id={stop_id}` for routes serving a stop
- `GET /v1/stop-predictions?stop_id={stop_id}` for live stop arrivals/departures
- `GET /v1/gtfs-rt/servicealerts` for active service alerts
- `GET /v1/gtfs-rt/vehiclepositions` for live vehicle positions
- `GET /v1/gtfs-rt/tripupdates` is documented but not used by the v1 CLI

The API returns JSON for these endpoints when called with `Accept: application/json` and a valid key.

## Bus filtering

Metlink exposes multiple modes through the same route and realtime endpoints. The CLI includes only bus services:

- Standard buses: `route_type=3`
- Metlink school buses: `route_type=712`

The CLI excludes rail `route_type=2`, ferry `route_type=4`, cable car `route_type=5`, and every other non-bus type. Static GTFS stops do not carry route type directly, so `stops`, `stop`, `arrivals`, and stop-only alerts check `GET /v1/gtfs/routes?stop_id={stop_id}` and keep only stops served by bus routes.

## Free-tier rate limits and stability

The Metlink Open Data portal issues free API keys, but the public API responses observed during live verification did not include `X-RateLimit-*` or similar quota headers. Treat free-tier limits as key-specific portal settings: check the signed-in developer portal for the exact quota attached to the key, avoid broad polling, prefer narrow commands, use small `--limit` values, and cache repeated route/stop lookups inside a workflow where practical.

Observed unauthenticated behavior:

- No `x-api-key`: HTTP 403 with `MissingAuthenticationTokenException`
- Invalid `x-api-key`: HTTP 403 with `{"message":"Forbidden"}`
- Observed successful route responses returned no rate-limit headers; the CLI therefore does not try to infer remaining quota

Endpoint names are stable enough for a small CLI, but the portal and OpenAPI catalog are behind sign-in. Verify representative commands live before relying on this skill in a workflow.

## Follow-ups

- Canterbury Metro / Environment Canterbury: add a second source after verifying GTFS static and GTFS-Realtime endpoints for Christchurch and Timaru. Keep it read-only and stdlib-only.
- ORC Bus: investigate Dunedin and Queenstown static and live feed availability.
- BayBus / NZTA / regional feeds: ignore unless a clean public endpoint is confirmed.
