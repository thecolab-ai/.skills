---
name: stats-nz-census
description: "Query official public 2018 Stats NZ Census national-highlights CSV tables while preserving dimensions and suppression/status markers. No API key required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
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
  thecolab.source_url: "https://www.stats.govt.nz/assets/Uploads/2018-Census-totals-by-topic-national-highlights-csv-update-30-04-20.zip"
  thecolab.allowed_domains: "www.stats.govt.nz"
  thecolab.last_verified: "2026-09-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Stats NZ Census

Query the official **2018 Census totals by topic – national highlights** CSV archive. This is a narrow, standalone public aggregate-data connector; it does not use authenticated Stats NZ surfaces or Census microdata.

## Use this when

- A user needs a published 2018 Census national-highlight count by topic/category.
- You need to discover the topic tables in the official CSV download.
- Another tool needs bounded JSON that retains the table's dimensions and source markers.

## Do not use this for

- 2023 Census observations, subnational tables, meshblock data, or time-series comparisons.
- Restricted/confidentialised unit records or authenticated Stats NZ surfaces.
- Estimation, interpolation, de-rounding, cross-tabulation, or joining unlike dimensions.

No 2023 values are implied: the public 2023 product finder is metadata, while detailed API access may require a subscription key.

## CLI

```bash
# List available topic tables (the positional topic is optional)
python3 skills/stats-nz-census/scripts/cli.py --json

# Query the common positional topic path
python3 skills/stats-nz-census/scripts/cli.py age-single-years --limit 10 --json
python3 skills/stats-nz-census/scripts/cli.py ethnic-group-total-responses --category european --json
python3 skills/stats-nz-census/scripts/cli.py age-single-years --measure Census_usually_resident --json
```

Arguments:

- `[TOPIC]`: case-insensitive substring of a published CSV member/topic slug. Omit it to list topics.
- `--category TEXT`: filter category code or label without changing either dimension.
- `--measure TEXT`: filter a published measure heading.
- `--limit N`: return 1–100 observations (default 20).
- `--json`: emit the repository result envelope; otherwise print concise text.

An unmatched topic or filter is a successful empty result with a warning. Source/schema failures are never reported as empty data.

## Data rules

- Preserve `category_dimension`, `category_code`, `category_label`, and `measure` separately.
- Preserve `raw_value`, `value_status`, and `source_symbol`; suppression/confidentiality/missing markers remain `value: null` and are never changed to zero.
- Retain the source member and source row for traceability.
- Treat figures as published, rounded national aggregate counts; do not infer hidden values.
- Attribute reported figures to Stats NZ and include the source URL.

Read `references/source-notes.md` for scope and status-marker details. Parser fixtures are in `tests/fixtures/`. Run `scripts/test_contract.py` and `scripts/smoke_test.py` after changes.
