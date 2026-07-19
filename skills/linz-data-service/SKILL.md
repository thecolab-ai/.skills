---
name: linz-data-service
description: "Search and inspect LINZ Data Service public Koordinates catalogue layers, tables, services, licences, tags, and download/view capabilities through no-login JSON endpoints. Use when the task involves Toitū Te Whenua LINZ datasets such as addresses, parcels, imagery, hydrography, roads, property, or geospatial layers. Read-only; no API key needed for catalogue metadata."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Toitū Te Whenua LINZ"
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
  thecolab.source_url: "https://data.linz.govt.nz/services/api/v1/"
  thecolab.allowed_domains: "data.linz.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# LINZ Data Service

## Goal

Find and inspect public LINZ Data Service catalogue records and advertised services without logging in.

## CLI

```bash
python3 skills/linz-data-service/scripts/cli.py search address --json
python3 skills/linz-data-service/scripts/cli.py layer 123113 --json
python3 skills/linz-data-service/scripts/cli.py services 123113
```

Commands:

- `search QUERY [--limit N] [--json]` - search public LDS layers
- `layer ID [--json]` - layer metadata, licence, tags, permissions, description
- `services ID [--json]` - advertised OGC/Koordinates service templates and auth requirements

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API notes: `references/api-notes.md`

## Notes

Metadata/search is no-auth. Some download/query service URLs advertise API-key variants; the skill reports those boundaries rather than bypassing them.
