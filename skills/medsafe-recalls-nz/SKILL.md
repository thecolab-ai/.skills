---
name: medsafe-recalls-nz
description: "Search official Medsafe medicine and medical-device recalls and safety communications. Use for product, batch, hazard and action retrieval; not medical advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "health"
  thecolab.source_owner: "Medsafe"
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
  thecolab.source_url: "https://www.medsafe.govt.nz/hot/Recalls/RecallSearch.asp"
  thecolab.allowed_domains: "www.medsafe.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Medsafe Recalls NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list latest recall and safety resources
python3 scripts/cli.py latest --json
# search official notices
python3 scripts/cli.py search QUERY --json
# search medicine recalls
python3 scripts/cli.py medicine NAME --json
# search medical-device recalls
python3 scripts/cli.py device NAME --json
# find a recall identifier
python3 scripts/cli.py recall ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Recall retrieval is not medical advice.
- Do not stop a medicine without professional guidance unless the official notice explicitly directs it.
- Preserve exact batch or lot scope and distinguish recalls from safety communications.

The CLI submits Medsafe's public read-only search form and parses its server-rendered recall table. Exact lookup parses the labelled official detail table, including product type, reference, brand, model, affected batch/model/software scope, recalling organisation, manufacturer, issue, action, level and commencement date when published.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/recalls.html` and `recall-detail.html` — list/detail and no-result parser fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
