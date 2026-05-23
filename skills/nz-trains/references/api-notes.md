# NZ Trains API notes

This skill is a lightweight read-only wrapper around Metlink Open Data GTFS and GTFS-RT endpoints for Wellington region train services.

## Source and auth

- Base URL: `https://api.opendata.metlink.org.nz/v1`
- Required header: `x-api-key: $METLINK_API_KEY`
- Auth model for this skill: API key from environment variable only

Do not hardcode API keys, commit `.env` files, store cookies, or write data back to Metlink.

## Endpoint families used

- `GET /gtfs/routes` for static route metadata; the CLI filters `route_type=2`
- `GET /gtfs/stops` for station names, parent station IDs, zones, and coordinates
- `GET /gtfs-rt/tripupdates` for current train delays and cancellations
- `GET /gtfs-rt/vehiclepositions` for live train positions
- `GET /gtfs-rt/servicealerts` for active service alerts
- `GET /stop-predictions?stop_id={stop_id}` for station arrivals

## Route scope

The CLI includes only the five Wellington train route codes from `route_type=2`:

- `JVL` - Johnsonville Line, route ID `6`
- `KPL` - Kapiti Line, route ID `2`
- `HVL` - Hutt Valley Line, route ID `5`
- `MEL` - Melling Line, route ID `3`
- `WRL` - Wairarapa Line, route ID `4`

Bus, school bus, ferry, cable car, and non-Metlink KiwiRail long-distance services are out of scope.

## Schema notes

- Static routes return an array with `route_id`, `route_short_name`, `route_long_name`, `route_desc`, `route_type`, and color fields.
- Static stops return an array with `stop_id`, `stop_code`, `stop_name`, `zone_id`, `stop_lat`, `stop_lon`, `location_type`, and `parent_station`.
- Parent stations such as `WELL`, `PETO`, and `WATE` group platform stop IDs such as `WELL1` or `PETO2`.
- Line station membership is scoped to known Wellington train stop IDs and enriched from `/gtfs/stops` for current names and coordinates.
- Stop predictions return `departures[]`; train departures are identified by `service_id` in `JVL`, `KPL`, `HVL`, `MEL`, or `WRL`.
- GTFS-RT trip updates and vehicle positions are returned as JSON with `header` and `entity[]`.
- Trip update delays are numeric seconds in GTFS-RT, while stop predictions use ISO-8601 durations such as `PT3M20S`.
- Service alerts use translated text fields under `header_text.translation[]` and `description_text.translation[]`.

## Rate limits and stability

- Metlink may rate-limit high-volume clients; keep queries narrow and prefer single-line commands when possible.
- The CLI caches static endpoint responses inside one process invocation only.
- Treat live data as a snapshot. Delay, vehicle, and alert state can change between calls.
- Endpoint shapes can change; verify with a small live command before relying on bulk automation.
- Handle `401`, `403`, and `429` as operational errors, not as reasons to add fallback credentials.
