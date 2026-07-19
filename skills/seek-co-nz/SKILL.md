---
name: seek-co-nz
description: "Search and inspect public SEEK.co.nz job listings through a lightweight no-login CLI. Use when the task involves New Zealand job search, SEEK listing IDs, role/company/location snapshots, salary snippets, classifications, or machine-readable public job data. Read-only; no login, saved searches, applications, account, recruiter, or job-posting actions."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "SEEK"
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
  thecolab.source_url: "https://nz.seek.com"
  thecolab.allowed_domains: "nz.seek.com,www.seek.co.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# SEEK.co.nz

## Goal

Query live public SEEK.co.nz job-search results and public job detail pages through a deterministic Python CLI with human-readable and JSON output.

## Use this when

- A user asks to search current SEEK.co.nz jobs by role, skill, company, or keyword
- A user wants New Zealand job-market snapshots by location, title, salary snippet, work type, or classification
- A user has a SEEK job id and wants public detail fields or the job-ad text
- A workflow needs machine-readable public job results for alerts, comparisons, or research

## Do not use this for

- Applying for jobs, saving jobs, creating saved searches, logging in, CV/profile actions, recruiter actions, or employer/job-posting workflows
- Private/authenticated SEEK data or candidate account information
- High-volume scraping, dataset redistribution, or bypassing SEEK access controls
- Salary-history or market-trend claims beyond the live result snippets returned by SEEK

## Preferred workflow

1. Run `scripts/cli.py search` with explicit keywords and the narrowest useful `--where` value.
2. Use `--limit` to keep result pages small and respectful.
3. Use `job <id>` for public detail after selecting a result.
4. Use `--json` for agent chaining, alerts, market snapshots, or downstream analysis.
5. Treat results as live snapshots: jobs can expire, move, or change without notice.

## CLI

Run from the repository root:

```bash
python3 skills/seek-co-nz/scripts/cli.py <command> [flags]
```

### Commands

- `search <keywords> [--where LOCATION] [--page N] [--limit N] [--json]` — search public SEEK.co.nz job listings
- `job <job-id> [--json]` — fetch public detail for a numeric SEEK job id

Examples:

```bash
python3 skills/seek-co-nz/scripts/cli.py search "python developer" --where Auckland --limit 5
python3 skills/seek-co-nz/scripts/cli.py search "data analyst" --where Wellington --limit 10 --json
python3 skills/seek-co-nz/scripts/cli.py job 92100951 --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- API/source notes: `references/api-notes.md`

## Notes

- No API key, OAuth app credentials, username, password, cookie, browser automation, or Playwright dependency is required for supported read-only commands.
- SEEK currently serves search results as public server-rendered HTML and uses GraphQL for supporting facets/suggestions; the CLI deliberately parses the public HTML search/detail pages instead of calling authenticated or account surfaces.
- The CLI sends browser-compatible request headers because bare default Python requests can receive `403` from Cloudflare/edge filtering even though the same public page is accessible without login.
- Keep usage narrow and respectful.
