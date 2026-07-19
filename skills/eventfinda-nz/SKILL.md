---
name: eventfinda-nz
description: "Search and inspect public Eventfinda New Zealand event listings from the no-login website pages. Use when the task involves finding NZ events by location, category, or keyword, getting Eventfinda event URLs, venues, dates, public session times, ticket badges, images, or JSON-LD detail from public event pages."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "events-and-media"
  thecolab.source_owner: "Eventfinda"
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
  thecolab.source_url: "https://www.eventfinda.co.nz"
  thecolab.allowed_domains: "www.eventfinda.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Eventfinda NZ

## Goal

Query live public Eventfinda New Zealand event listings through a small deterministic CLI with human-readable and JSON output.

## Use this when

- A user asks what events are on in Auckland, Wellington, Christchurch, or New Zealand generally
- A workflow needs Eventfinda event titles, URLs, venues, dates, categories, badges, or images
- A user has an Eventfinda event URL/path and wants structured details, sessions, venue address, geo coordinates, or offer/pricing metadata published in the page JSON-LD
- An agent needs a no-login NZ event discovery source before checking venue-specific sources

## Do not use this for

- Buying tickets, reserving seats, logging into Eventfinda, or changing account data
- High-volume scraping, full-site mirroring, or alerting that hammers Eventfinda pages
- Private organiser, attendee, sales, or ticket inventory data
- Treating scraped public website structure as a permanent API contract
- The official Eventfinda developer API unless you explicitly have credentials and add a separate authenticated wrapper

## Preferred workflow

1. Run `scripts/cli.py upcoming --location <slug>` for broad discovery
2. Use `search <query>` for keyword searches such as artists, festivals, venues, or genres
3. Pass the chosen event URL to `event <url>` for structured JSON-LD details and sessions
4. Use `--json` for agent chaining, comparisons, or structured summaries
5. Cite Eventfinda event URLs and include the date/venue when reporting findings
6. If a listing has repeated sessions, summarize the first few and mention the total session count

## CLI

Run with:

```bash
python3 skills/eventfinda-nz/scripts/cli.py <command> [flags]
```

### Commands

- `upcoming [--location slug] [--category slug] [--page N] [--limit N] [--json]` — list public Eventfinda event cards from a location/category page
- `search <query> [--page N] [--limit N] [--json]` — search Eventfinda public pages by keyword
- `event <url-or-path> [--json] [--raw]` — inspect a public Eventfinda event detail page using embedded JSON-LD

Examples:

```bash
python3 skills/eventfinda-nz/scripts/cli.py upcoming --location auckland --limit 5
python3 skills/eventfinda-nz/scripts/cli.py upcoming --location wellington --category concerts-gig-guide --limit 5 --json
python3 skills/eventfinda-nz/scripts/cli.py search "jazz" --limit 5 --json
python3 skills/eventfinda-nz/scripts/cli.py event /2026/classic-comedy-all-stars-festival-edition/auckland --json
python3 skills/eventfinda-nz/scripts/cli.py event https://www.eventfinda.co.nz/2026/classic-comedy-all-stars-festival-edition/auckland --raw --json
```

## Location and category slugs

The CLI uses Eventfinda website URL slugs. Common locations include:

- `new-zealand`
- `auckland`
- `wellington`
- `christchurch`
- `hamilton`
- `dunedin`
- `tauranga`

Category slugs are the same path segments Eventfinda uses, for example:

- `concerts-gig-guide`
- `festivals-lifestyle`
- `performing-arts`
- `sports-outdoors`
- `exhibitions`
- `comedy`

If a category/location combination produces no cards, try the broader `upcoming --location <slug>` page or `search <query>`.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and website notes: `references/api-notes.md`

## Notes

- No username, password, API key, account cookie, or browser automation is required for the implemented public website commands
- The official `api.eventfinda.co.nz/v2` developer API returned `401 Incorrect authentication details supplied` without Basic-auth credentials during verification; this skill intentionally uses public website pages instead
- Listing pages are parsed from public HTML event cards; detail pages are parsed from embedded Schema.org JSON-LD
- Eventfinda page markup can change; run the smoke test before relying on this skill in automation
- Keep requests narrow and respectful
