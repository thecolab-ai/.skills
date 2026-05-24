---
name: linz-data-service
description: Search and inspect LINZ Data Service public Koordinates catalogue layers, tables, services, licences, tags, and download/view capabilities through no-login JSON endpoints. Use when the task involves Toitū Te Whenua LINZ datasets such as addresses, parcels, imagery, hydrography, roads, property, or geospatial layers. Read-only; no API key needed for catalogue metadata.
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
