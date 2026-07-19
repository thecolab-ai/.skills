---
name: nzta-crash-data-nz
description: "Query NZTA/Waka Kotahi Crash Analysis System public crash statistics from the no-key ArcGIS FeatureServer and data.govt.nz CKAN mirror. Use when the task involves New Zealand road deaths, serious injuries, crash severity by region or TLA, yearly road-toll counts, or public CAS crash indicator fields such as weather, light, road surface, vehicle type, roadside objects, and roadworks."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "NZ Transport Agency Waka Kotahi"
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
  thecolab.source_url: "https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/"
  thecolab.allowed_domains: "catalogue.data.govt.nz,opendata-nzta.opendata.arcgis.com,services.arcgis.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZTA Crash Data NZ

## Overview

Read-only CLI over the **NZTA/Waka Kotahi Crash Analysis System (CAS)** public
open-data layer. It uses the no-login ArcGIS FeatureServer for bounded,
paginated queries and data.govt.nz CKAN for source discovery.

Use it for questions about New Zealand road deaths, fatal crashes, serious or
minor injury crashes, regional/TLA crash records, yearly road tolls, and public
crash indicator fields such as weather, light, road surface, vehicle types,
roadside objects, and roadworks.

Do not use it for live state-highway incidents, closures, or roadworks; use
`nz-road-closures` for current operational road status. The public CAS layer
does not expose exact crash dates or detailed driver contributing-factor codes
such as alcohol/drugs, speed as a cause, or fatigue.

## Commands

Run commands from this skill directory with `python3 scripts/cli.py ...`.
Every data command accepts `--json`.

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `datasets` | Check ArcGIS FeatureServer and CKAN mirror reachability | `--json` |
| `crashes` | Return bounded crash records with pagination | `--region`, `--from`, `--to`, `--severity`, `--limit`, `--json` |
| `road-toll` | Sum fatalities and fatal crashes for a calendar year | `--year`, `--json` |
| `factors` | Aggregate public CAS indicator fields | `--region`, `--from`, `--to`, `--top`, `--json` |

`crashes` accepts `--severity fatal|serious|minor|non-injury`. `--region`
matches either `region` or `tlaName` as a substring, so `Auckland`,
`Wellington`, and `Selwyn` are valid examples.

The public layer exposes `crashYear` and `crashFinancialYear`, not exact crash
dates. `--from` and `--to` are accepted as `YYYY-MM-DD`, but the CLI applies
them as calendar-year bounds and includes a `date_precision` note in outputs.
If no date window is supplied, `crashes` and `factors` default to a bounded
recent two-calendar-year window.

## Examples

```bash
# Confirm source endpoints and mirror resources
python3 scripts/cli.py datasets --json

# Fatal crash records in Auckland for 2025
python3 scripts/cli.py crashes --region Auckland --from 2025-01-01 --to 2025-12-31 --severity fatal --limit 10

# Machine-readable current-year road toll
python3 scripts/cli.py road-toll --year 2026 --json

# Public indicator aggregation for Wellington over a bounded window
python3 scripts/cli.py factors --region Wellington --from 2024-01-01 --to 2025-12-31 --json
```

## Notes

- CAS is updated monthly. Fatal crashes are usually available within about 1
  working day; serious and minor injury crashes may lag by about 4 weeks, so
  recent DSI/minor counts can be incomplete.
- The ArcGIS layer page size is capped by the service; `crashes` uses
  `resultOffset`/`resultRecordCount` and enforces a local `--limit` cap to avoid
  unbounded full-history downloads.
- `--source auto` uses ArcGIS first and falls back to a capped CSV mirror scan
  if ArcGIS is unavailable. CSV fallback is intentionally capped by `--scan-cap`
  and may be partial for broad/current queries.
- Endpoint details, field caveats, and pagination notes are in
  [references/api-notes.md](references/api-notes.md).
- The reusable CLI and smoke test live in `scripts/`.

## Resources

- API/source notes: `references/api-notes.md`
- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
