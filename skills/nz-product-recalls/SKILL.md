---
name: nz-product-recalls
description: "Search official Product Safety New Zealand non-food consumer-product recalls by product, supplier, category, hazard and date."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "safety"
  thecolab.source_owner: "Product Safety New Zealand"
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
  thecolab.source_url: "https://www.productsafety.govt.nz/recalls"
  thecolab.allowed_domains: "www.productsafety.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Product Recalls

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list latest recall notices
python3 scripts/cli.py latest --json
# list active recall notices
python3 scripts/cli.py active --json
# search products, models, brands or suppliers
python3 scripts/cli.py search QUERY --json
# filter by supplier
python3 scripts/cli.py supplier NAME --json
# filter by category
python3 scripts/cli.py category NAME --json
# filter by hazard
python3 scripts/cli.py hazard QUERY --json
# find a recall identifier
python3 scripts/cli.py recall ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Do not infer coverage beyond official model, batch and date identifiers.
- Keep remedy language faithful to the official notice.
- This connector does not contact suppliers or submit claims.

The CLI parses Product Safety New Zealand's server-rendered recall articles (date, title, categories and canonical detail URL). Exact recall lookup parses official product identifiers, supplier, responsible agency, hazard and remedy sections without broadening their stated scope.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/product-recalls.html` and `product-recall-detail.html` — list/detail fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
