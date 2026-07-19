---
name: household-hardship-nz
description: "Query New Zealand household material hardship, child and family poverty, income adequacy, housing affordability and rent burden, low-income household counts, and the Gini coefficient of income inequality from the Stats NZ Household Economic Survey \"Household Wellbeing\" release on data.govt.nz. Use for questions about NZ deprivation, cost-of-living stress, who is struggling to afford housing, hardship by region or ethnicity (including Maori households), or income inequality figures with confidence intervals."
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
  thecolab.source_url: "https://catalogue.data.govt.nz/api/3/action"
  thecolab.allowed_domains: "catalogue.data.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Household Hardship NZ

## Overview

Read-only CLI over the **Stats NZ Household Economic Survey (HES) "Household
Wellbeing"** release, distributed on **data.govt.nz** through the public CKAN
API. No login, API key, or browser needed. Each dataset ships as a ZIP-of-CSV
that the CLI unpacks with the Python standard library only.

It answers questions like material hardship counts, income adequacy, housing
affordability (housing cost as a share of income), low-income household numbers,
and income inequality (Gini) — broken down **by region or by ethnicity**
(including Maori households), each with 95% confidence intervals (LCI/UCI) and
relative standard error.

## When to Use

- "How many households are in material hardship in Auckland?"
- "Compare housing affordability stress across ethnicities."
- "Which regions have the worst income adequacy?"
- "Show the Gini coefficient of income inequality by region."
- "How many low-income households spend over 40% of income on housing?"
- Any NZ deprivation / cost-of-living / housing-cost-burden / inequality lookup.

Not for: live benefit caseloads, the public housing register, or building-level
deprivation indexes — those live in other sources.

## Commands

All commands are run via `scripts/cli.py` and accept `--json` for machine output.
Most accept `--dataset <ckan-id>` to target a different HES release (default is
the 2020-2021 wellbeing release).

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `search <query>` | Search data.govt.nz for HES wellbeing/hardship datasets | `--limit` |
| `datasets` | List available HES Household Wellbeing releases | |
| `hardship` | Material hardship household counts | `--region`, `--ethnicity [name]` |
| `income-adequacy` | Income adequate vs not adequate | `--region`, `--ethnicity [name]` |
| `affordability` | Households spending over 30/40/50 percent of income on housing | `--region`, `--ethnicity [name]`, `--tenure [name]`, `--threshold`, `--lowincome` |
| `low-income` | Low-income household counts (after housing costs) | `--region`, `--ethnicity [name]` |
| `gini` | Gini coefficient of income inequality | `--region`, `--ethnicity [name]` |

`--ethnicity` and `--tenure` take an optional value: bare `--ethnicity` returns
all groups; `--ethnicity European` filters to one. Without `--ethnicity` or
`--tenure`, breakdowns are by region (optionally filtered with `--region auckland`).
`--threshold` accepts `30`, `40`, or `50`.

## Examples

```bash
# Material hardship households in Auckland with confidence intervals
python3 scripts/cli.py hardship --region auckland

# Material hardship by ethnicity, as JSON
python3 scripts/cli.py hardship --ethnicity --json

# Low-income households spending over 30% of income on housing, by ethnicity
python3 scripts/cli.py affordability --ethnicity --threshold 30 --lowincome --json

# Income adequacy across all regions
python3 scripts/cli.py income-adequacy

# Gini coefficient of income inequality by region
python3 scripts/cli.py gini

# Find other HES wellbeing releases (e.g. 2018-19, "Warm and Dry")
python3 scripts/cli.py search "warm and dry"
python3 scripts/cli.py datasets
```

## Notes

- Source: Stats NZ HES Household Wellbeing, via the data.govt.nz CKAN API. The
  default dataset is `household-economic-survey-2020-2021-household-wellbeing-including-maori-households`.
- All counts are survey estimates with sampling error: `lci`/`uci` are the 95%
  confidence bounds and `rse_percent` the relative standard error. A `flag` of
  `*` marks estimates Stats NZ flags as having high sampling error.
- Region and ethnicity names are matched loosely (case/punctuation-insensitive),
  so `auckland`, `hawkes bay`, and `Maori` all work.
- Endpoint detail, table names, and column meanings are in
  [references/api-notes.md](references/api-notes.md).
- Run `python3 scripts/smoke_test.py` to verify the live data path.
