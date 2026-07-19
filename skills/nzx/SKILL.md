---
name: nzx
description: "Query NZX public delayed market data through a lightweight no-login CLI. Use when the task involves New Zealand Exchange listed share prices, S&P/NZX index levels, NZSX movers, historical daily OHLC-style performance, dividends, or ticker/company lookup. Read-only; no account, portfolio, order, or trading actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "finance"
  thecolab.source_owner: "NZX"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://api.nzx.com/ticker/1.0"
  thecolab.allowed_domains: "api.nzx.com,www.nzx.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZX

## Goal

Query NZX public delayed market data through a small deterministic CLI with human-readable and JSON output, without browser automation, login, API keys, portfolio access, or local cache state.

This skill ships support for:

- Delayed quote snapshots for one or more NZX tickers
- S&P/NZX 50, S&P/NZX 20, and S&P/NZX All index snapshots
- NZSX top gainers and losers
- Two-year daily OHLC-style instrument performance with volume/activity fields
- Upcoming and recent dividends
- NZSX ticker/company search

## Use this when

- A user asks for current delayed NZX-listed share or ETF prices
- A user asks for NZX 50, NZX 20, or NZX All index levels
- A user wants today's NZSX gainers or losers
- A user wants daily price history, high/low/open/close, volume, or market cap for an NZX ticker
- A user asks about recent or upcoming NZX dividends
- A user wants to find NZX tickers by company or instrument name
- A workflow needs public, no-login, machine-readable NZX market data

## Do not use this for

- Trading, order placement, portfolio holdings, broker login, watchlists, or account actions
- Real-time market-data redistribution or claims that values are live tick-by-tick
- Investment advice, valuation recommendations, tax advice, or suitability decisions
- Non-NZX exchanges unless the instrument is surfaced by NZX public data
- Paid NZX data products or authenticated vendor feeds

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `quote` for delayed ticker snapshots and `index` for S&P/NZX index levels
3. Use `movers --top` or `movers --losers` for market-wide daily movers
4. Use `history <ticker> --from ... --to ...` for daily OHLC-style history
5. Use `dividends <ticker>` for upcoming and past dividend rows
6. Use `search <query>` to resolve company names to ticker codes before quote/history calls
7. Use `--json` when another tool or agent needs machine-readable output
8. Mention that NZX market data is delayed by 20 minutes and may be cached

## CLI

Run with:

```bash
python3 skills/nzx/scripts/cli.py <command> [flags]
```

## Commands

- `quote <ticker> [<ticker>...] [--json]` - delayed price snapshot for one or more tickers
- `index [--name nzx50|nzx20|nzx-all] [--json]` - delayed index level and day change
- `movers [--top|--losers] [--limit N] [--json]` - top NZSX gainers or losers today
- `history <ticker> [--from DATE] [--to DATE] [--limit N] [--json]` - daily OHLC-style performance history
- `dividends <ticker> [--json]` - upcoming and recent dividends
- `search <query> [--limit N] [--json]` - find NZSX tickers by code or company/instrument name

Examples:

```bash
python3 skills/nzx/scripts/cli.py quote AIR FPH MEL --json
python3 skills/nzx/scripts/cli.py index --name nzx50 --json
python3 skills/nzx/scripts/cli.py movers --losers --limit 5
python3 skills/nzx/scripts/cli.py history AIR --from 2026-05-01 --to 2026-05-22 --json
python3 skills/nzx/scripts/cli.py dividends AIR --json
python3 skills/nzx/scripts/cli.py search "a2 milk" --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, username, password, account cookie, broker login, or browser session is required for implemented read-only operations
- Upstream source is NZX: `https://www.nzx.com`, `https://api.nzx.com/ticker/1.0`, and `https://api.nzx.com/public`
- NZX states that market data is delayed by 20 minutes and page information may be cached; include that caveat in user-facing market-data answers
- `quote`, `index`, `movers`, and `search` use delayed ticker snapshot endpoints under `https://api.nzx.com/ticker/1.0`
- `history` and `dividends` use public NZX market-data endpoints under `https://api.nzx.com/public`
- The live SSE-style ticker endpoints are intentionally not used by the CLI because they stream indefinitely; the CLI uses `/last` snapshot endpoints so commands terminate
- Default output is human-readable; every data command supports `--json` for chaining into other tools
- Avoid high-volume polling; use narrow ticker lists, small mover limits, and bounded history ranges
