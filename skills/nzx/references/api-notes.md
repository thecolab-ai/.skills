# NZX API Notes

This skill is a read-only wrapper around public NZX website and market-data endpoints. It does not use authenticated API products, broker sessions, cookies, portfolio data, or paid data-feed credentials.

## Sources shipped

### NZX ticker snapshot API

- Provider: NZX Limited
- Website: `https://www.nzx.com`
- API base used by the CLI: `https://api.nzx.com/ticker/1.0`
- Auth model for implemented commands: none
- Data delay: NZX website footer states that market data is delayed by 20 minutes and page information may be cached/current per the displayed timestamp

Implemented endpoints:

- `GET /instrument/{ticker}/last`
  - Command: `quote`
  - Returns one delayed instrument snapshot with price, change, bid/offer, open/high/low, volume, value, market cap, P/E, dividend yield, and update timestamps
  - Example: `https://api.nzx.com/ticker/1.0/instrument/AIR/last`

- `GET /indices/all/last`
  - Command: `index`
  - Returns delayed index snapshots including `NZ50`, `NZ20`, and `ALL`
  - Fields include index value, open/high/low, day change, relative change, and index date

- `GET /nzsx/instruments/last`
  - Commands: `movers`, `search`
  - Returns delayed snapshots for NZSX instruments
  - Used for gainers/losers and to enrich search results with price/change/volume

### NZX public market-data API

- Provider: NZX Limited
- API base used by the CLI: `https://api.nzx.com/public`
- Auth model for implemented commands: none

Implemented endpoints:

- `GET /market/NZSX/instruments/active.json`
  - Command: `search`
  - Returns active NZSX instruments with code, ISIN, name, market, category, type, shares issued, and listing dates

- `GET /instruments/by/code/{ticker}/all.json`
  - Commands: `history`, `dividends`
  - Resolves an NZX ticker to instrument metadata and ISIN

- `GET /instrument/{isin}/metrics/performance/past/2Y.json`
  - Command: `history`
  - Returns daily performance rows for roughly two years
  - Fields include `firstPrice`, `highPrice`, `lowPrice`, `lastPrice`, `marketPrice`, `highOffer`, `lowOffer`, and index/capital-adjustment values
  - The CLI maps these to OHLC-style fields: open, high, low, close, and market price

- `GET /instrument/{isin}/metrics/activity/past/2Y.json`
  - Command: `history`
  - Returns matching daily activity rows with volume, value, on/off-market volume, trade count, capitalisation, and quote bases
  - The CLI joins these rows to performance rows by NZ local date

- `GET /instrument/{isin}/dividends/upcoming.json`
  - Command: `dividends`
  - Returns upcoming dividends where available

- `GET /instrument/{isin}/dividends/past/3Y.json`
  - Command: `dividends`
  - Returns recent past dividends for roughly three years
  - `amount` is paired with `baseQuantity`; the CLI derives `amount_per_security = amount / baseQuantity`

## Sources checked but not shipped

- `https://api.nzx.com/ticker/1.0/instrument/{ticker}` and `https://api.nzx.com/ticker/1.0/instrument/{ticker}/price-history` are SSE-style live endpoints. They return an initial event and then keep the HTTP connection open. The CLI uses `/last` snapshot variants instead so commands are deterministic and terminate.
- `GET /instrument/{isin}/metrics/pricing/all.json` under `https://api.nzx.com/public` returned HTTP 403 in live no-login testing, so it is not used.
- NZX website pages such as `https://www.nzx.com/instruments/AIR`, `https://www.nzx.com/instruments/AIR/dividends`, `https://www.nzx.com/markets/NZSX`, and `https://www.nzx.com/markets/indices` embed equivalent data in Next.js `__NEXT_DATA__`. The CLI uses the underlying JSON endpoints instead of scraping those pages.
- Sharesies/Jarden-style public ticker fallbacks were not needed because the NZX public endpoints above cover the requested read-only commands without login.

## Schema notes

- Ticker API `priceChangeRelative` and index `valueChangeRelative` are decimal fractions, for example `0.0088` for `0.88%`. The CLI emits both `change_relative` and `change_percent`.
- NZX public performance timestamps represent NZ local trading dates. The CLI converts epoch values through `Pacific/Auckland` before filtering or emitting dates.
- `history` defaults to the latest 30 returned rows when no `--from`, `--to`, or `--limit` is supplied. Supplying a date range returns all matched rows unless `--limit` is also supplied.
- Historical rows are daily, not tick-by-tick. Intraday trade points are available from ticker price-history snapshots, but the shipped `history` command uses the richer two-year daily performance/activity endpoints.
- Bond, ETF, warrant, and ordinary-share fields share the same ticker schema; some financial fields can be null depending on instrument type.

## Live verification snapshot

Representative live checks on 23 May 2026 UTC succeeded for:

- `quote AIR FPH MEL ATM IFT`
- `index --name nzx50`
- `movers --top --limit 5`
- `history AIR --from 2026-05-20 --to 2026-05-22`
- `dividends AIR`
- `search "a2 milk"`
