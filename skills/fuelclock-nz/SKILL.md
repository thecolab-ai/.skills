---
name: fuelclock-nz
description: Query New Zealand fuel price and supply data from fuelclock.nz. Use when the task involves NZ petrol or diesel prices, fuel supply security, days of supply remaining, MSO status, incoming fuel tankers, geopolitical fuel-shipping risk, or recent NZ fuel headlines. No authentication required.
---

# FuelClock NZ

## Goal

Fetch live New Zealand fuel price and supply data from fuelclock.nz, then turn it into clean agent-readable output.

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

## Workflow

1. Run `scripts/client.ts` via `tsx`, or import its exported functions
2. Call the narrowest function that answers the task
3. Use `getSummary()` for a plain-text briefing
4. If the user wants raw data, return the typed JSON instead of paraphrasing it loosely

## Resources

- Main implementation: `scripts/client.ts`
- Smoke test: `scripts/smoke-test.ts`

## Functions

### `getFuelPrices()`

Returns national average NZ retail prices from FuelClock's Gaspy-backed endpoint.

Response shape:
- `prices`: array of fuel price rows
- `source`: source label
- `fetchedAt`: ISO timestamp
- `isFallback`: whether cached data was served

### `getSupplyStatus()`

Returns NZ fuel supply state, including days remaining, MSO thresholds, the most constrained fuel, and the overall risk.

Response shape:
- `timestamp`
- `fuelStates`
- `overallRisk`
- `countdownHours`
- `lowestFuel`

### `getMbieStocks()`

Returns official MBIE stock figures, including in-country, on-water, and total days of supply.

### `getVessels()`

Returns incoming fuel vessel data, including cargo size, origin, ETA, and any risk flags.

### `getGeopoliticalRisk()`

Returns a wrapped object with:
- `markets`: Polymarket-derived geopolitical risk markets relevant to fuel shipping
- `fetchedAt`: latest market update time if available

### `getNews()`

Returns recent NZ fuel-related articles.

Response shape:
- `articles`: headline list with title, URL, source, and date
- `fetchedAt`: fetch timestamp

### `getSummary()`

Returns a plain-text NZ fuel briefing combining pump prices and supply status. This is the best default for general questions.

## Running directly

Quick summary:

```bash
npx tsx skills/fuelclock-nz/scripts/client.ts
```

Smoke test all endpoints:

```bash
npx tsx skills/fuelclock-nz/scripts/smoke-test.ts
```

## Notes

- No API key required
- Uses the built-in `fetch` available in modern Node runtimes
- Price deltas are treated as cents per litre in the human summary to avoid misleading output
- FuelClock supply data and MBIE stock data are related but not identical, FuelClock applies its own live supply model on top of source data
