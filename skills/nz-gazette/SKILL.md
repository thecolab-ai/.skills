---
name: nz-gazette
description: "Search and retrieve authoritative New Zealand Gazette notices by keyword, identifier, date, category and legislation. Retrieval only; not legal advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "New Zealand Gazette"
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
  thecolab.source_url: "https://gazette.govt.nz/"
  thecolab.allowed_domains: "gazette.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Gazette

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search official notices
python3 scripts/cli.py search QUERY --json
# list latest notice resources
python3 scripts/cli.py latest --json
# find a Gazette notice identifier
python3 scripts/cli.py notice ID --json
# search notices under named legislation
python3 scripts/cli.py under-act ACT_NAME --json
# filter notice category
python3 scripts/cli.py category NAME --json
# discover notices in an inclusive ISO date range
python3 scripts/cli.py date --from YYYY-MM-DD --to YYYY-MM-DD --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.
Malformed or reversed date ranges fail as invalid input before any source request.

## Coverage and interpretation

- Notice retrieval is not legal advice and does not determine legal effect.
- Check linked amendments, revocations and corrections.
- Return only personal detail necessary to identify the official notice.

The CLI reads the Gazette's server-rendered official search surface and returns canonical notice/search links. Gazette IDs, dates, notice types and legislation remain tied to the linked official notice; this connector does not determine legal effect.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/search.html` and `notice.html` — deterministic official-schema fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
