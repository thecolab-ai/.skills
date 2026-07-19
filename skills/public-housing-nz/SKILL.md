---
name: public-housing-nz
description: "Query New Zealand public and social housing open data from the Ministry of Housing and Urban Development (HUD) on data.govt.nz — public housing stock (Kainga Ora and community housing providers), social housing IRRS and market-rent tenancies, accommodation supplement recipients and weekly spend, and the Local Housing Statistics dashboard (housing affordability, rent burden, bonds, building consents, MSD benefit numbers, and the year-on-year change in the public/social housing register). Use when the task involves NZ public housing, the social housing register or wait-list, Kainga Ora, housing deprivation, accommodation supplement, housing affordability, or HUD housing statistics. No API key, login, or browser session required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "social-policy"
  thecolab.source_owner: "Ministry of Housing and Urban Development and Stats NZ"
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
  thecolab.source_url: "https://catalogue.data.govt.nz"
  thecolab.allowed_domains: "catalogue.data.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Public Housing NZ

## Overview

Read-only stdlib CLI over the Ministry of Housing and Urban Development (HUD)
open-data releases published on data.govt.nz (CKAN at `catalogue.data.govt.nz`).
Every command supports `--json` for machine-readable output and a human-readable
default. No login, API key, browser automation, or cache state.

Covered data:

- Public housing stock by territorial authority and provider (Kainga Ora / CHP)
- Social housing tenancies (Income-Related Rent Subsidy + market rent) by TLA
- Accommodation Supplement recipients and total weekly spend by area
- Local Housing Statistics dashboard: affordability, rent burden, bonds,
  building consents, sales, census crowding, MSD figures, population, and the
  1-year change in the Housing Register
- CKAN catalogue discovery and server-side DataStore filtering

## When to Use

- A user asks about NZ public/social housing stock, Kainga Ora, or CHP homes
- A user wants social housing tenancy counts (IRRS + market rent) by district
- A user asks about the Accommodation Supplement (recipients, weekly cost)
- A user asks about housing affordability, rent burden, or the change in the
  housing register / social housing wait-list trend
- Another tool needs no-login, machine-readable HUD housing data as JSON

## Do not use this for

- The exact current Public/Social Housing Register wait-list headcount — HUD
  publishes that as XLSX/HTML, not clean CSV (see Notes); this skill exposes the
  Local Housing Statistics dashboard's *change in register* series instead
- Private, unpublished, or authenticated MSD/HUD data
- Redistributing the public extracts as a standalone dataset

## Commands

Run with:

```bash
python3 skills/public-housing-nz/scripts/cli.py <command> [flags]
```

- `datasets [--query Q] [--limit N] [--json]` - list HUD housing datasets/resources via CKAN package_search (format + last-modified)
- `public-homes [--area AREA] [--provider KO|CHP] [--date YYYY-MM-DD] [--json]` - public housing stock; defaults to the latest as-at date
- `tenancies [--area TLA] [--date YYYY-MM-DD] [--json]` - social housing (IRRS + market rent) tenancies by TLA; defaults to latest date
- `accommodation-supplement [--area AREA] [--area-type TLA] [--date YYYY-MM-DD] [--json]` - AS recipients and weekly spend; defaults to latest date
- `local-stats [--area NAME] [--theme THEME] [--series SERIES] [--year YYYY] [--limit N] [--json]` - Local Housing Statistics dashboard rows
- `series [--json]` - list the distinct series and themes available in `local-stats`
- `query --resource sochouse|publichomes|as|local [--filter k=v ...] [--q TEXT] [--limit N] [--json]` - passthrough to CKAN `datastore_search` for server-side filtering

## Examples

```bash
python3 skills/public-housing-nz/scripts/cli.py datasets --json
python3 skills/public-housing-nz/scripts/cli.py public-homes --provider KO --json
python3 skills/public-housing-nz/scripts/cli.py tenancies --area "Invercargill City" --json
python3 skills/public-housing-nz/scripts/cli.py accommodation-supplement --area Ashburton --json
python3 skills/public-housing-nz/scripts/cli.py local-stats --series "Change in Housing Register" --json
python3 skills/public-housing-nz/scripts/cli.py local-stats --area "New Zealand" --theme Affordability --year 2024 --json
python3 skills/public-housing-nz/scripts/cli.py series --json
python3 skills/public-housing-nz/scripts/cli.py query --resource sochouse --filter TLA_Name="WHANGAREI DISTRICT" --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Endpoint and dataset notes: `references/api-notes.md`

## Notes

- All data is published by the Ministry of Housing and Urban Development (HUD)
  on data.govt.nz; mention HUD as the source and include the release URL.
- No API key, username, password, cookie, or browser session is required.
- `tenancies`, `public-homes`, and `accommodation-supplement` default to the
  latest as-at date in the file when `--date` is omitted.
- Suppressed values in the public-homes file appear as `s`; the CLI reports
  these rows as `null` and counts them under `suppressed_rows`.
- The `publichomes` resource is geolocated by numeric TLA code (its
  `Area_Name` is mostly codes, plus a "Not geolocated" rollup), so use
  `--provider` and `--date`; use `tenancies` for clean TLA-name social housing
  counts.
- The actual current Public/Social Housing Register wait-list headcount is
  published by HUD as XLSX + HTML, not clean CSV, so it is intentionally not
  wired; use `local-stats --series "Change in Housing Register"` for the
  register trend, or `datasets` to discover the latest register release.
- `query` is a thin passthrough to CKAN `datastore_search`; CKAN returns dates
  as ISO datetimes (e.g. `2022-12-31T00:00:00`).
- Default output is human-readable; every command supports `--json`.
- Avoid high-volume polling; use date and area filters or the `query` passthrough.
