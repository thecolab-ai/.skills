---
name: treasury-fiscal-data-nz
description: "Query official New Zealand Treasury fiscal forecast, appropriation, Crown revenue, expenditure and debt resources with publication provenance."
license: MIT
compatibility: "Requires Python 3.10+, openpyxl, and network access for live data"
metadata:
  thecolab.category: "economics"
  thecolab.source_owner: "New Zealand Treasury"
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
  thecolab.source_url: "https://www.treasury.govt.nz/publications/budgets/forecasts"
  thecolab.allowed_domains: "www.treasury.govt.nz,treasury.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Treasury Fiscal Data NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# discover latest fiscal publications
python3 scripts/cli.py latest --json
# search forecast indicators
python3 scripts/cli.py forecast INDICATOR --json
# search appropriations
python3 scripts/cli.py appropriation QUERY --json
# filter by Vote
python3 scripts/cli.py vote NAME --json
# compare exact shared key-indicator forecasts across two publication vintages
python3 scripts/cli.py compare --from VALUE --to VALUE --json
# discover fiscal model resources
python3 scripts/cli.py fiscal-model --json
# list official source publications and workbooks
python3 scripts/cli.py sources --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Do not compare measures whose definitions changed between publications.
- Keep actuals, forecasts, scenarios and policy assumptions distinct.
- Fiscal data retrieval is not financial or investment advice.

`latest` returns primary EFU releases in the official catalogue's newest-first order, while `sources`
adds each release's official downloadable workbooks and documents. `forecast` returns one structured
Table 1 value per period. `appropriation` and `vote` return one structured amount per financial year
from the expenditure workbook's Raw Data sheet; Vote names accept either `Health` or `Vote Health`.
Every value includes its published unit, period, actual/forecast status, publication, workbook,
worksheet and exact cell provenance.

`compare` resolves two
primary EFU releases, selects each release's unique Charts and Data workbook, and compares only exact
shared Table 1 definitions, units, period basis and forecast periods. Every value retains publication,
workbook, worksheet, row, column and cell provenance. Changed or ambiguous definitions fail closed.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/publication.html` — deterministic official resource fixture; workbook rows are generated in-memory by the smoke test
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
