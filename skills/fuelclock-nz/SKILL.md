---
name: fuelclock-nz
description: "Query NZ fuel prices, supply, inbound tankers, MSO status, geopolitical shipping risk markets, and NZ fuel headlines from fuelclock.nz. No authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "food-and-fuel"
  thecolab.source_owner: "FuelClock"
  thecolab.source_type: "community"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://fuelclock.nz"
  thecolab.allowed_domains: "fuelclock.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# FuelClock NZ

## Goal

Query live New Zealand fuel price and supply data from fuelclock.nz through a CLI that is easy for agents to script and easy for humans to scan. Includes geopolitical shipping risk markets and recent NZ fuel headlines.

## Use this when

- A user asks about current NZ petrol, diesel, or premium fuel prices
- A user wants to know whether NZ fuel supply is tight or below MSO thresholds
- A user asks what tankers are en route to New Zealand
- A user wants a quick fuel situation summary focused on prices, supply, and vessels
- A user asks about geopolitical shipping risk markets relevant to NZ fuel supply
- A user wants recent NZ fuel headlines

## Do not use this for

- Fuel prices outside New Zealand
- Electricity, gas, or LPG pricing
- Vehicle fuel efficiency calculations
- Forecasting future fuel prices beyond the live observed data

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `summary` for a quick situational briefing across prices, supply, and vessels
3. Use `watch` for a quick briefing across geopolitical risk markets and recent headlines
4. Use default human output for direct answers
5. Use `--json` when another tool or agent needs machine-readable output

## CLI

Run with:

```bash
python3 skills/fuelclock-nz/scripts/cli.py <command> [flags]
```

### `summary [--json]`

Best default for general fuel questions. Combines prices, supply, and inbound vessels.

JSON shape:

- `prices`: fetched price snapshot plus filtered price rows
- `supply`: overall risk, countdown, lowest fuel, below-MSO list, and fuel rows
- `vessels`: fetched time, inbound vessel count, flagged count, and top vessels

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py summary
python3 skills/fuelclock-nz/scripts/cli.py summary --json
```

### `watch [--json]`

Quick briefing combining top geopolitical risk markets and recent NZ fuel headlines.

JSON shape:

- `risk.fetchedAt`, `risk.totalMarkets`, `risk.markets[]`
- `news.fetchedAt`, `news.totalArticles`, `news.articles[]`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py watch
python3 skills/fuelclock-nz/scripts/cli.py watch --json
```

### `prices [--fuel 91|95|98|diesel] [--json]`

Shows national average NZ pump prices from FuelClock's Gaspy-backed endpoint.

JSON shape:

- `fetchedAt`
- `source`
- `isFallback`
- `filters.fuel`
- `count`
- `prices[]` with `fuel`, `label`, `price`, `change7d`, `change28d`, `changePercent28d`, `direction7d`, `direction28d`, `min`, `max`, `stationCount`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py prices
python3 skills/fuelclock-nz/scripts/cli.py prices --fuel diesel
python3 skills/fuelclock-nz/scripts/cli.py prices --fuel 95 --json
```

### `supply [--fuel petrol|diesel|jet] [--below-mso] [--json]`

Shows NZ fuel supply state, including days remaining, MSO gap, and depletion timing.

JSON shape:

- `timestamp`
- `anchorDate`
- `mbieAsAtDate`
- `overallRisk`
- `countdownHours`
- `lowestFuel`
- `filters.fuel`
- `filters.belowMSO`
- `count`
- `fuels[]` with `fuel`, `label`, `currentDays`, `totalDays`, `onLandDays`, `onWaterDays`, `msoThreshold`, `gapToMSODays`, `belowMSO`, `calendarDaysToDepletion`, `dailyConsumptionML`, `currentStockML`, `remainingOnWaterDays`, `remainingOnWaterML`, `mbieInCountryDays`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py supply
python3 skills/fuelclock-nz/scripts/cli.py supply --below-mso
python3 skills/fuelclock-nz/scripts/cli.py supply --fuel diesel --json
```

### `vessels [--fuel petrol|diesel|jet] [--flagged-only] [--limit N] [--json]`

Shows inbound vessel data, sorted by ETA.

JSON shape:

- `fetchedAt`
- `source`
- `govOnWaterByFuel`
- `filters.fuel`
- `filters.flaggedOnly`
- `filters.limit`
- `totalMatching`
- `returnedCount`
- `vessels[]` with `name`, `fuel`, `status`, `eta`, `arrived`, `cargoML`, `cargoDays`, `origin`, `progressPct`, `flagRisk`, `flagReason`, `hormuzTransit`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py vessels
python3 skills/fuelclock-nz/scripts/cli.py vessels --flagged-only --limit 3
python3 skills/fuelclock-nz/scripts/cli.py vessels --fuel diesel --json
```

### `risk [--limit N] [--json]`

Shows tracked geopolitical markets relevant to fuel shipping (Polymarket-style), sorted by trading volume.

JSON shape:

- `fetchedAt`
- `sort`
- `filters.limit`
- `totalMarkets`
- `returnedCount`
- `markets[]` with `title`, `shortTitle`, `probability`, `volume`, `liquidity`, `lastUpdated`, `isFallback`, `subMarkets[]`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py risk
python3 skills/fuelclock-nz/scripts/cli.py risk --limit 5
python3 skills/fuelclock-nz/scripts/cli.py risk --limit 3 --json
```

### `news [--limit N] [--json]`

Shows recent NZ fuel headlines, newest first.

JSON shape:

- `fetchedAt`
- `filters.limit`
- `totalArticles`
- `returnedCount`
- `articles[]` with `title`, `source`, `date`, `url`

Examples:

```bash
python3 skills/fuelclock-nz/scripts/cli.py news
python3 skills/fuelclock-nz/scripts/cli.py news --limit 3
python3 skills/fuelclock-nz/scripts/cli.py news --limit 5 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`

## Notes

- No API key required
- Pure Python 3 standard library (`urllib`); no third-party dependencies
- Default output is human-readable and filtered for quick answers
- `--json` output is intended for chaining into other tools or agent steps
- FuelClock supply data and MBIE stock data are related but not identical, FuelClock applies its own live supply model on top of source data
- Geopolitical risk probabilities are market yes-prices from Polymarket-style data, not direct NZ fuel risk scores

## Source notes

Read `references/source-notes.md` for source ownership, access, and freshness boundaries.
