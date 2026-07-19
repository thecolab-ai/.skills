---
name: eeca-ev-chargers-nz
description: "Query EECA New Zealand public EV charger dashboard CSVs and data.govt.nz metadata, including public charger units, co-funded charger pipeline rows, EV metrics by district or region, BEVs per charger, charging kW, site counts, and source caveats. Use for NZ EV infrastructure, EVRoam-derived charger coverage, charging equity, public co-funding, and For Good transport research."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Energy Efficiency and Conservation Authority"
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
  thecolab.source_url: "https://www.eeca.govt.nz/insights/data-tools/public-ev-charger-dashboard/"
  thecolab.allowed_domains: "catalogue.data.govt.nz,www.eeca.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# EECA EV Chargers NZ

## Overview

Read-only CLI for repeatable access to EECA's public EV charger dashboard
exports and the data.govt.nz CKAN package metadata. It uses Python 3 standard
library only, no API key, no browser, and no cache.

The CLI fetches official CSV exports for public charger units, co-funded charger
applications, and EV metrics by region or district. It normalises numeric
fields, exposes JSON for agent workflows, and includes source caveats when
aggregating charger capacity and BEV ratios.

## Use When

- Research needs current New Zealand public EV charger locations, site counts,
  charge points, operator/owner names, connector types, current type, or rated
  kW.
- A task asks for EV charging infrastructure coverage by region or district.
- You need BEVs per public charge point, kW per BEV, BEV penetration, or
  population-relative EV metrics from EECA dashboard exports.
- You need to separate live and in-progress co-funded charger applications.
- A For Good or policy workflow needs citable, repeatable public EV charger
  aggregates without one-off scraping.

Do not use this skill for private charger networks, route planning, real-time
charger availability, pricing, account access, or booking sessions. The EECA CSV
exports are public dashboard data, not a live operational charger API.

## Commands

Run commands through `scripts/cli.py`. Every command accepts `--json`.

| Command | Purpose |
| --- | --- |
| `datasets` | Report data.govt.nz package metadata, resource URLs, dashboard URL, and caveats |
| `chargers [--region REGION] [--district DISTRICT] [--min-kw KW] [--current AC|DC] [--operator TEXT]` | Return public charger unit rows with site, points, current, kW, lat/lon, locality, and connectors |
| `metrics --level region|district [--region REGION] [--district DISTRICT] [--sort FIELD]` | Return EECA EV metrics including BEVs, charge points, sites, kW, BEVs per charge point, penetration, and per-capita values |
| `cofunded [--status live|in-progress] [--region REGION] [--district DISTRICT] [--min-kw KW]` | Return EECA co-funded charger applications and pipeline rows |
| `summary --level region|district [--min-kw KW] [--region REGION] [--district DISTRICT]` | Aggregate charger units into charge points, sites, DC fast sites, total kW, BEVs per point, and kW per BEV |

## Examples

```bash
python3 skills/eeca-ev-chargers-nz/scripts/cli.py datasets --json
python3 skills/eeca-ev-chargers-nz/scripts/cli.py chargers --region Waikato --current DC --min-kw 50 --json
python3 skills/eeca-ev-chargers-nz/scripts/cli.py metrics --level district --region Northland --sort bevs_per_charge_point --json
python3 skills/eeca-ev-chargers-nz/scripts/cli.py cofunded --status in-progress --region Canterbury --json
python3 skills/eeca-ev-chargers-nz/scripts/cli.py summary --level region --min-kw 50 --json
```

## Notes

- Source CSVs are hosted by EECA and listed in the `public-ev-chargers`
  data.govt.nz package. The dashboard notes EVRoam/EECA-derived charger data;
  treat it as periodic dashboard data rather than live charger status.
- `chargers` reports individual charger units. A site may have multiple units,
  and a unit may have more than one charge point.
- `summary` multiplies rated kW by point count for unit-derived totals. EECA's
  metric CSV can differ if it uses different timing or source aggregation.
- DC fast sites in `summary` are sites with at least one DC unit rated 50 kW or
  above.
- Source URLs, field notes, and caveats are in `references/source-notes.md`.
- Run `python3 scripts/smoke_test.py` to verify the live data path.

## Resources

- CLI: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes: `references/source-notes.md`
