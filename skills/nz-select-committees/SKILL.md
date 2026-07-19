---
name: nz-select-committees
description: "Track official New Zealand select committees, open submissions, business, public evidence and reports. Read-only; does not submit on a user's behalf."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "New Zealand Parliament"
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
  thecolab.source_url: "https://www3.parliament.nz/en/pb/sc/"
  thecolab.allowed_domains: "www3.parliament.nz, www.parliament.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Select Committees

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list current committee resources
python3 scripts/cli.py committees --json
# list open submission resources
python3 scripts/cli.py open-submissions --json
# discover submissions closing soon
python3 scripts/cli.py closing-soon --days VALUE --json
# discover committee business
python3 scripts/cli.py business --committee VALUE --json
# discover public evidence
python3 scripts/cli.py evidence ITEM_ID --json
# discover reports since an ISO date
python3 scripts/cli.py reports --since YYYY-MM-DD --json
# find a committee item
python3 scripts/cli.py item ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.
Malformed `--since` values fail as invalid input before any Parliament request.

## Coverage and interpretation

- This connector does not submit on a user's behalf or operate Parliament accounts.
- Verify exact closing time and timezone in the linked item.
- Public evidence may contain personal information; retain official context.

The CLI reads Parliament's server-rendered select-committee index, including official committee, open-submission, business, evidence and report links. It accepts only source-specific record paths and never treats navigation links as records. Deadline values must be verified in the linked item; the connector never submits or operates an account.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/open.html` and `detail.html` — deadline, membership and evidence fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
