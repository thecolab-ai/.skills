---
name: doc-nz
description: "Query Department of Conservation (DOC) New Zealand public huts, campsites, Great Walk booking availability, current alerts, and track pages through a lightweight read-only CLI. Use when the task involves DOC huts, campsites, Great Walks, availability calendars, track alerts, or DOC place status in New Zealand."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Department of Conservation"
  thecolab.source_type: "official"
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
  thecolab.source_url: "https://www.doc.govt.nz/"
  thecolab.allowed_domains: "bookings.doc.govt.nz,doc.govt.nz,prod-nz-rdr.recreation-management.tylerapp.com,www.doc.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# DOC NZ

## Goal

Query live Department of Conservation New Zealand huts, campsites, Great Walk availability, alerts, and track information through a small deterministic CLI with human-readable and JSON output, without login or booking actions.

## Use this when

- A user asks whether a Great Walk hut or campsite has spaces for a date range
- A user wants DOC Great Walk booking status or booking windows
- A user asks for current DOC track, hut, campsite, park, or region alerts
- A user wants a quick DOC track description with active alerts
- A workflow needs machine-readable DOC hut, campsite, or Great Walk data

## Do not use this for

- Booking, modifying, holding, cancelling, or paying for DOC reservations
- Login, customer accounts, payment, checkout, or basket workflows
- Private booking data, personal itineraries, or account-specific prices
- Non-DOC accommodation or non-New Zealand public land
- Safety-critical trip decisions without checking DOC directly before travel

## Preferred workflow

1. Run `scripts/cli.py` with the narrowest subcommand that answers the task
2. Use `great-walks` to resolve DOC Great Walk place ids and booking windows
3. Use `availability` for date-grid availability on a Great Walk name/place id or facility id
4. Use `alerts --region <region>` for current regional DOC alerts and closures
5. Use `track <name>` for a DOC page summary plus page-level alerts
6. Use `--json` for agent chaining, comparisons, and reports

## CLI

Run with:

```bash
python3 skills/doc-nz/scripts/cli.py <command> [flags]
```

### Commands

- `great-walks [--json]` - list Great Walks, public booking window, ids, and open/closed booking status
- `huts [--region text] [--query text] [--limit N] [--json]` - list popular public DOC booking places and filter locally
- `huts --great-walk <name-or-id> [--from DATE] [--to DATE] [--nights N] [--accommodation NAME] [--direction ID_OR_NAME] [--json]` - list Great Walk hut/campsite facility ids with an availability grid
- `availability <name-or-id> [--from DATE] [--to DATE] [--nights N] [--accommodation NAME] [--direction ID_OR_NAME] [--json]` - Great Walk availability by walk name/place id, or facility id from `huts --great-walk`
- `alerts [--region REGION] [--limit N] [--json]` - list DOC alert regions, or current alert groups for one region
- `track <name> [--json]` - track or booking-place description with DOC page alerts where a DOC page is linked

## Examples

```bash
python3 skills/doc-nz/scripts/cli.py great-walks --json
python3 skills/doc-nz/scripts/cli.py huts --query campsite --limit 10 --json
python3 skills/doc-nz/scripts/cli.py huts --great-walk routeburn --from 2026-11-01 --nights 1 --accommodation Hut --json
python3 skills/doc-nz/scripts/cli.py availability "Milford Track" --from 2026-11-01 --nights 3 --json
python3 skills/doc-nz/scripts/cli.py availability 2864 --from 2026-11-01 --nights 1 --json
python3 skills/doc-nz/scripts/cli.py alerts --region fiordland --limit 5 --json
python3 skills/doc-nz/scripts/cli.py track "Routeburn Track" --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Upstream source: Department of Conservation New Zealand, including `bookings.doc.govt.nz` and `doc.govt.nz`
- No API key, username, password, account cookie, or browser automation is required for the implemented read-only commands
- Booking availability is live public availability, not a hold or guarantee; always confirm directly with DOC before travel
- Great Walk availability is the most complete booking surface; generic DOC booking place detail endpoints were not reliable enough to expose
- Endpoint shapes can change; verify with a small live query before relying on broad workflows
- Do not use this skill for booking actions, checkout, payment, login, account access, or high-volume scraping
