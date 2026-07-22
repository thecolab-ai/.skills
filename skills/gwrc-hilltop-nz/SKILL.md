---
name: gwrc-hilltop-nz
description: "Query Greater Wellington Regional Council Hilltop environmental monitoring time series through a lightweight no-login CLI: rainfall gauges, river and stream levels and flows, monitoring site lists with coordinates, and per-site measurement catalogues. Use when the task involves Wellington-region rainfall totals, current river levels, flood-watch context, or Hilltop time-series data. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Greater Wellington Regional Council"
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
  thecolab.source_url: "https://hilltop.gw.govt.nz/data.hts"
  thecolab.allowed_domains: "hilltop.gw.govt.nz,data.hbrc.govt.nz,hydro.marlborough.govt.nz,hilltop.nrc.govt.nz,envdata.tasman.govt.nz"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# GWRC Hilltop NZ

## Goal

Query Greater Wellington Regional Council's public Hilltop environmental monitoring
server for rainfall gauge totals and river/stream levels and flows — the core
severe-weather situational data for the Wellington region — through a deterministic
read-only CLI with human and JSON output.

## Use this when

- A task needs current or recent Wellington-region river or stream levels/flows
- A task needs rainfall totals across the region's gauges over a recent window
- A task needs GWRC monitoring site locations or the measurements a site offers
- A workflow needs machine-readable Hilltop time-series data from a verified
  council server in the built-in registry; GWRC is the default

## Do not use this for

- Official flood or severe weather warnings — gauge data is raw and provisional;
  warnings come from MetService and civil defence channels
- River water quality (use `lawa-nz`), tides (use `nz-tides-surf`), or forecasts
- Any write, subscription, or alerting action

## Commands

```bash
python3 skills/gwrc-hilltop-nz/scripts/cli.py sites --search "hutt river" --limit 10
python3 skills/gwrc-hilltop-nz/scripts/cli.py sites --measurement Flow --json
python3 skills/gwrc-hilltop-nz/scripts/cli.py measurements --site "Hutt River at Taita Gorge"
python3 skills/gwrc-hilltop-nz/scripts/cli.py latest --site "Hutt River at Taita Gorge" --measurement Flow --json
python3 skills/gwrc-hilltop-nz/scripts/cli.py rainfall --hours 24 --limit 20 --json
python3 skills/gwrc-hilltop-nz/scripts/cli.py rivers --hours 24 --search hutt --json
python3 skills/gwrc-hilltop-nz/scripts/cli.py collections
```

- `sites [--measurement NAME] [--search TEXT] [--limit N] [--json]` — monitoring sites with lat/long
- `measurements --site NAME [--json]` — data sources, labels, copy-pastable `request as` names, units, and date spans at one site
- `latest --site NAME --measurement NAME [--window-hours N] [--json]` — most recent observation; a plain label resolves to the freshest matching series, while an exact `request as` value selects that series explicitly
- `rainfall [--hours N] [--search TEXT] [--limit N] [--json]` — per-gauge totals over the window, wettest first
- `rivers [--hours N] [--search TEXT] [--limit N] [--json]` — latest level/flow per site with min/max and rising/falling/steady trend
- `collections [--json]` — Hilltop collection names
- `councils [--json]` — verified council Hilltop servers in the registry

All data commands accept `--council gwrc|hbrc|marlborough|northland|tasman`.
Arbitrary endpoints are deliberately rejected; new official council servers must be
verified and added to the registry and declared-domain metadata. Collection names
differ per council: `rainfall`/`rivers` default to GWRC's collections — for another
council run `collections --council <key>` and pass `--collection NAME`.

## Notes

- No API key or login. Data is CC BY 4.0 — attribute "Greater Wellington Regional Council".
- Gauges log every ~5–15 minutes but upload every 2–3 hours: treat "latest" as up to
  a few hours behind reality, and never as a substitute for official warnings.
- Timestamps are NZ local time exactly as published by the server.
- Sites can expose duplicate labels such as `Stage` under multiple data sources.
  `measurements` prints each exact `request as` value; `latest --measurement Stage`
  selects the matching series with the newest advertised `to` timestamp and reports
  both `requested_measurement` and `resolved_measurement` in JSON.
- `rainfall` and `rivers` exclude decommissioned gauges that still answer with
  years-old data, and report how many were excluded; `latest` flags such readings
  with `stale: true` and their age in hours.
- Keep windows narrow (`--hours` defaults to 24, max 168) — collection queries fan out
  across ~100 sites server-side.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Endpoint discovery, latency, and licence detail: `references/source-notes.md`
