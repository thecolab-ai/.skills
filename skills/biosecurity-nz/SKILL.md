---
name: biosecurity-nz
description: Searches New Zealand biosecurity public data from the Official NZ Pest Register, PIER import requirements metadata, data.govt.nz CKAN records, and MPI active-response pages. Use when checking whether an organism is regulated, unwanted, or notifiable in NZ; finding pest synonyms/statuses; resolving import commodity requirement links; listing current biosecurity responses; or documenting source/access caveats.
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
