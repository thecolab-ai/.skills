---
name: child-poverty-nz
description: "Query official New Zealand child poverty statistics from Stats NZ — the nine Child Poverty Reduction Act measures (BHC/AHC low-income lines, material hardship, severe material hardship, DEP-17 deprivation), national rates and child numbers 2007-2025 with confidence intervals, and breakdowns by region, ethnicity (Māori, Pacific, European, Asian) and disability. Use for tasks about NZ child poverty rates, kids in hardship or deprivation, poverty by region or ethnic group, annual change, or finding the latest Stats NZ child-poverty release."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "social-policy"
  thecolab.source_owner: "Stats NZ"
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
  thecolab.source_url: "https://www.stats.govt.nz"
  thecolab.allowed_domains: "www.stats.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Child Poverty NZ

## Overview

Read-only CLI over Stats NZ's annual Child Poverty Reduction Act (CPRA) data
releases. Each release is a public ZIP of UTF-8 CSVs (no API key, no login, no
bot challenge). The CLI auto-discovers the latest release from the Stats NZ
CSV-files index, downloads the ZIP in memory, and parses the national and
disaggregated data files with the Python standard library only.

The nine measures use codes `MEASA`–`MEASJ` (Stats NZ skips `MEASD`). The three
**primary** legislated measures are `MEASA` (income below 50% of the median
before housing costs, moving line), `MEASB` (below 50% after housing costs,
anchored line) and `MEASC` (**material hardship**, DEP-17, lacking 6+ of 17
items). `MEASI` is **severe** material hardship (lacking 9+ items) — a subset of
`MEASC` — and `MEASJ` is the combined low-income-and-hardship measure.

## When to Use

Use this when the task involves:
- NZ child poverty rates, child numbers, or annual change for any CPRA measure
- material hardship / severe hardship / DEP-17 deprivation among children
- poverty broken down by region, ethnicity (Māori, Pacific, European, Asian), or disability
- a time series of child-poverty rates for charting (2007-2025 national; 2019-2025 disaggregated)
- finding the latest Stats NZ child-poverty release ZIP

Do not use this for: household-income/housing-cost statistics, benefit payment
records, the public housing register, or non-NZ poverty data.

## Commands

Run with `python3 scripts/cli.py <command>`. Every command supports `--json`.

- `measures [--json]` — list the nine CPRA measure codes with plain-English names.
- `national --measure CODE [--year Y] [--from Y] [--to Y] [--json]` — proportion (%), number (000s), annual change and child population for a measure, with confidence intervals. Defaults to `MEASA`, full 2007-2025 range.
- `latest [--json]` — the most recent year's headline proportion + CI for all nine measures.
- `breakdown --measure CODE --by region|ethnicity|disability [--year Y] [--json]` — disaggregated proportion/number across the demographic codes (2019-2025).
- `trend --measure CODE [--demographic CODE] [--json]` — full time series for charting; pass a demographic code (e.g. `REGC02`, `ETHG02`, `DISD01`) for a disaggregated series.
- `releases [--json]` — scrape the Stats NZ CSV-files index to list available child-poverty releases and their ZIP URLs.

Errors print to stderr and exit non-zero.

## Examples

```bash
# Headline picture for the latest year, all nine measures
python3 scripts/cli.py latest --json

# Primary measure (BHC<50%) national trend, last three years
python3 scripts/cli.py national --measure MEASA --from 2023 --to 2025

# Material hardship among children by disability status
python3 scripts/cli.py breakdown --measure MEASC --by disability --json

# Child poverty by ethnicity for the primary measure
python3 scripts/cli.py breakdown --measure MEASA --by ethnicity

# Māori child poverty time series for charting
python3 scripts/cli.py trend --measure MEASA --demographic ETHG02 --json

# Discover the latest release ZIP
python3 scripts/cli.py releases --json
```

## Notes

- Estimates carry sampling error; always surface the confidence interval (`*_lower_ci` / `*_upper_ci`) alongside a rate, not just the point estimate.
- Regional figures are unavailable for 2022 and regional annual change is unavailable for 2023 (2022 data-quality issues). 2025 material-hardship and disability questions changed in the transition to the Household Income and Living Survey, so disabled-children hardship is not comparable to earlier years.
- Flags: `NA` = no prior-year data (change not applicable); cells may be suppressed (`S`) for confidentiality when fewer than six units contribute.
- All commands hit the network. Run `scripts/smoke_test.py` for a live check.
- Endpoint detail, file layout, and the full code legend are in `references/api-notes.md`.
