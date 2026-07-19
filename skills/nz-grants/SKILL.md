---
name: nz-grants
description: "Query New Zealand grant opportunities and grant-distribution history from DIA/Granted.govt.nz Class 4 gambling grants and CommunityMatters fund pages. Use when the task involves current NZ community grant opportunities, CommunityMatters fund criteria/source pages, pokie/Class 4 grant recipient history, funders, half-year periods, recipients, or Territorial Local Authority grant totals. Read-only and no API key required; upstream bot protection may require graceful retry or skip."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Department of Internal Affairs and participating funders"
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
  thecolab.source_url: "https://catalogue.data.govt.nz"
  thecolab.allowed_domains: "catalogue.data.govt.nz,www.communitymatters.govt.nz,www.granted.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# NZ Grants

## Goal

Find current New Zealand public grant opportunities and inspect grant distribution history using official public sources:

- DIA / Granted.govt.nz Class 4 gambling grants CSV, published through data.govt.nz.
- CommunityMatters public funds and opportunity pages, parsed from HTML when reachable.

## Use this when

- A user asks for current NZ community grant opportunities or CommunityMatters fund pages.
- A workflow needs an official source URL, summary text, criteria/application links, or a slug for a CommunityMatters fund.
- A user asks about Class 4 / pokie grant recipients, funders, distribution totals, half-year periods, or Territorial Local Authority history.
- A task needs machine-readable JSON from public grant sources with no account login.

## Do not use this for

- Applying for grants, logging into funding portals, submitting forms, or changing any record.
- Circumventing CAPTCHA, Incapsula, Cloudflare, or other request challenges. Treat those as upstream unavailable.
- Frozen Lottery recipient CSVs on CKAN; those are explicitly out of scope for this skill.
- Legal, tax, accounting, or eligibility advice. Use the source links and recommend official guidance where needed.

## CLI

```bash
python3 skills/nz-grants/scripts/cli.py class4 --period 2024-H2 --json
python3 skills/nz-grants/scripts/cli.py class4 --recipient "Auckland City Mission" --json
python3 skills/nz-grants/scripts/cli.py class4 --tla "Auckland" --limit 10 --json
python3 skills/nz-grants/scripts/cli.py funds --json
python3 skills/nz-grants/scripts/cli.py fund get community-organisation-grants-scheme --json
```

Commands:

- `class4 [--period YYYY-H1|YYYY-H2] [--recipient ORG] [--tla DISTRICT] [--funder NAME] [--status Accepted|Declined] [--query TEXT] [--limit N] [--json]` - streams the official Class 4 CSV and returns matching rows plus totals.
- `funds [--limit N] [--json]` - extracts CommunityMatters fund/opportunity links from the public funds index.
- `fund get <slug-or-url> [--max-chars N] [--json]` - fetches one CommunityMatters fund page and returns structured source URL, title, description, application/guidance links, and readable page text.

## Operational notes

CommunityMatters may return Incapsula/Cloudflare-style HTTP 403 from headless environments. The CLI reports `upstream_unavailable` with exit code 2 instead of trying to bypass the protection. Smoke tests treat that condition as a clean skip.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/api-notes.md`
