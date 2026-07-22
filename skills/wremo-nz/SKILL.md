---
name: wremo-nz
description: "Read Wellington Region Emergency Management Office (WREMO) public news and updates through a lightweight no-login CLI: news listings with dates and snippets, and full article text by slug or URL. Use when the task involves WREMO announcements, Wellington-region emergency management updates, preparedness campaigns, or recovery information. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "emergency"
  thecolab.source_owner: "Wellington Region Emergency Management Office"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.wremo.nz/news-and-events/wremo-news"
  thecolab.allowed_domains: "www.wremo.nz"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# WREMO NZ

## Goal

Read the Wellington Region Emergency Management Office's public news and updates —
the official regional civil defence communications channel — as structured data:
listings with dates and snippets, and full article text.

## Use this when

- A task needs current WREMO announcements or severe-weather/incident updates
- A task needs Wellington-region preparedness or recovery information as text
- A workflow monitors official regional emergency management communications

## Do not use this for

- Live CAP alerts (use `nz-emergency-alerts`) or Emergency Mobile Alerts
- Community Emergency Hub locations (query the GWRC portal via `wcc-arcgis-nz`)
- Any account, submission, or contact flow

## Commands

```bash
python3 skills/wremo-nz/scripts/cli.py news --limit 10
python3 skills/wremo-nz/scripts/cli.py news --search "severe weather" --json
python3 skills/wremo-nz/scripts/cli.py article severe-weather-update-26-june --json
```

- `news [--search TEXT] [--limit N] [--json]` — news items with title, date, snippet, URL, newest first
- `article SLUG_OR_URL [--json]` — full paragraphs of one article (site chrome stripped)

## Notes

- HTML parsing of wremo.nz (no feed exists); a markup change fails closed with an
  explicit schema error rather than an empty success.
- News is WREMO's editorial channel — updated during events (e.g. severe weather
  updates) but not a real-time alert stream; pair with `nz-emergency-alerts`.
- Dates are NZ-style ("6 Sept 2024") normalised to ISO; unparseable dates are kept
  as raw text rather than dropped.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Markup assumptions and stability notes: `references/source-notes.md`
