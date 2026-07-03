---
name: energy-hardship-nz
description: Query New Zealand energy hardship data — MBIE's Report on Energy Hardship Measures workbook, Stats NZ Household Economic Survey (HES) electricity/domestic-fuel expenditure burden by income decile or quintile, and Electricity Authority EMI domestic disconnection-for-non-payment counts. Use for questions about NZ energy poverty, electricity affordability, households unable to pay power bills, energy spend as a share of income, or disconnection trends. No login or API key required.
---

# Energy Hardship NZ

## Overview

Read-only CLI over three public New Zealand energy-hardship sources:

- **MBIE's "Report on Energy Hardship Measures"** — an Excel-only workbook
  published on mbie.govt.nz with no CSV sibling. Parsed by hand with stdlib
  `zipfile` + `xml.etree` (an `.xlsx` is a zip of XML).
- **Stats NZ Household Economic Survey (HES)** household expenditure
  statistics, distributed on **data.govt.nz** via the public CKAN API —
  electricity/domestic-fuel spend as a share of income or expenditure.
- **Electricity Authority EMI** "Disconnections for Non-Payment" dataset —
  domestic disconnection counts.

No login, API key, browser automation, or data mutation. Python standard
library only.

## When to Use

- "What are MBIE's latest energy hardship measures?"
- "How much of household income goes on electricity, by income decile?"
- "How many households were disconnected for non-payment last year?"
- Any NZ energy poverty / power-bill affordability / electricity-burden lookup.

Not for: retail electricity plan comparisons, wholesale spot prices, or grid
demand — see `nz-electricity` for those. Not for general housing/material
hardship without an energy angle — see `household-hardship-nz`.

## Commands

All commands are run via `scripts/cli.py` and accept `--json` for machine
output.

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `datasets` | List the three underlying sources and whether each is currently reachable | |
| `measures` | MBIE's energy hardship measures from the published workbook | `--year-ended YYYY` |
| `burden` | HES electricity/domestic-fuel spend as a share of income | `--breakdown income-decile\|income-quintile`, `--year YYYY` |
| `disconnections` | EMI domestic disconnections for non-payment | `--from YYYY-MM`, `--to YYYY-MM` |

## Examples

```bash
# Check which sources are reachable right now
python3 scripts/cli.py datasets --json

# MBIE's energy hardship measures workbook, filtered for year ended 2024
python3 scripts/cli.py measures --year-ended 2024 --json

# Electricity spend as a share of income, by income decile, for 2023
python3 scripts/cli.py burden --breakdown income-decile --year 2023 --json

# Disconnections for non-payment across a date range
python3 scripts/cli.py disconnections --from 2024-01 --to 2024-06 --json
```

## Notes

- The MBIE workbook and EMI dataset each ship as a single release with no
  guaranteed stable filename or column layout from year to year. Every
  command degrades to a flagged raw/partial result (with a `note` field)
  instead of crashing when a specific column or year can't be matched —
  always check `note` in the JSON output before trusting a filtered result.
- `burden` and `datasets` discover the current HES dataset via CKAN
  `package_search` rather than a hardcoded dataset id, so they keep working
  as Stats NZ publishes new HES releases.
- Source/endpoint detail is in [references/api-notes.md](references/api-notes.md).
- Run `python3 scripts/smoke_test.py` to verify the live data path; it skips
  (rather than fails) on upstream network errors.
