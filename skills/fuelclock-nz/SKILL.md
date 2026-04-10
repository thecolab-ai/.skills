---
name: fuelclock-nz
description: Query New Zealand fuel price and supply data from fuelclock.nz. Use when the task involves NZ petrol or diesel prices, fuel supply security, days of supply remaining, MSO status, incoming fuel tankers, geopolitical fuel-shipping risk, or recent NZ fuel headlines. No authentication required.
---

# FuelClock NZ

## Goal

Query live New Zealand fuel price and supply data from fuelclock.nz through a CLI that is easy for agents to script and easy for humans to scan.

## Use this when

- A user asks about current NZ petrol, diesel, or premium fuel prices
- A user wants to know whether NZ fuel supply is tight or below MSO thresholds
- A user asks what tankers are en route to New Zealand
- A user asks about geopolitical shipping risk relevant to NZ fuel supply
- A user wants recent NZ fuel headlines or a quick fuel situation summary

## Do not use this for

- Fuel prices outside New Zealand
- Electricity, gas, or LPG pricing
- Vehicle fuel efficiency calculations
- Forecasting future fuel prices beyond the live observed data

## Preferred workflow

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Use default human output for direct answers
3. Use `--json` when another tool or agent needs machine-readable output
4. Fall back to importing `scripts/client.ts` only when you need the raw typed fetch functions

## CLI

Run with:

```bash
npx tsx skills/fuelclock-nz/scripts/cli.ts <command> [flags]
```

### `summary [--json]`

Best default for general questions. Combines prices, supply, inbound vessels, top tracked markets, and recent headlines.

JSON shape:
- `prices`: fetched price snapshot plus filtered price rows
- `supply`: overall risk, countdown, lowest fuel, below-MSO list, and fuel rows
- `vessels`: inbound vessel count, flagged count, and top vessels
- `risk`: fetched time, total market count, and top markets
- `news`: fetched time, total article count, and latest articles

Examples:

```bash
npx tsx skills/fuelclock-nz/scripts/cli.ts summary
npx tsx skills/fuelclock-nz/scripts/cli.ts summary --json
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
npx tsx skills/fuelclock-nz/scripts/cli.ts prices
npx tsx skills/fuelclock-nz/scripts/cli.ts prices --fuel diesel
npx tsx skills/fuelclock-nz/scripts/cli.ts prices --fuel 95 --json
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
npx tsx skills/fuelclock-nz/scripts/cli.ts supply
npx tsx skills/fuelclock-nz/scripts/cli.ts supply --below-mso
npx tsx skills/fuelclock-nz/scripts/cli.ts supply --fuel diesel --json
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
npx tsx skills/fuelclock-nz/scripts/cli.ts vessels
npx tsx skills/fuelclock-nz/scripts/cli.ts vessels --flagged-only --limit 3
npx tsx skills/fuelclock-nz/scripts/cli.ts vessels --fuel diesel --json
```

### `risk [--limit N] [--json]`

Shows tracked geopolitical markets relevant to fuel shipping. Output is sorted by market volume. The `probability` field is the market yes-price, not a direct NZ fuel risk score.

JSON shape:
- `fetchedAt`
- `sort`
- `filters.limit`
- `totalMarkets`
- `returnedCount`
- `markets[]` with `title`, `shortTitle`, `probability`, `volume`, `liquidity`, `lastUpdated`, `isFallback`, `subMarkets[]`

Examples:

```bash
npx tsx skills/fuelclock-nz/scripts/cli.ts risk
npx tsx skills/fuelclock-nz/scripts/cli.ts risk --limit 5
npx tsx skills/fuelclock-nz/scripts/cli.ts risk --limit 3 --json
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
npx tsx skills/fuelclock-nz/scripts/cli.ts news
npx tsx skills/fuelclock-nz/scripts/cli.ts news --limit 3
npx tsx skills/fuelclock-nz/scripts/cli.ts news --limit 5 --json
```

## Resources

- CLI entrypoint: `scripts/cli.ts`
- Typed fetch client: `scripts/client.ts`
- Live smoke test: `scripts/smoke-test.ts`

## Notes

- No API key required
- Uses the built-in `fetch` available in modern Node runtimes
- Default output is human-readable and filtered for quick answers
- `--json` output is intended for chaining into other tools or agent steps
- FuelClock supply data and MBIE stock data are related but not identical, FuelClock applies its own live supply model on top of source data
