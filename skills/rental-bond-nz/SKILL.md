---
name: rental-bond-nz
description: Query MBIE/Tenancy Services NZ rental bond and market-rent statistics, including quarterly/monthly bonded-tenancy counts, median and quartile rent values, and market-rent snapshots by suburb, property type, and bedroom size. Use for rent affordability analysis, tenure trending, and housing policy workflows. Data is keyless and sourced from tenancy.govt.nz first-party endpoints with data.govt.nz CKAN metadata fallback where relevant.
---

# Rental Bond NZ

## Overview

Read-only CLI wrapper for Ministry of Business, Innovation and Employment (MBIE) / Tenancy Services rental bond and market-rent data.

This skill covers:

- Discoverable public MBIE/Tenancy rental-bond CSV releases (monthly by regional/territorial area and detailed quarterly)
- Market-rent endpoint for suburb-level current-range rent snapshots (active bonds, lower/median/upper quartiles)
- Automatic CKAN mirror discovery for dataset metadata and alternate discovery paths

No authentication, no API key, and no browser automation required for this skill.

## When to Use

- A task asks for NZ rental bond activity (lodged, active, closed bonds) over time by area
- A task asks for market-rent snapshots by location, property type, and bedroom size
- A task needs direct links and metadata for the MBIE/Tenancy public release files and CKAN records
- Another workflow needs machine-readable housing-rent trend data for policy/research automation

## Commands

Run with:

```bash
python3 skills/rental-bond-nz/scripts/cli.py <command> [flags]
```

- `datasets [--query Q] [--limit N] [--json]` - discover Tenancy bond and related datasets via `tenancy.govt.nz` links and `data.govt.nz` package search
- `bonds [--from YYYY-MM] [--to YYYY-MM] [--area NAME] [--scope tla|region] [--limit N] [--json]` - monthly bonded-tenancy rows filtered by period and area
- `areas [--query Q] [--city CITY] [--limit N] [--json]` - discover market-rent city/suburb values from the Tenancy autosuggest endpoint
- `market-rent --area NAME [--city CITY] [--suburb SUBURB] [--property-type PROPERTY] [--bedrooms N|N+] [--period YYYY-MM] [--json]` - fetch market-rent rows for a location/property combination

### Examples

```bash
python3 skills/rental-bond-nz/scripts/cli.py datasets --json
python3 skills/rental-bond-nz/scripts/cli.py bonds --from 2025-01 --to 2026-06 --area "Auckland City" --scope tla --json
python3 skills/rental-bond-nz/scripts/cli.py areas --query Auckland --json
python3 skills/rental-bond-nz/scripts/cli.py market-rent --city Auckland --suburb Avondale --period 2025-10 --property-type apartment --json
python3 skills/rental-bond-nz/scripts/cli.py market-rent --area "Auckland - Avondale" --bedrooms "2" --json
```

## Notes and caveats

- Market rent output is a six-month window (for the current/latest period returned by the tenancy endpoint), not a single reference date.
- Bond datasets are rounded and privacy-suppressed by source, consistent with MBIE/Tenancy's public methodology.
- Market-rent and release metadata are hosted on tenancy.govt.nz; CKAN package data is used for discoverability and fallback metadata only.
- If upstream pages or endpoints are temporarily blocked, the command returns `upstream_unavailable` for structured handling.

## Resources

- `scripts/cli.py`
- `references/api-notes.md`
- `scripts/smoke_test.py`
