---
name: lawa-nz
description: "Query Land Air Water Aotearoa (LAWA) public river-quality sites, swimming sites, and river indicator summaries through no-login Umbraco JSON endpoints. Use when the task involves NZ river quality, macroinvertebrate/community index data, E. coli/nutrient indicator bands, swim-site listings, or LAWA environmental monitoring site discovery. Read-only."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Land Air Water Aotearoa"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.lawa.org.nz"
  thecolab.allowed_domains: "www.lawa.org.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# LAWA NZ

## Goal

Query public LAWA environmental monitoring site and indicator data with a deterministic read-only CLI.

## CLI

```bash
python3 skills/lawa-nz/scripts/cli.py river-sites --query waikato --json
python3 skills/lawa-nz/scripts/cli.py swim-sites --query beach --limit 10
python3 skills/lawa-nz/scripts/cli.py indicators --lawa-id ARC-00001 --json
```

Commands:

- `river-sites [--query TEXT] [--limit N] [--json]` - river-quality map sites and regions
- `swim-sites [--query TEXT] [--limit N] [--json]` - swimming site cards parsed from LAWA public response HTML
- `indicators [--lawa-id ID] [--parameter PARAM] [--limit N] [--json]` - river indicator summaries from LAWA public JSON

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

LAWA endpoints are public/read-only but not a formal published API contract; keep calls modest and verify live data before relying on broad analysis.
