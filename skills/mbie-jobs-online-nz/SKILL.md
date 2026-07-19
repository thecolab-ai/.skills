---
name: mbie-jobs-online-nz
description: "Query official MBIE Jobs Online advertised-vacancy trends by occupation, industry, region and skill level with methodology context."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "employment"
  thecolab.source_owner: "Ministry of Business, Innovation and Employment"
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
  thecolab.source_url: "https://www.mbie.govt.nz/business-and-employment/employment-and-skills/labour-market-reports-data-and-analysis/jobs-online"
  thecolab.allowed_domains: "www.mbie.govt.nz,mbie.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# MBIE Jobs Online NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# show latest headline resources
python3 scripts/cli.py latest --json
# filter by occupation
python3 scripts/cli.py occupation QUERY --json
# filter by industry
python3 scripts/cli.py industry NAME --json
# filter by region
python3 scripts/cli.py region NAME --json
# filter by skill level
python3 scripts/cli.py skill-level NUMBER --json
# discover an inclusive ISO date-range trend
python3 scripts/cli.py trend --from YYYY-MM-DD --to YYYY-MM-DD --json
# show methodology and series definitions
python3 scripts/cli.py definitions --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.
Malformed or reversed trend ranges fail as invalid input before the workbook download.

## Coverage and interpretation

- Advertised vacancies are not employment, hiring or unique job openings.
- Preserve index, seasonal-adjustment, revision and methodology context.
- Do not merge with job-listing counts unless definitions and deduplication are explicit.

The CLI parses MBIE's consolidated unadjusted quarterly CSV and returns actual AVI rows by geography and series. Every row retains export provenance and methodology warnings.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/jobs.csv` — deterministic official CSV-schema fixture
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
