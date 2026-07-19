---
name: statsnz-building-consents
description: "Query official Stats NZ building-consent counts, values and floor area by region, building type and period with revision context."
license: MIT
compatibility: "Requires Python 3.10+, openpyxl, and network access for live data"
metadata:
  thecolab.category: "housing"
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
  thecolab.source_url: "https://datainfoplus.stats.govt.nz/item/nz.govt.stats/ee083b32-8c10-4ccf-b1ee-a4990b27273c"
  thecolab.allowed_domains: "datainfoplus.stats.govt.nz,stats.govt.nz,www.stats.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Statsnz Building Consents

Use the read-only Python CLI to retrieve embedded release series and workbook tables from Stats NZ.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# show latest release resources
python3 scripts/cli.py latest --json
# filter by geography
python3 scripts/cli.py region NAME --json
# filter by building type
python3 scripts/cli.py type NAME --json
# retrieve a date-range time series
python3 scripts/cli.py timeseries --from 2025-01 --to 2026-05 --json
# retrieve published national value measures
python3 scripts/cli.py value --region "New Zealand" --json
# compare the latest published regional dwelling counts
python3 scripts/cli.py compare-regions --json
# show measure, classification and revision definitions
python3 scripts/cli.py definitions --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Consents are intentions or authorisations, not completed buildings.
- Keep residential units, buildings, alterations and non-residential measures distinct.
- Preserve revised series and geography-boundary context.

The current information release exposes monthly actual, seasonally adjusted and trend series plus regional comparison tables as embedded CSV. Its linked workbook supplies annual national count, value and floor-area series with Stats NZ series references. Regional release tables cover new-dwelling counts; the workbook's value and floor-area tables are national, so non-national `value` requests fail explicitly rather than implying unsupported coverage.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/release.html` — deterministic first-party release metadata and graph fixture
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
