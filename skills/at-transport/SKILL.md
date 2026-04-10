---
name: at-transport
description: Query live Auckland Transport (AT) public transport data — stops, departures, service alerts, vehicle positions, routes, and network status. Use when the task involves Auckland buses, trains, ferries, or real-time transit information.
---

# Auckland Transport

## Goal

Query live Auckland public transport data from the AT API through a CLI that is easy for agents to script and easy for humans to scan. Covers real-time departures, service alerts, stop search, nearby stops, vehicle tracking, and network status.

## Use this when

- A user asks about Auckland public transport — buses, trains, ferries
- A user wants real-time departure information from a specific stop
- A user asks about service disruptions or alerts in Auckland
- A user wants to find nearby stops or search for a stop by name
- A user asks about live vehicle positions on the Auckland network
- A user wants a quick overview of Auckland Transport network status

## Do not use this for

- Transport outside Auckland / New Zealand
- Route planning or journey directions (use AT's journey planner)
- Historical schedule data or timetable lookups
- Fares or ticketing information
- Traffic or road conditions

## Preferred workflow

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Use default human output for direct answers
3. Use `--json` when another tool or agent needs machine-readable output
4. Fall back to importing `scripts/client.ts` only when you need the raw typed fetch functions

## CLI

Run with:

```bash
npx tsx skills/at-transport/scripts/cli.ts <command> [flags]
```

### `alerts [--limit N] [--json]`

Active service alerts and disruptions across the Auckland network.

JSON shape:
- `timestamp`
- `total_active`
- `returned`
- `alerts[]` with `id`, `severity_level`, `cause`, `effect`, `header_text`, `description_text`, `active_period`, `informed_entity`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts alerts
npx tsx skills/at-transport/scripts/cli.ts alerts --limit 5
npx tsx skills/at-transport/scripts/cli.ts alerts --json
```

### `departures <stop_id> [--limit N] [--json]`

Real-time departures from a stop. Uses stop code (e.g. `11814`) or full stop ID. Shows route, expected time, and delay. For parent stations, includes all child platform stops.

JSON shape:
- `stop` with stop details
- `total_departures`
- `returned`
- `departures[]` with `route_id`, `route_short_name`, `route_type`, `trip_id`, `stop_id`, `stop_name`, `direction_id`, `scheduled_time`, `expected_time`, `delay_seconds`, `vehicle_id`, `vehicle_label`

Key stop codes:
- `11814` — Britomart (bus terminal)
- `11815` — Customs St/Britomart
- `11895` — Britomart Queens Arcade
- `31986` — Britomart Lower Albert

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts departures 11814
npx tsx skills/at-transport/scripts/cli.ts departures 7155 --limit 5
npx tsx skills/at-transport/scripts/cli.ts departures 11814 --json
```

### `stops <query> [--limit N] [--json]`

Search stops by name, code, or ID. Returns matching stops with location and type info.

JSON shape:
- `query`
- `total_matches`
- `returned`
- `stops[]` with `stop_id`, `stop_code`, `stop_name`, `stop_lat`, `stop_lon`, `location_type`, `parent_station`, `platform_code`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts stops Britomart
npx tsx skills/at-transport/scripts/cli.ts stops Newmarket
npx tsx skills/at-transport/scripts/cli.ts stops 7155 --json
```

### `nearby <lat,lon> [--radius N] [--limit N] [--json]`

Find stops near a geographic location. Radius in meters, defaults to 500m.

JSON shape:
- `location` with `lat`, `lon`
- `radius_m`
- `total_nearby`
- `returned`
- `stops[]` with stop details plus `distance_m`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768
npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768 --radius 1000
npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768 --json
```

### `route <route_id> [--json]`

Show details for a specific route. Use full route ID (e.g. `STH-201`).

JSON shape:
- `route_id`, `route_short_name`, `route_long_name`, `route_type`, `agency_id`, `route_color`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts route STH-201
npx tsx skills/at-transport/scripts/cli.ts route 70-221 --json
```

### `vehicles [--route <route_id>] [--limit N] [--json]`

Live vehicle positions across the network, optionally filtered by route.

JSON shape:
- `timestamp`
- `filter_route`
- `total_vehicles`
- `returned`
- `vehicles[]` with `vehicle_id`, `label`, `lat`, `lon`, `speed`, `bearing`, `route_id`, `trip_id`, `last_update`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts vehicles
npx tsx skills/at-transport/scripts/cli.ts vehicles --route STH-201
npx tsx skills/at-transport/scripts/cli.ts vehicles --limit 10 --json
```

### `status [--json]`

Overall network status summary — active trips, vehicles, on-time %, delays, and alert counts.

JSON shape:
- `timestamp`
- `alerts_count`
- `alerts_by_severity`
- `active_trips`
- `active_vehicles`
- `delayed_trips`
- `avg_delay_seconds`
- `on_time_percentage`

Examples:

```bash
npx tsx skills/at-transport/scripts/cli.ts status
npx tsx skills/at-transport/scripts/cli.ts status --json
```

## Resources

- CLI entrypoint: `scripts/cli.ts`
- Typed fetch client: `scripts/client.ts`
- Live smoke test: `scripts/smoke-test.ts`

## Notes

- API key stored in env var `AT_API_KEY`, falls back to bundled key
- Uses GTFS v3 for static data (stops, routes) and GTFS-RT legacy feed for real-time data (alerts, trip updates, vehicle positions)
- Departures show only trips with active real-time tracking — vehicles currently approaching or at the stop
- Parent stations (location_type=1) automatically include departures from child platform stops
- Default output is human-readable; `--json` is intended for chaining into other tools or agent steps
- Route types: 0=Tram, 2=Train, 3=Bus, 4=Ferry
