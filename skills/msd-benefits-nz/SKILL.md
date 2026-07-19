---
name: msd-benefits-nz
description: "Query official New Zealand MSD benefit statistics - Jobseeker Support, Sole Parent Support, Supported Living Payment, Youth Payment, NZ Superannuation and Veteran's Pension recipient numbers by quarter, gender, ethnicity, age group, and Work and Income region. Use for working-age benefit numbers, main benefit counts, welfare/superannuation recipient breakdowns, and benefit trends. No API key or browser session required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "social-policy"
  thecolab.source_owner: "Ministry of Social Development"
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
  thecolab.source_url: "https://www.msd.govt.nz/documents/about-msd-and-our-work/"
  thecolab.allowed_domains: "www.msd.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# MSD Benefits NZ

## Overview

Query official Ministry of Social Development (MSD) quarterly benefit statistics through a small deterministic CLI with human-readable and JSON output, without browser automation, login, API keys, or local cache state.

This skill wires three public MSD CSV releases:

- National main-benefit recipient counts (Jobseeker Support, Sole Parent Support, Supported Living Payment, Youth Payment and Young Parent Payment, Other Main Benefits)
- NZ Superannuation and Veteran's Pension recipient counts
- Work and Income region-level main-benefit counts

Each supports breakdowns by gender, ethnicity, age group, and (region CSV) MSD service region, plus a multi-quarter trend.

**Important:** these CSVs are the **December 2019 "benefit fact sheets" release** - a frozen historical series. The latest quarter present is `Dec_19` (quarters run `Dec_14` through `Dec_19`). Treat output as a stable historical reference set, not a live current-quarter feed. See `references/api-notes.md`.

## When to Use

- A user asks for New Zealand benefit numbers, main benefit recipient counts, or welfare statistics
- A user wants Jobseeker, Sole Parent, Supported Living, Youth Payment, NZ Super, or Veteran's Pension recipient figures
- A user needs benefit recipients broken down by gender, ethnicity, age group, or Work and Income region
- A user wants a quarterly trend for a benefit group across 2014-2019
- Another tool or agent needs JSON output from official MSD benefit data

## Do not use this for

- Current-quarter or post-2019 benefit numbers (this release stops at `Dec_19`; point users to msd.govt.nz benefit fact sheets for newer data)
- Individual or identifiable case data (the source is aggregated and confidentialised)
- Child poverty / material hardship / public housing register figures (those are separate Stats NZ and HUD datasets, not in this release)
- Redistributing the extract as a standalone dataset

## Commands

Run with:

```bash
python3 skills/msd-benefits-nz/scripts/cli.py <command> [flags]
```

- `list-quarters [--csv national|nzs|region] [--json]` - distinct `Quarter` values available in a CSV
- `main-benefits [--quarter Sep_19] [--group 'Jobseeker Support'] [--gender] [--ethnicity] [--age] [--json]` - national main-benefit counts; default groups by benefit when no breakdown flag is given
- `nz-super [--quarter Sep_19] [--group ...] [--age-group] [--ethnicity] [--json]` - NZ Super / Veteran's Pension counts (age is Under 65 / 65 and over)
- `region --region 'Auckland Metro' [--quarter Sep_19] [--group ...] [--gender] [--ethnicity] [--age] [--json]` - Work and Income region breakdown
- `trend --group 'Sole Parent Support' [--gender F] [--json]` - time series of recipient `Count` across all quarters

Quarter format is `Mon_YY`, e.g. `Mar_15`, `Dec_19`. Default quarter is `Dec_19` (the latest in the release).
Region values are MSD Work and Income service regions (e.g. `Auckland Metro`, `Wellington`, `Canterbury`), **not** regional councils.

## Examples

```bash
python3 skills/msd-benefits-nz/scripts/cli.py list-quarters --csv national --json
python3 skills/msd-benefits-nz/scripts/cli.py main-benefits --quarter Sep_19 --json
python3 skills/msd-benefits-nz/scripts/cli.py main-benefits --quarter Sep_19 --group 'Jobseeker Support' --ethnicity --json
python3 skills/msd-benefits-nz/scripts/cli.py nz-super --quarter Sep_19 --age-group --json
python3 skills/msd-benefits-nz/scripts/cli.py region --region 'Auckland Metro' --quarter Sep_19 --group 'Sole Parent Support' --json
python3 skills/msd-benefits-nz/scripts/cli.py trend --group 'Sole Parent Support' --gender F --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Endpoint and schema detail: `references/api-notes.md`

## Notes

- MSD is the upstream source for all commands; cite it and include the release URL when reporting figures
- No API key, username, password, cookie, or browser session is required
- The CSVs contain `Gender suppressed`, `Ethnicity suppressed`, `Age suppressed`, and `Unspecified` categories where MSD applied confidentiality; these are summed into totals and shown as their own breakdown rows
- Default output is human-readable; every command supports `--json` for chaining into other tools
- `--group` matching is case-insensitive and accepts unique substrings; an ambiguous or unknown value lists the valid groups
