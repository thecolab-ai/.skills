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

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Use default human output for direct answers
3. Use `--json` when another tool or agent needs machine-readable output
4. Use `--location lat,lon` for custom coordinates not in the named list

## Environment

- **API Key env var:** `METOCEAN_API_KEY`
- Falls back to hardcoded key if env var is not set

## CLI

Run with:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts <command> [flags]
```

### `now [location] [--json] [--location lat,lon]`

Current conditions snapshot: temperature, wind, rain, humidity, pressure, cloud cover, visibility.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts now auckland
npx tsx skills/metservice-nz/scripts/cli.ts now wellington --json
npx tsx skills/metservice-nz/scripts/cli.ts now --location -37.0,175.5
```

### `forecast [location] [--json] [--location lat,lon]`

24-hour hourly forecast: time, temperature, rain, wind speed/direction, cloud cover.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts forecast auckland
npx tsx skills/metservice-nz/scripts/cli.ts forecast christchurch --json
```

### `daily [location] [--json] [--location lat,lon]`

7-day daily summary: high/low temperature, total rain, average wind, dominant wind direction.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts daily queenstown
npx tsx skills/metservice-nz/scripts/cli.ts daily wellington --json
```

### `marine [location] [--json] [--location lat,lon]`

Marine forecast: wave height, swell height, swell period, swell direction, sea temperature (where available).

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts marine auckland
npx tsx skills/metservice-nz/scripts/cli.ts marine clevedon --json
```

### `wind [location] [--json] [--location lat,lon]`

Detailed wind forecast: speed, gusts, direction — hourly for 24 hours.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts wind wellington
npx tsx skills/metservice-nz/scripts/cli.ts wind auckland
```

### `rain [location] [--json] [--location lat,lon]`

Precipitation forecast: hourly rain rate for 24 hours.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts rain christchurch
npx tsx skills/metservice-nz/scripts/cli.ts rain queenstown --json
```

### `warnings [--json]`

Scrape MetService severe weather warnings page for active alerts, watches, and advisories.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts warnings
npx tsx skills/metservice-nz/scripts/cli.ts warnings --json
```

### `cyclone [location] [--json] [--location lat,lon] [--hours n]`

Cyclone-specific data: pressure trend, extreme wind, storm surge indicators. Fetches 48h by default. Shows current snapshot, pressure trend, peak conditions, and hourly table.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts cyclone auckland
npx tsx skills/metservice-nz/scripts/cli.ts cyclone wellington --hours 72
npx tsx skills/metservice-nz/scripts/cli.ts cyclone clevedon --json
```

### `pressure [location] [--json] [--location lat,lon]`

Barometric pressure trend — the #1 cyclone indicator. Shows 12h history + 12h forecast with rate of change and severity classification.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts pressure auckland
npx tsx skills/metservice-nz/scripts/cli.ts pressure wellington --json
```

### `watch [location] [--location lat,lon] [--interval minutes] [--json]`

Continuous cyclone monitoring. Polls every 5 minutes (configurable) and alerts on significant changes. Shows pressure change between polls.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts watch auckland
npx tsx skills/metservice-nz/scripts/cli.ts watch wellington --interval 2
npx tsx skills/metservice-nz/scripts/cli.ts watch clevedon --json
```

### `locations [--json]`

List all named locations with coordinates.

Examples:

```bash
npx tsx skills/metservice-nz/scripts/cli.ts locations
npx tsx skills/metservice-nz/scripts/cli.ts locations --json
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

- CLI entrypoint: `scripts/cli.ts`
- Typed API client: `scripts/client.ts`
- Live smoke test: `scripts/smoke-test.ts`

## Notes

- API key required — set `METOCEAN_API_KEY` or falls back to embedded key
- Temperature returned in Kelvin, converted to Celsius in display
- Pressure returned in Pascals, converted to hPa in display
- Wind speed returned in m/s, converted to km/h in display
- Marine data may return null for inland or sheltered points
- Default output is human-readable; `--json` output is for chaining into other tools
- A location must always be specified — there is no default

## Cyclone Tracking Tools

### Data indicators to watch

| Indicator | Threshold | Meaning |
|---|---|---|
| Pressure | < 990 hPa | Tropical cyclone territory |
| Pressure drop | > 3 hPa/hr | Rapid intensification — DANGER |
| Sustained winds | > 63 km/h | Tropical cyclone |
| Sustained winds | > 118 km/h | Severe tropical cyclone |
| Storm surge | Wave height + tide level | Coastal flooding risk |

### CLI commands for cyclone monitoring

```bash
# Pressure + extreme wind + storm surge data
npx tsx skills/metservice-nz/scripts/cli.ts cyclone auckland

# Continuous polling — alerts on changes
npx tsx skills/metservice-nz/scripts/cli.ts watch wellington

# Active MetService alerts
npx tsx skills/metservice-nz/scripts/cli.ts warnings

# Wave height / surge data
npx tsx skills/metservice-nz/scripts/cli.ts marine auckland

# Pressure trend (12h history + 12h forecast)
npx tsx skills/metservice-nz/scripts/cli.ts pressure christchurch
```

### MetOcean variables for cyclone tracking

- `air.pressure.at-sea-level` — pressure drop is the #1 cyclone indicator
- `wind.speed.at-10m` — sustained winds
- `wind.speed.gust.at-10m` — gusts
- `wind.direction.at-10m` — wind direction shifts
- `wave.height` — storm surge / swell
- `wave.height.primary-swell` — incoming ocean swell
- `wave.period.peak` — long period = distant storm energy
- `precipitation.rate` — rainfall intensity

### Official NZ sources

- MetService warnings: https://www.metservice.com/warnings/home
- MetService severe weather outlook: https://www.metservice.com/warnings/severe-weather-outlook
- MetService tropical cyclone tracker: https://www.metservice.com/marine-surf/tropical-cyclones
- NIWA: https://www.niwa.co.nz/
- Civil Defence / NEMA: https://www.civildefence.govt.nz/

### Regional / Pacific sources

- RSMC Nadi (Regional Specialised Meteorological Centre for Pacific tropical cyclones): https://www.met.gov.fj/
- Australia BoM tropical cyclone tracker: http://www.bom.gov.au/cyclone/
- Joint Typhoon Warning Center (JTWC): https://www.metoc.navy.mil/jtwc/jtwc.html

### Best visual trackers

- Windy.com — best visual with pressure/wind overlays: https://www.windy.com/?-36.9,175.1,7
- Zoom.earth — real satellite imagery: https://zoom.earth/
- Cyclocane: https://www.cyclocane.com/
- GDACS (Global Disaster Alert): https://www.gdacs.org/
