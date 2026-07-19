---
name: nz-police-data
description: "Query official anonymised New Zealand Police victimisation, proceedings and offence statistics with suppression and interpretation context."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-safety"
  thecolab.source_owner: "New Zealand Police"
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
  thecolab.source_url: "https://www.police.govt.nz/about-us/publications-statistics/data-and-statistics/policedatanz"
  thecolab.allowed_domains: "www.police.govt.nz,police.govt.nz,public.tableau.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Police Data

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# discover victimisation statistics
python3 scripts/cli.py victimisations --json
# discover offender proceeding statistics
python3 scripts/cli.py proceedings --json
# discover offence trends
python3 scripts/cli.py trend --offence VALUE --json
# filter resources by area
python3 scripts/cli.py area NAME --json
# discover supported demographic dimensions
python3 scripts/cli.py demographics --measure VALUE --json
# show source definitions and interpretation resources
python3 scripts/cli.py definitions --json
# list official datasets and workbooks
python3 scripts/cli.py datasets --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- All suppression, rounding and small-cell rules must be preserved.
- Recorded crime is not a direct measure of total underlying crime prevalence.
- Do not produce person-level, address-level, profiling or predictive-policing output.
- Geographic comparisons require population, base-rate and boundary context.

The CLI parses the official Police report catalogue and exact Tableau workbook references. Because no stable documented row API is published, it explicitly returns report/filter descriptors rather than manufacturing statistical rows.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/catalog.html` and `report.html` — deterministic official catalogue/embed fixtures
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
