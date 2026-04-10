---
name: fuelclock-nz-watch
description: Monitor NZ fuel watch signals using recent fuel headlines and fuel-shipping market signals. Use when the task involves recent NZ fuel news, geopolitical shipping market signals relevant to NZ fuel supply, or a quick watchlist summary. No authentication required.
---

# FuelClock NZ Watch

## Goal

Track NZ fuel watch signals that sit outside the core price and supply workflow, specifically recent fuel headlines and shipping-related market signals.

## Use this when

- A user asks for recent NZ fuel headlines
- A user asks about geopolitical shipping market signals relevant to NZ fuel supply
- A user wants a quick fuel watchlist summary instead of raw price or stock data

## Do not use this for

- NZ pump prices, use `fuelclock-nz`
- NZ fuel stock levels or MSO status, use `fuelclock-nz`
- Inbound tanker details, use `fuelclock-nz`
- Non-NZ fuel news or broad macro market research

## Preferred workflow

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Use `summary` for a compact watchlist brief
3. Use `risk` when the question is about market signals
4. Use `news` when the question is about recent fuel headlines
5. Use `--json` when another tool or agent needs machine-readable output

## CLI

Run with:

```bash
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts <command> [flags]
```

### `summary [--json]`

Best default for a quick watchlist briefing. Combines top tracked markets with the latest recent fuel headlines.

JSON shape:

- `risk.fetchedAt`
- `risk.totalMarkets`
- `risk.markets[]`
- `news.fetchedAt`
- `news.totalArticles`
- `news.articles[]`

Examples:

```bash
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts summary
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts summary --json
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
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk --limit 5
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk --limit 3 --json
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
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news --limit 3
npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news --limit 5 --json
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
- The watch skill is intentionally separate from `fuelclock-nz`, which stays focused on prices, supply, and vessels
