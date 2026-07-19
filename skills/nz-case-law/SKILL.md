---
name: nz-case-law
description: "Search publicly available official New Zealand judgments by citation, court, party, judge, date and subject. Retrieval only; coverage is not exhaustive and this is not legal advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "legal"
  thecolab.source_owner: "Courts of New Zealand"
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
  thecolab.source_url: "https://www.courtsofnz.govt.nz/judgments"
  thecolab.allowed_domains: "www.courtsofnz.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Case Law

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search published judgments
python3 scripts/cli.py search QUERY --json
# find a neutral citation
python3 scripts/cli.py citation CITATION --json
# filter by court code
python3 scripts/cli.py court CODE --json
# filter by judge
python3 scripts/cli.py judge NAME --json
# discover recent judgments
python3 scripts/cli.py recent --court VALUE --json
# find a judgment identifier
python3 scripts/cli.py judgment ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Retrieval only: not legal advice or outcome prediction.
- Coverage is not exhaustive and varies by court and publication date.
- Respect suppression orders, statutory restrictions and source redactions.
- The connector does not bypass portal or bulk-access controls.

The CLI parses official Courts judgment cards and preserves neutral citation, court, date, judge
where published, summary and PDF provenance. Court sources fail independently, and valid zero-result
searches return empty success. Coverage limits are explicit on each record.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/judgments.html` — deterministic official judgment-card fixture
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
