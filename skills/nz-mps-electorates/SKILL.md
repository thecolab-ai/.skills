---
name: nz-mps-electorates
description: "Query official current New Zealand MP, electorate, party, portfolio, role, committee and public office contact records."
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
  thecolab.source_url: "https://www3.parliament.nz/en/mps-and-electorates/members-of-parliament/"
  thecolab.allowed_domains: "www3.parliament.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Mps Electorates

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list current MP directory resources
python3 scripts/cli.py list --json
# find an MP
python3 scripts/cli.py mp NAME --json
# find an electorate
python3 scripts/cli.py electorate NAME --json
# filter by party
python3 scripts/cli.py party NAME --json
# search portfolios and roles
python3 scripts/cli.py portfolio QUERY --json
# search committee membership
python3 scripts/cli.py committee NAME --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Return official public office contact channels only.
- Do not infer voting position, ideology or availability from directory metadata.
- Current roles can change; use the retrieval timestamp.

The CLI parses Parliament's current member table into name, party, electorate/list status and
canonical profile URL. `mp` follows matching profiles for current roles and official Parliament
email addresses. `portfolio` and `committee` inspect labelled current-role tables on official
profiles and return only matching current MPs. This source does not provide historical coverage.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/members.html` and `profile.html` — representative Parliament fixtures
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
