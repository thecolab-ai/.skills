---
name: oia-statistics-nz
description: "Query New Zealand Public Service Commission six-monthly OIA compliance statistics with per-period and per-agency views, including timeliness, extensions, transfers, refusals, proactive publication, and Ombudsman complaints."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "Public Service Commission"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-download"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-download"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.publicservice.govt.nz/data/oia-statistics"
  thecolab.allowed_domains: "www.publicservice.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# OIA Statistics NZ

## Goal

Expose the Public Service Commission six-monthly Official Information Act (OIA) statistics in a small, deterministic CLI that removes scraping friction for downstream civic-transparency workflows.

The skill focuses on the PSC all-data CSV series, which contains historical per-agency series from January/July 2015 onward.

## Use this when

- You need per-agency OIA workload and performance series for NZ public-sector bodies.
- You need a machine-readable on-time rate, complaint, extension, transfer, or refusal snapshot for a period.
- You need the latest period and historical aggregate totals for reporting or comparison.
- You need official links and discovered OIA release table URLs for reproducible citations.

## Do not use this for

- Accessing any non-OIA datasets.
- Requesting private or protected internal agency systems.
- Non-official or third-party mirror data.

## Commands

- `list-agencies [--json]` - list distinct agencies in the all-data CSV.
- `agency <name-or-org-id> [--period YYYY-MM-DD|latest] [--json]` - full per-period time series for one agency or one period.
- `period <YYYY-MM-DD|latest> [--sort name|worst|best|requests] [--json]` - all agencies for one period with computed timeliness percentage.
- `periods [--json]` - list all discovered survey periods with simple period-level counts.
- `tables [--format all|csv|xlsx|pdf] [--json]` - discover PSC OIA table assets from the landing page (plus the stable all-data CSV fallback).
- `timeliness [--period latest] [--sort worst|best|name] [--limit 20] [--json]` - agency timeliness metrics for a period.
- `refusals [--period latest] [--sort worst|best|name] [--limit 20] [--json]` - refusal count and percentage per agency.
- `extensions [--period latest] [--sort worst|best|name] [--limit 20] [--json]` - extension count and percentage per agency.
- `complaints [--period latest] [--sort complaints|final_opinions|worst|best|name] [--limit 20] [--json]` - Ombudsman complaints and final-opinion counts.
- `totals [--period latest] [--json]` - sector-wide totals and computed aggregate on-time rate for a period.

## CLI

Run with:

```bash
python3 skills/oia-statistics-nz/scripts/cli.py <command> [flags]
```

## Notes

- No API key, auth, or browser automation required for implemented commands.
- Network timeout and upstream-unavailable handling are built in for blocked upstreams.
- CSV is the preferred parse format because this repo avoids non-stdlib XLSX dependencies.
- XLSX/period releases are discoverable and referenced through `tables`, and the CLI documents that structured parsing is not implemented for XLSX in this skill.

## Resources

- API notes: `references/api-notes.md`
