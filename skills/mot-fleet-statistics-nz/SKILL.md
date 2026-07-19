---
name: mot-fleet-statistics-nz
description: "Query New Zealand Ministry of Transport annual fleet statistics workbooks for VKT, fleet composition, and light-fleet fuel or powertrain counts. Use when the task involves NZ vehicle kilometres travelled, annual fleet statistics, Ministry fleet workbook tables, EV-transition research, fuel counts, or source caveats for bot-protected transport data."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Ministry of Transport"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.transport.govt.nz/statistics-and-insights/fleet-statistics/sheet/annual-fleet-statistics"
  thecolab.allowed_domains: "www.mot-dev.link,www.transport.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# MoT Fleet Statistics NZ

## Goal

Discover and extract public Ministry of Transport annual vehicle fleet workbook tables with a read-only, keyless CLI.

## Use This When

- A user asks for New Zealand annual vehicle kilometres travelled (VKT)
- A workflow needs Ministry annual fleet workbook sheet names, table headings, or source caveats
- A transport or EV-transition analysis needs light-fleet fuel or powertrain counts
- Another tool already has a downloaded `NZVehicleFleet_2024.xlsx` workbook and needs JSON rows

## Do Not Use This For

- Current individual-vehicle register rows; use NZTA open vehicle fleet data instead
- Real-time traffic, crash, charging-station, or public-transport operations data
- Registration mutation, licence checks, owner lookup, or authenticated Motor Vehicle Register access
- Hybrid/PHEV VKT allocation unless the workbook publishes that split directly

## Preferred Workflow

1. Run `scripts/cli.py datasets --json` to inspect the official source pages, workbook-discovery status, release notes, and caveats.
2. Run `tables --json` to list workbook sheets and preview row/column headings when the workbook is reachable.
3. Use focused commands for common For Good transport questions:
   - `vkt --year 2024 --json`
   - `fuel-counts --year 2024 --json`
4. If the Ministry site blocks direct HTTP, download the public workbook in a browser and rerun with `--url file:///absolute/path/NZVehicleFleet_2024.xlsx`.
5. Keep `source_url`, `fetched_at`, `table`, `sheet`, and `notes` with any reported figures.

## CLI

Run with:

```bash
python3 skills/mot-fleet-statistics-nz/scripts/cli.py <command> [flags]
```

Commands:

- `datasets [--json]` - report source pages, release notes, workbook discovery status, and caveats
- `tables [--url URL] [--json]` - list workbook sheets with preview headings and year coverage
- `vkt --year YEAR [--url URL] [--json]` - return rows from annual VKT/travel tables for the requested year
- `fuel-counts --year YEAR [--url URL] [--json]` - return light-fleet fuel or powertrain count rows for the requested year
- `workbook --url URL [--sheet NAME] [--limit N] [--json]` - parse a public XLSX workbook URL or local `file://` workbook

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and table caveats: `references/api-notes.md`

## Notes

- The CLI is read-only, keyless, and uses Python standard library modules only.
- XLSX workbooks are parsed with `zipfile` and `xml.etree.ElementTree`; no `openpyxl` dependency is required.
- The Ministry website can return Incapsula/bot-protection HTML to HTTP clients. Commands classify that as `blocked` and include the official source URL instead of treating the source as missing.
- The 2024 workbook publishes petrol, diesel, and pure-electric VKT tables; do not invent hybrid or PHEV VKT splits unless a future Ministry table publishes them.
