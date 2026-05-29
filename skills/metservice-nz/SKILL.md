---
name: metservice-nz
description: Query New Zealand weather data from the MetOcean API (MetService's data arm). Use when the task involves NZ weather forecasts, current conditions, marine/wave data, wind, rain, or atmospheric conditions for New Zealand locations. Requires METOCEAN_API_KEY.
---

# MetService NZ (MetOcean API)

## Goal

Query point forecasts from the MetOcean API for New Zealand locations — weather, marine, and atmospheric data through a CLI that is easy for agents to script and easy for humans to scan.

## Use this when

- A user asks about current or forecast weather in New Zealand
- A user wants temperature, rain, wind, or cloud data for an NZ location
- A user asks about marine conditions — wave height, swell, sea temperature
- A user wants a multi-day weather outlook for NZ
- A user asks about wind conditions for a specific NZ location

## Do not use this for

- Weather outside New Zealand (API coverage is NZ/Pacific focused)
- Historical weather data (API provides forecasts, not archives)
- Long-range forecasts beyond ~7 days

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use default human output for direct answers
3. Use `--json` when another tool or agent needs machine-readable output
4. Use `--location lat,lon` for custom coordinates not in the named list

## Setup

Requires a MetOcean API key (free tier available).

1. Sign up at https://forecast-v2.metoceanapi.com
2. Add to your `.env`:
   ```
   METOCEAN_API_KEY=your_key_here
   ```
3. The skill reads `process.env.METOCEAN_API_KEY` — no fallback, key is required.

## CLI

Run with:

```bash
python3 skills/metservice-nz/scripts/cli.py <command> [flags]
```

### `now [location] [--json] [--location lat,lon]`

Current conditions snapshot: temperature, wind, rain, humidity, pressure, cloud cover, visibility.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py now auckland
python3 skills/metservice-nz/scripts/cli.py now wellington --json
python3 skills/metservice-nz/scripts/cli.py now --location -37.0,175.5
```

### `forecast [location] [--json] [--location lat,lon]`

24-hour hourly forecast: time, temperature, rain, wind speed/direction, cloud cover.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py forecast auckland
python3 skills/metservice-nz/scripts/cli.py forecast christchurch --json
```

### `daily [location] [--json] [--location lat,lon]`

7-day daily summary: high/low temperature, total rain, average wind, dominant wind direction.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py daily queenstown
python3 skills/metservice-nz/scripts/cli.py daily wellington --json
```

### `marine [location] [--json] [--location lat,lon]`

Marine forecast: wave height, swell height, swell period, swell direction, sea temperature (where available).

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py marine auckland
python3 skills/metservice-nz/scripts/cli.py marine clevedon --json
```

### `wind [location] [--json] [--location lat,lon]`

Detailed wind forecast: speed, gusts, direction — hourly for 24 hours.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py wind wellington
python3 skills/metservice-nz/scripts/cli.py wind auckland
```

### `rain [location] [--json] [--location lat,lon]`

Precipitation forecast: hourly rain rate for 24 hours.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py rain christchurch
python3 skills/metservice-nz/scripts/cli.py rain queenstown --json
```

### `warnings [--json]`

Scrape MetService severe weather warnings page for active alerts, watches, and advisories.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py warnings
python3 skills/metservice-nz/scripts/cli.py warnings --json
```

### `cyclone [location] [--json] [--location lat,lon] [--hours n]`

Cyclone-specific data: pressure trend, extreme wind, storm surge indicators. Fetches 48h by default. Shows current snapshot, pressure trend, peak conditions, and hourly table.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py cyclone auckland
python3 skills/metservice-nz/scripts/cli.py cyclone wellington --hours 72
python3 skills/metservice-nz/scripts/cli.py cyclone clevedon --json
```

### `pressure [location] [--json] [--location lat,lon]`

Barometric pressure trend — the #1 cyclone indicator. Shows 12h history + 12h forecast with rate of change and severity classification.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py pressure auckland
python3 skills/metservice-nz/scripts/cli.py pressure wellington --json
```

### `watch [location] [--location lat,lon] [--interval minutes] [--json]`

Continuous cyclone monitoring. Polls every 5 minutes (configurable) and alerts on significant changes. Shows pressure change between polls.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py watch auckland
python3 skills/metservice-nz/scripts/cli.py watch wellington --interval 2
python3 skills/metservice-nz/scripts/cli.py watch clevedon --json
```

### `locations [--json]`

List all named locations with coordinates.

Examples:

```bash
python3 skills/metservice-nz/scripts/cli.py locations
python3 skills/metservice-nz/scripts/cli.py locations --json
```

## Named Locations

| Name | Lat | Lon |
|---|---|---|
| clevedon | -36.9697 | 175.0752 |
| auckland | -36.8485 | 174.7633 |
| wellington | -41.2865 | 174.7762 |
| christchurch | -43.5321 | 172.6362 |
| queenstown | -45.0312 | 168.6626 |

## Available API Variables

### Atmospheric
- `air.temperature.at-2m` (K)
- `air.humidity.at-2m` (%)
- `air.pressure.at-sea-level` (Pa)
- `air.visibility` (m)
- `cloud.cover` (fraction 0-1)
- `precipitation.rate` (mm/hr)
- `radiation.flux.downward.shortwave` (W/m²)

### Wind
- `wind.speed.at-10m` (m/s)
- `wind.direction.at-10m` (degrees)
- `wind.speed.gust.at-10m` (m/s)

### Marine/Wave
- `wave.height` (m)
- `wave.height.primary-swell` (m)
- `wave.height.wind-sea` (m)
- `wave.period.peak` (s)
- `wave.period.primary-swell.peak` (s)
- `wave.direction.peak` (degrees)
- `wave.direction.primary-swell.mean` (degrees)
- `sea.temperature.at-surface` (K)

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`

## Notes

- API key required — set `METOCEAN_API_KEY` in your `.env`
- Temperature returned in Kelvin, converted to Celsius in display
- Pressure returned in Pascals, converted to hPa in display
- Wind speed returned in m/s, converted to km/h in display
- Marine data may return null for inland or sheltered points
- Default output is human-readable; `--json` output is for chaining into other tools
- A location must always be specified — there is no default

## Cyclone Tracking Tools

Data indicators, CLI commands, MetOcean variables, and official NZ and Pacific sources:
[references/cyclone-tracking.md](references/cyclone-tracking.md)
