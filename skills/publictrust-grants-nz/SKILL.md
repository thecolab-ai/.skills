---
name: publictrust-grants-nz
description: Query Public Trust New Zealand public grants finder records through a read-only CLI. Use when the task involves NZ grant discovery, Public Trust grants, grant eligibility snippets, open/close status, regions, sectors, or organisation/personal grant matching. No login, application submission, or mutation.
---

# Public Trust grants NZ

## Goal

Query Public Trust's public grants finder through a small deterministic CLI with human-readable and JSON output. The skill fetches the current public page configuration, then uses the public Algolia grants index for read-only search and discovery.

## Use this when

- A user asks for Public Trust grants in New Zealand
- A user wants grants matching a keyword, region, sector, or grant type
- A user needs currently open Public Trust grants at fetch time
- A workflow needs structured grant titles, URLs, types, regions, sectors, dates, and eligibility/guideline snippets
- A user needs observed Public Trust sector or region values for filtering

## Do not use this for

- Submitting grant enquiries, registrations, applications, forms, or documents
- Login-gated, applicant-specific, or private grant data
- Treating Public Trust grants as exhaustive national grant coverage
- Treating machine-readable access as proof that the records are open-licensed for redistribution
- High-volume scraping or building a bulk mirror of Public Trust content

## Preferred workflow

1. Run `scripts/cli.py search` with a focused query and filters when possible
2. Use `list-open` for grants flagged as currently open by Public Trust
3. Use `detail` with a result `id` or slug before making eligibility claims
4. Use `sectors` and `regions` to discover exact filter values
5. Use `--json` for agent chaining and cite the `source_url`, `index_name`, and `fetched_at` fields
6. Tell users that open status and dates are current only at fetch time and should be checked on the Public Trust page before acting

## CLI

Run with:

```bash
python3 skills/publictrust-grants-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search QUERY [--region X] [--sector X] [--type X] [--open-only] [--limit N] [--json]` - keyword search
- `list-open [--region X] [--sector X] [--type X] [--limit N] [--json]` - grants with `applications_open_now`
- `detail ID_OR_SLUG [--json]` - one grant by Algolia object id, title, or URL slug
- `sectors [--json]` - observed sector values from current results
- `regions [--json]` - observed region values from current results
- `raw-query QUERY [--param key=value] [--json]` - debugging wrapper around Algolia parameters

Examples:

```bash
python3 skills/publictrust-grants-nz/scripts/cli.py search youth --json
python3 skills/publictrust-grants-nz/scripts/cli.py search education --region hawkes-bay --open-only
python3 skills/publictrust-grants-nz/scripts/cli.py list-open --limit 10 --json
python3 skills/publictrust-grants-nz/scripts/cli.py detail j-b-s-dudding-trust --json
python3 skills/publictrust-grants-nz/scripts/cli.py sectors --json
python3 skills/publictrust-grants-nz/scripts/cli.py regions --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- API and stability notes: `references/api-notes.md`

## Notes

- Public Trust's page exposes public Algolia configuration including the grants index; the CLI fetches it live instead of committing the search key
- JSON output includes `source_url`, `index_name`, `fetched_at`, and normalised grant fields
- Availability/open status is a live snapshot and can change without notice
- Machine-readable results do not imply open-licensed data or exhaustive New Zealand grant coverage
- Stay read-only: no login, no account actions, no application submission, no form mutation
