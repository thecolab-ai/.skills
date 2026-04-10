---
name: nz-news
description: Aggregate RSS feeds from New Zealand news websites (NZ Herald, Stuff, RNZ, Newsroom, The Spinoff, Interest.co.nz). Use when the task involves NZ news, current events in New Zealand, what's happening in NZ, or NZ headlines. No authentication required.
---

# NZ News

## Goal

Aggregate live RSS feeds from major New Zealand news websites into a single CLI tool for quick headline scanning, source browsing, and topic searching.

## Use this when

- A user asks about current NZ news or what's happening in New Zealand
- A user wants today's headlines from NZ media
- A user asks about news from a specific NZ outlet (Stuff, RNZ, NZ Herald, etc.)
- A user wants to find NZ news about a specific topic or keyword
- A user needs a quick news briefing for New Zealand

## Do not use this for

- International news not covered by NZ outlets
- Historical news or archived articles
- Paywalled content (some NZ Herald articles may be paywalled)
- Social media or non-news content
- Real-time breaking news alerts (RSS feeds have a delay)

## Preferred workflow

1. Run `scripts/cli.ts` with the narrowest subcommand that answers the task
2. Use default human output for direct answers
3. Use `--json` when another tool or agent needs machine-readable output
4. For topic-specific questions, use `topic <keyword>` to filter

## CLI

Run with:

```bash
npx tsx skills/nz-news/scripts/cli.ts <command> [flags]
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

News from a specific source. Accepts source ID (rnz, stuff, herald, spinoff, newsroom, interest) or name. Default limit: 10.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts source rnz
npx tsx skills/nz-news/scripts/cli.ts source stuff --limit 5
npx tsx skills/nz-news/scripts/cli.ts source herald --json
```

### `topic <keyword> [--limit N] [--json]`

Filter headlines by keyword across all primary sources. Searches titles and summaries. Default limit: 10.

Examples:

```bash
npx tsx skills/nz-news/scripts/cli.ts topic cyclone
npx tsx skills/nz-news/scripts/cli.ts topic "housing market"
npx tsx skills/nz-news/scripts/cli.ts topic rugby --limit 5 --json
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
| rnz-te-ao-maori | RNZ Te Ao Maori | RSS | Category |

Primary sources are queried by default. Category feeds (RNZ sub-feeds) are available via `source <id>` but excluded from `headlines`/`topic`/`summary` to avoid duplicates.

## Resources

- CLI entrypoint: `scripts/cli.ts`
- Feed definitions and parser: `scripts/feeds.ts`
- Live smoke test: `scripts/smoke-test.ts`

## Notes

- No API key required
- Uses the built-in `fetch` available in modern Node runtimes
- No external XML parsing dependencies — uses regex-based RSS/Atom parsing
- Default output is human-readable; `--json` output is for chaining into other tools or agent steps
- Headlines are deduplicated by normalised title across sources
- RNZ category feeds may overlap with the main RNZ feed
