---
name: nz-consultations
description: "List open New Zealand central-government consultations, agencies, topics, deadlines and official submission links. Read-only; does not submit responses."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "New Zealand Government"
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
  thecolab.source_url: "https://www.govt.nz/browse/engaging-with-government/consultations-have-your-say/consultations-listing/"
  thecolab.allowed_domains: "www.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Consultations

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list open consultation resources
python3 scripts/cli.py open --json
# discover consultations closing soon
python3 scripts/cli.py closing-soon --days VALUE --json
# filter by agency
python3 scripts/cli.py agency NAME --json
# filter by topic
python3 scripts/cli.py topic QUERY --json
# find a consultation identifier
python3 scripts/cli.py consultation ID --json
# discover recently closed consultations
python3 scripts/cli.py recently-closed --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- This connector does not submit consultation responses.
- Verify exact timezone and closing time in the linked consultation.
- The cross-government listing is not necessarily exhaustive.

The CLI parses the server-rendered official listing into consultation title, agency, status,
summary, opening and closing dates, and the agency's canonical consultation link. When a distinct
submission or survey URL is published it is retained separately as `submission_url`, never confused
with `detail_url`. The listing publishes dates rather than exact deadline times, so the linked page remains authoritative.
Parser failure is an explicit schema error, never an empty success.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/consultations.html` — representative official-listing fixture
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
