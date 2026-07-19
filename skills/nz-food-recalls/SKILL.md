---
name: nz-food-recalls
description: "Search official MPI food recalls by product, brand, allergen, hazard, batch and date. Use for source-backed current and historical food-recall checks."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "safety"
  thecolab.source_owner: "Ministry for Primary Industries"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.mpi.govt.nz/food-safety-home/food-recalls-and-complaints/"
  thecolab.allowed_domains: "www.mpi.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Food Recalls

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list active recall resources
python3 scripts/cli.py active --json
# list latest recall resources
python3 scripts/cli.py latest --json
# search by product, retailer, hazard, batch or date
python3 scripts/cli.py search QUERY --json
# search by allergen
python3 scripts/cli.py allergen NAME --json
# search by brand
python3 scripts/cli.py brand NAME --json
# find an official recall
python3 scripts/cli.py recall ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Do not infer recall coverage outside the official batch or date range.
- Preserve the exact undeclared allergen name.
- Official consumer and emergency guidance takes precedence.

The CLI parses MPI's server-rendered yearly recalled-food lists. Exact lookup preserves the official Product information, distribution, consumer-action and contact sections so batch/date markings, allergens and advice remain scoped to the notice.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/mpi-recalls.html` and `mpi-recall-detail.html` — bounded list/detail fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
