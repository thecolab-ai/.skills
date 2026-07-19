---
name: elections-nz
description: "Query official New Zealand election results, electorate voting, turnout and published finance resources from the Electoral Commission."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "Electoral Commission"
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
  thecolab.source_url: "https://elections.nz/stats-and-research/"
  thecolab.allowed_domains: "elections.nz,www.elections.nz,electionresults.govt.nz,www.electionresults.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Elections NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# discover election results
python3 scripts/cli.py results --year VALUE --json
# discover electorate results
python3 scripts/cli.py electorate NAME --year VALUE --json
# discover party-vote results
python3 scripts/cli.py party-vote --year VALUE --json
# discover turnout series
python3 scripts/cli.py turnout --year VALUE --json
# discover candidate results
python3 scripts/cli.py candidate NAME --year VALUE --json
# discover party donation returns
python3 scripts/cli.py donations --party VALUE --json
# discover candidate expense returns
python3 scripts/cli.py expenses --candidate VALUE --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Only Electoral Commission outcomes are authoritative.
- Preserve preliminary versus official status and publication date.
- Finance records retain reporting-period and disclosure-threshold context.
- Do not derive voter-level profiles or political persuasion.

Result commands parse the Commission's published CSV tables and finance commands return matching first-party return documents. It never converts a parser failure into an empty success. Follow linked primary records for definitions and reporting-period context.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/overall-results.csv`, `turnout.csv`, `winning-candidates.csv` and `finance.html` — export-specific fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
