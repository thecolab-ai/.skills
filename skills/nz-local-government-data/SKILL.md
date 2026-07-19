---
name: nz-local-government-data
description: "Discover and preview official New Zealand local government finance, performance, and statistics datasets from Stats NZ/data.govt.nz, DIA local council downloads, DIA council performance metrics, and OAG local-government insight sources. Use when the task involves council profiles, rates revenue, local authority statistics, comparing councils, finding machine-readable local-government datasets, or identifying official source gaps. Read-only, no login or API key required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Stats NZ, Department of Internal Affairs, and Office of the Auditor-General"
  thecolab.source_type: "mixed"
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
  thecolab.source_url: "https://catalogue.data.govt.nz/api/3/action/"
  thecolab.allowed_domains: "catalogue.data.govt.nz,oag.parliament.nz,www.localcouncils.govt.nz,www.mcert.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Local Government Data

## Goal

Find and preview official New Zealand local government datasets without login, mutation, API keys, browser automation, or invented structure for PDF-only sources.

The skill focuses on discovery-first access to:

- Stats NZ / data.govt.nz local-government and local-authority statistics catalogue resources
- DIA Local Councils downloadable data index resources
- DIA local government performance metrics / council profile data release
- OAG local-government insights as official context, not as invented structured rows

## Use this when

- A user asks where official NZ council finance, performance, rates, population, or comparison data lives
- A user needs a council list with identifiers/types from DIA council profile data
- A user wants a small preview of DIA council performance metrics such as rates revenue or population
- A user wants to discover Stats NZ/data.govt.nz local authority statistics datasets and resources
- A user asks how councils compare on a simple metric and official DIA profile data has a matching column
- A workflow needs JSON source URLs, formats, cadence notes, and licence caveats for local-government datasets

## Do not use this for

- Private, unpublished, authenticated, scraped-login, or embargoed council data
- Paying rates, lodging consents, submitting forms, or mutating council systems
- Claiming complete council-spending transparency or line-item expenditure coverage
- Converting PDFs into structured data unless the official source supplies machine-readable rows
- Legal, audit, or financial advice; cite source caveats and point users to official records

## Preferred workflow

1. Run `scripts/cli.py datasets --json` to discover source catalogues and key official resources.
2. Run `scripts/cli.py downloads --json` to enumerate DIA Local Councils CSV/XLSX/PDF downloads.
3. Run `scripts/cli.py performance-metrics --json` for a small DIA council profile data preview.
4. Run `scripts/cli.py councils --json` when you need council names, DIA profile group codes, and source identifiers.
5. Run `scripts/cli.py local-authority-stats --query <topic> --json` for Stats NZ/data.govt.nz local-authority dataset discovery.
6. Use `compare` only for simple comparisons against columns present in the DIA performance workbook.
7. Always include source URLs, date/cadence notes, format/licence caveats, and any fetch errors in user-facing summaries.

## CLI

Run with:

```bash
python3 skills/nz-local-government-data/scripts/cli.py <command> [flags]
```

## Commands

- `datasets [--limit N] [--json]` - list official source catalogues plus discovered data.govt.nz datasets and DIA resource previews
- `downloads [--format CSV|XLSX|PDF] [--limit N] [--json]` - enumerate downloadable resources from the DIA Local Councils index
- `performance-metrics [--council TEXT] [--limit N] [--json]` - preview the DIA council profiles XLSX data release
- `councils [--query TEXT] [--json]` - list councils and DIA profile group codes/types from the performance data release
- `local-authority-stats [--council NAME] [--query TEXT] [--limit N] [--preview N] [--json]` - discover Stats NZ/data.govt.nz local-authority datasets and preview the first machine-readable resource when possible
- `compare --metric METRIC --councils A,B [--json]` - compare a simple DIA profile metric across council name fragments

Examples:

```bash
python3 skills/nz-local-government-data/scripts/cli.py datasets --json
python3 skills/nz-local-government-data/scripts/cli.py downloads --format CSV --json
python3 skills/nz-local-government-data/scripts/cli.py councils --query Auckland --json
python3 skills/nz-local-government-data/scripts/cli.py performance-metrics --council Wellington --json
python3 skills/nz-local-government-data/scripts/cli.py local-authority-stats --council Auckland --json
python3 skills/nz-local-government-data/scripts/cli.py compare --metric rates --councils Auckland,Wellington --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/source-notes.md`

## Notes

- The CLI is read-only and uses Python standard library modules only (`urllib`, `html.parser`, `csv`, `zipfile`, `xml.etree.ElementTree`, `argparse`, and `json`).
- The DIA performance metrics workbook is parsed directly from XLSX XML using stdlib code so no Excel dependency is required.
- The legacy `localcouncils.govt.nz` HTTPS endpoint may fail with TLS/SNI errors; the CLI records this and falls back to the public HTTP endpoint.
- The issue's Stats NZ group URL is retained in outputs, but live CKAN discovery uses the current data.govt.nz `Local and regional government` group plus local-authority search terms when the older group slug is unavailable.
- OAG insight pages are listed as official context; automated HTTP may receive 403, and the skill does not invent structured rows from narrative report pages.
