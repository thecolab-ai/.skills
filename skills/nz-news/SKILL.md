---
name: nz-news
description: Aggregate RSS feeds from major New Zealand news websites. Use when the task involves NZ news, current events in New Zealand, what's happening in NZ, NZ headlines, or searching NZ stories by topic, timeframe, or source. No authentication required.
---

# NZ News

## Goal

Aggregate live RSS feeds from major New Zealand news websites into a single CLI tool for quick headline scanning, source browsing, and obvious topic searching.

## Use this when

- A user asks about current NZ news or what's happening in New Zealand
- A user wants today's headlines from NZ media
- A user asks about news from a specific NZ outlet (Stuff, RNZ, NZ Herald, etc.)
- A user wants to search NZ news by topic, keyword, timeframe, or source
- A user needs a quick New Zealand news briefing

## Do not use this for

- International news not covered by NZ outlets
- Historical news or archived articles
- Paywalled content (some NZ Herald articles may be paywalled)
- Social media or non-news content
- Real-time breaking news alerts (RSS feeds have a delay)

## Preferred workflow

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Start with `search` for any topic lookup, either positionally or with flags
3. Use `--source`, `--since-hours`, `--since-date`, `--contains-all`, `--exact`, and `--exclude` when the request needs tighter matching
4. Use default human output for direct answers
5. Use `--json` when another tool or agent needs machine-readable output

## CLI

Run with:

```bash
npx tsx skills/nz-news/scripts/cli.ts <command> [flags]
```

### Search first

The easiest path for topic lookups is now `search`.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts search cyclone
npx tsx skills/nz-news/scripts/cli.ts search --keyword cyclone --since-hours 24
npx tsx skills/nz-news/scripts/cli.ts search --keyword "housing market" --contains-all --source rnz,newsroom
npx tsx skills/nz-news/scripts/cli.ts search --keyword coalition --exact --since-date 2026-04-01
npx tsx skills/nz-news/scripts/cli.ts topic cyclone --exclude sport --limit 5
```

`topic` is kept as an alias for `search`, so both of these work:

```bash
npx tsx skills/nz-news/scripts/cli.ts topic cyclone
npx tsx skills/nz-news/scripts/cli.ts search --keyword cyclone
```

### `headlines [--limit N] [--json]`

Top headlines across all primary sources (NZ Herald, Stuff, RNZ, Newsroom, The Spinoff, Interest.co.nz), deduplicated and sorted by date. Default limit: 10.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts headlines
npx tsx skills/nz-news/scripts/cli.ts headlines --limit 20
npx tsx skills/nz-news/scripts/cli.ts headlines --json
```

### `source <name> [--limit N] [--json]`

News from a specific source. Accepts source ID (for example `rnz`, `stuff`, `herald`) or a source name. Default limit: 10.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts source rnz
npx tsx skills/nz-news/scripts/cli.ts source stuff --limit 5
npx tsx skills/nz-news/scripts/cli.ts source herald --json
```

### `search [keyword...] [flags]`

Search headlines and summaries across NZ sources. You can provide the search term positionally or with `--keyword`.

Useful flags:

- `--keyword <text>` for flag-based search input
- `--source rnz,herald` to limit the search to specific feeds
- `--since-hours <hours>` to keep only recent stories
- `--since-date <YYYY-MM-DD or ISO timestamp>` for a fixed start date
- `--contains-all` to require every term in a multi-word query
- `--exact` to match an exact phrase
- `--exclude sport,opinion` to remove unwanted terms
- `--limit N`
- `--json`

JSON shape:

- `fetchedAt`
- `keyword`
- `matchMode`
- `sourcesQueried`
- `sourcesOk`
- `filters.sourceIds`
- `filters.sinceHours`
- `filters.sinceDate`
- `filters.exclude`
- `filters.limit`
- `totalMatching`
- `returnedCount`
- `items[]` with `title`, `url`, `published`, `source`, `sourceId`, `summary`
- `errors[]`

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts search cyclone
npx tsx skills/nz-news/scripts/cli.ts search --keyword cyclone --since-hours 24
npx tsx skills/nz-news/scripts/cli.ts search --keyword "housing market" --contains-all --source rnz,newsroom
npx tsx skills/nz-news/scripts/cli.ts search --keyword coalition --exact --since-date 2026-04-01
npx tsx skills/nz-news/scripts/cli.ts topic cyclone --exclude sport --limit 5 --json
```

### `sources [--json]`

List all available news sources with a live status check showing which feeds are working, how many items each returned, and response time.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts sources
npx tsx skills/nz-news/scripts/cli.ts sources --json
```

### `summary [--json]`

Brief summary showing total story count across sources and the top 5 headlines.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts summary
npx tsx skills/nz-news/scripts/cli.ts summary --json
```

## Sources

| ID | Name | Format | Type |
|---|---|---|---|
| herald | NZ Herald | RSS | Primary |
| stuff | Stuff | Atom | Primary |
| rnz | RNZ | RSS | Primary |
| newsroom | Newsroom | RSS | Primary |
| spinoff | The Spinoff | Atom | Primary |
| interest | Interest.co.nz | RSS | Primary |
| rnz-politics | RNZ Politics | RSS | Category |
| rnz-business | RNZ Business | RSS | Category |
| rnz-national | RNZ National | RSS | Category |
| rnz-world | RNZ World | RSS | Category |
| rnz-sport | RNZ Sport | RSS | Category |
| rnz-te-ao-maori | RNZ Te Ao Māori | RSS | Category |

Primary sources are queried by default. Category feeds (RNZ sub-feeds) are available via `source <id>` and `search --source <id>`, but excluded from `headlines` and `summary` to avoid duplicate stories.

## Setup

No API key required — just Node.js and `npx tsx`.

## Resources

- CLI entrypoint: `scripts/cli.ts`
- Feed definitions and parser: `scripts/feeds.ts`
- Live smoke test: `scripts/smoke-test.ts`

## Notes

- No API key required
- Uses the built-in `fetch` available in modern Node runtimes
- No external XML parsing dependencies, uses regex-based RSS and Atom parsing
- Default output is human-readable, `--json` output is for chaining into other tools or agent steps
- Headlines are deduplicated by normalised title across sources
- RNZ category feeds may overlap with the main RNZ feed
