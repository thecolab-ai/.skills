---
name: biosecurity-nz
description: "Searches New Zealand biosecurity public data from the Official NZ Pest Register, PIER import requirements metadata, data.govt.nz CKAN records, and MPI active-response pages. Use when checking whether an organism is regulated, unwanted, or notifiable in NZ; finding pest synonyms/statuses; resolving import commodity requirement links; listing current biosecurity responses; or documenting source/access caveats."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Ministry for Primary Industries"
  thecolab.source_type: "mixed"
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
  thecolab.source_url: "https://onzpr.mpi.govt.nz"
  thecolab.allowed_domains: "catalogue.data.govt.nz,onzpr.mpi.govt.nz,pierpestregister.mpi.govt.nz,piersearch.mpi.govt.nz,www.mpi.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Biosecurity NZ

## Goal

Query keyless New Zealand biosecurity sources through a small deterministic CLI, with explicit blocked states when MPI/ONZPR/PIER pages are protected by Incapsula.

## Use This When

- A user asks whether an organism is regulated, unwanted, or notifiable in New Zealand.
- A user needs ONZPR pest names, synonyms, organism type, regulatory status, HSNO status, country freedom, or detail-page links.
- A user needs PIER import commodity requirement candidates and official requirement links.
- A user needs current MPI biosecurity response page links, or source metadata from data.govt.nz.

Do not use this for personalised import advice or legal clearance decisions. Return source URLs and tell the user to verify against MPI's official pages.

## CLI

```bash
python3 skills/biosecurity-nz/scripts/cli.py pest search --query "fruit fly" --json
python3 skills/biosecurity-nz/scripts/cli.py pest get 111 --json
python3 skills/biosecurity-nz/scripts/cli.py notifiable --limit 10 --json
python3 skills/biosecurity-nz/scripts/cli.py import-requirements --commodity Apple --country Japan --json
python3 skills/biosecurity-nz/scripts/cli.py responses --json
python3 skills/biosecurity-nz/scripts/cli.py sources --json
```

Commands:

- `pest search --query TEXT [--limit N] [--json]` - search ONZPR records through `pest-api.php?method=GetTableDataAjax`.
- `pest get PEST_ID [--json]` - fetch an ONZPR detail page and return parsed status/taxonomy/source links.
- `notifiable [--limit N] [--json]` - list notifiable ONZPR records.
- `import-requirements --commodity NAME [--country NAME] [--commodity-type-id ID] [--json]` - resolve PIER commodity types, result rows, country lists, and requirement pages where available.
- `responses [--json]` - parse MPI's active biosecurity response index when accessible; otherwise return `status: blocked`.
- `sources [--json]` / `datasets [--json]` - return CKAN metadata and source endpoint notes.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and caveats: `references/api-notes.md`
