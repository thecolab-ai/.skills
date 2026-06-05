---
name: nzbn-register
description: Search and lookup public NZBN Register NZ business records: NZBN identity, company/entity status, trading names, addresses, and source-register identifiers. No login or API key required.
---

# NZBN Register

## Goal

Query live public NZBN Register business/entity data through a small deterministic Python CLI with human-readable and JSON output.

## Use this when

- A user asks to find an NZ business/entity by name
- A user has a 13-digit NZBN and wants public register details
- A workflow needs machine-readable NZBN, entity status, entity type, trading names, Companies Office source id, public addresses, websites, or contact fields published on the register
- A user needs an official NZ business identifier before checking other sources

## Do not use this for

- Authenticated MyNZBN actions, authority management, watchlists, or profile edits
- Private/suppressed register data
- Bulk scraping, full-register replication, or enrichment at high volume
- Mutating NZBN records or contacting businesses automatically
- Treating live register output as legal advice

## Preferred workflow

1. Run `scripts/cli.py search` with the narrowest business name/query that answers the task
2. Select the likely `nzbn` from results, then run `lookup <nzbn>` for exact public details
3. Use `--json` for agent chaining, comparisons, or structured reports
4. Cite the NZBN and source-register id/date fields when reporting findings
5. If multiple similar names appear, show candidates and avoid overclaiming identity

## CLI

Run with:

```bash
python3 skills/nzbn-register/scripts/cli.py <command> [flags]
```

### Commands

- `search <query> [--limit N] [--page N] [--json]` — search NZBN entities by business/entity name or NZBN text
- `lookup <nzbn> [--json] [--raw]` — fetch exact public details for a 13-digit NZBN

Examples:

```bash
python3 skills/nzbn-register/scripts/cli.py search "the warehouse" --limit 5
python3 skills/nzbn-register/scripts/cli.py search "the warehouse" --limit 5 --json
python3 skills/nzbn-register/scripts/cli.py lookup 9429000023795 --json
python3 skills/nzbn-register/scripts/cli.py lookup 9429000023795 --raw --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- No API key, OAuth token, username, password, cookie, or browser automation is required for the supported read-only commands
- The official API gateway (`api.business.govt.nz/gateway/nzbn/v5`) requires a subscription key when called directly; this skill uses the public NZBN website proxy used by the register UI
- Treat records as live public register snapshots; entity details can change
- Keep queries small and respectful
