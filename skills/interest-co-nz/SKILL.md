---
name: interest-co-nz
description: "Query interest.co.nz public mortgage-rate tables through a lightweight no-login HTML parser. Use when the task involves current New Zealand mortgage rates, bank home-loan rates, variable/floating rates, fixed terms from 6 months to 5 years, special LVR rows, or comparing advertised mortgage rates across NZ lenders. Read-only; no application, lead, login, or quote submission."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "finance"
  thecolab.source_owner: "interest.co.nz"
  thecolab.source_type: "commercial"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-commercial-web"
  thecolab.source_url: "https://www.interest.co.nz/borrowing"
  thecolab.allowed_domains: "www.interest.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# interest.co.nz Mortgage Rates

## Goal

Extract current NZ mortgage-rate table rows from interest.co.nz public pages into concise text or normalized JSON.

## CLI

```bash
python3 skills/interest-co-nz/scripts/cli.py mortgage-rates --limit 20
python3 skills/interest-co-nz/scripts/cli.py mortgage-rates --bank Westpac --json
python3 skills/interest-co-nz/scripts/cli.py mortgage-rates --specials-only
```

Commands:

- `mortgage-rates [--bank NAME] [--product TEXT] [--specials-only] [--limit N] [--json]`

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`
