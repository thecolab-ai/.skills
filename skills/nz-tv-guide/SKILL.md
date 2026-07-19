---
name: nz-tv-guide
description: "Query NZ TV guide and EPG for Sky NZ, Sky Sport, ESPN, Trackside, and Freeview/TVNZ. Use for NZ sport showtimes, movie schedules, and what's on now or tonight. Read-only; no streaming or account actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "events-and-media"
  thecolab.source_owner: "Sky New Zealand and participating broadcasters"
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
  thecolab.source_url: "https://api.skyone.co.nz/exp/graph"
  thecolab.allowed_domains: "api.skyone.co.nz,freeviewnz.tv,tvguide.sky.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ TV Guide

## Goal

Answer live New Zealand TV guide questions through a small deterministic CLI with human-readable and JSON output, focused on "when is this sport on, what channel, what time?" workflows.

## Use this when

- A user asks what is on Sky Sport, ESPN, Trackside, or another Sky channel
- A user asks when rugby, cricket, Formula 1, football, netball, basketball, NFL, or tennis is on TV in NZ
- A user wants tonight's sport or movie schedule
- A user wants to search current EPG listings by programme, team, sport, or channel name
- A workflow needs lightweight machine-readable NZ TV schedule data

## Do not use this for

- Streaming playback, Sky Sport Now account access, subscriptions, purchases, My Sky recording, reminders, or login-gated actions
- Channels outside New Zealand
- Historical TV listings beyond what the live guide sources currently expose
- Republishing EPG listings as a dataset or high-volume scraping
- Claiming a fixture is official if it is not present in the live EPG snapshot

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `sport` for "what sport is on?" questions and `tonight --type sport` for the 7pm-late sports window
3. Use `now --channel <name>` for current channel checks
4. Use `search <query>` for team, competition, sport, or show lookups across upcoming guide days
5. Use `schedule <channel> --date YYYY-MM-DD` for a full-day channel listing
6. Use `--json` for agent chaining, comparisons, or structured reports
7. Mention that listings are live unofficial EPG snapshots and can change at the source

## CLI

Run with:

```bash
python3 skills/nz-tv-guide/scripts/cli.py <command> [flags]
```

## Commands

- `channels [--provider sky|freeview|tvnz] [--type sport|entertainment|news] [--json]` - list channels
- `now [--channel <name>] [--provider sky|freeview|tvnz] [--json]` - show what is on now
- `next [--channel <name>] [--provider sky|freeview|tvnz] [--limit N] [--json]` - upcoming programmes
- `schedule <channel> [--date YYYY-MM-DD] [--provider sky|freeview|tvnz] [--json]` - full day schedule for a channel
- `search <query> [--date YYYY-MM-DD] [--provider sky|freeview|tvnz] [--limit N] [--json]` - find matching programmes
- `sport [--code rugby|cricket|football|f1|netball|basketball|nfl|tennis] [--date YYYY-MM-DD] [--from HH:MM] [--to HH:MM] [--provider sky|freeview|tvnz] [--limit N] [--json]` - sport programmes, defaulting to Sky Sport
- `tonight [--provider sky|freeview|tvnz] [--type sport|movies] [--json]` - tonight's 7pm-late sport or movie listings

## Examples

```bash
python3 skills/nz-tv-guide/scripts/cli.py now --channel "Sky Sport 1"
python3 skills/nz-tv-guide/scripts/cli.py sport --code rugby --date 2026-05-24 --json
python3 skills/nz-tv-guide/scripts/cli.py sport --from 19:00 --to 22:00
python3 skills/nz-tv-guide/scripts/cli.py tonight --type sport
python3 skills/nz-tv-guide/scripts/cli.py search "All Blacks" --limit 10
python3 skills/nz-tv-guide/scripts/cli.py search "Coronation Street" --provider freeview --json
python3 skills/nz-tv-guide/scripts/cli.py schedule "Sky Sport 1" --date 2026-05-24
python3 skills/nz-tv-guide/scripts/cli.py schedule "TVNZ 1" --provider freeview --date 2026-05-24
python3 skills/nz-tv-guide/scripts/cli.py channels --provider sky --type sport --json
```

## Notes

- Detailed endpoint, schema, freshness, and time-zone notes are in `references/api-notes.md`
- Sky listings come from Sky NZ's public TV Guide at `https://tvguide.sky.co.nz/`, backed by the no-login `https://api.skyone.co.nz/exp/graph` EPG GraphQL endpoint used by the website
- Free-to-air listings come from the public Freeview TV Guide page at `https://freeviewnz.tv/whats-on/tv-guide/`
- `--provider tvnz` is a convenience filter over Freeview's public TVNZ linear-channel listings; it does not call a separate TVNZ account or streaming API
- Sky Sport, Sky Sport Select, ESPN, Trackside, Sky Arena, and Sky movie/entertainment/news groups are available through Sky channel groups
- Sky Sport NOW streaming-only account or entitlement schedules are not implemented; use Sky linear EPG results as the no-login source of truth
- All displayed times are converted to `Pacific/Auckland`; human output intentionally does not show UTC
- EPGs are live snapshots and typically refresh at least daily, but programmes can move or be corrected by providers during the day
- No username, password, account cookie, HAR, browser storage, streaming URL, recording, purchase, or mutation endpoint is required or used
