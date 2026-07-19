---
name: winz-rates-nz
description: "Query current and historical public Work and Income New Zealand benefit/payment rate tables and A-Z benefit entitlement pages. Use when the task involves WINZ benefit rates, NZ Super rates, Jobseeker/Sole Parent/Supported Living payment amounts, Accommodation Supplement thresholds, or official Work and Income eligibility/criteria page summaries."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "social-policy"
  thecolab.source_owner: "Work and Income"
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
  thecolab.source_url: "https://www.workandincome.govt.nz"
  thecolab.allowed_domains: "www.workandincome.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# WINZ rates NZ

## Goal

Fetch official public Work and Income New Zealand pages for benefit/payment rates and A-Z benefit entitlement information through a small deterministic Python CLI.

## Use this when

- A user asks for current Work and Income benefit or payment rates
- A workflow needs official annual rate tables such as Jobseeker Support, Sole Parent Support, Supported Living Payment, NZ Super and Veteran's Pension, Accommodation Supplement, Disability Allowance, childcare assistance, or related WINZ payments
- A user asks what a named WINZ benefit is, who can get it, or wants the official Work and Income page link
- An agent needs JSON output for rate table rows or A-Z entitlement page sections

## Do not use this for

- Calculating or guaranteeing a person's eligibility or entitlement amount
- Collecting private personal, health, income, housing, or identity information
- Applying for benefits, logging into MyMSD, uploading documents, or changing account data
- Using the partner-gated MSD API at `api.msd.govt.nz`
- High-volume scraping or mirroring Work and Income pages

## Preferred workflow

1. Use `rates --year <year> --json` to list available rate sections on the April rates page.
2. Use `rates get <payment-slug> --year <year> --json` to inspect one section's tables.
3. Use `benefits list --json` to discover A-Z benefit entitlement page slugs.
4. Use `benefits get <slug> --json` to fetch official summary, eligibility-like sections, page sections, and links.
5. Cite the returned `source_url` and make clear that Work and Income is the authority for decisions.
6. If Work and Income blocks the hosting environment, report the `upstream unavailable/blocked` condition rather than guessing.

## CLI

Run with:

```bash
python3 skills/winz-rates-nz/scripts/cli.py <command> [flags]
```

### Commands

- `rates [--year YEAR] [--json]` — list all payment/rate sections from `benefit-rates-april-<year>.html`.
- `rates get <payment-slug> [--year YEAR] [--json]` — return one rate section with table contexts, headers, and rows.
- `benefits list [--json]` — list public Work and Income A-Z benefit pages under `/products/a-z-benefits/`.
- `benefits get <slug> [--json]` — inspect one A-Z benefit page and extract overview, eligibility-like sections, page sections, and links.

Examples:

```bash
python3 skills/winz-rates-nz/scripts/cli.py rates --year 2026 --json
python3 skills/winz-rates-nz/scripts/cli.py rates get jobseeker-support --year 2026 --json
python3 skills/winz-rates-nz/scripts/cli.py benefits list --json
python3 skills/winz-rates-nz/scripts/cli.py benefits get accommodation-supplement --json
```

## Output notes

- Rate rows preserve the text of the Work and Income table headings and cells.
- Some Work and Income tables have multi-row headings or blank heading cells; the CLI keeps best-effort headings and falls back to `column_N` keys when row width differs.
- A-Z `eligibility_sections` are sections whose headings look like eligibility or criteria headings; they are not a legal eligibility determination.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Live smoke test: `scripts/smoke_test.py`
- Source notes: `references/api-notes.md`
