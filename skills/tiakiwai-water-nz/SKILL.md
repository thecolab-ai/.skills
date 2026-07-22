---
name: tiakiwai-water-nz
description: "Query Wellington Water (Tiaki Wai) public network fault and job status records through a lightweight no-login CLI: current water, wastewater, and stormwater faults and repair jobs across Wellington, Hutt, Upper Hutt, and Porirua with location, status, priority, and report times. Use when the task involves Wellington-region water outages, pipe faults, stormwater blockages, or three-waters incident monitoring. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "emergency"
  thecolab.source_owner: "Wellington Water (Tiaki Wai)"
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
  thecolab.source_url: "https://www.tiakiwai.co.nz/faults-and-outages/see-outages/network-status"
  thecolab.allowed_domains: "www.tiakiwai.co.nz,services7.arcgis.com"
  thecolab.last_verified: "2026-07-22"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Tiaki Wai Water NZ

## Goal

Query Wellington Water's (Tiaki Wai's) public network fault and job records — the
data behind their network-status map — for current drinking water, wastewater, and
stormwater faults across Wellington, Hutt, Upper Hutt, and Porirua council areas.

## Use this when

- A task needs current Wellington-region water/wastewater/stormwater faults or
  repair jobs (location, status, priority, report time)
- A task needs fault counts by council area and water type (storm-impact signal)
- A workflow needs machine-readable three-waters incident data for the region

## Do not use this for

- Fault reporting, service requests, or any account/write action
- Water quality (use `lawa-nz` / `safeswim-nz`) or river levels (use `gwrc-hilltop-nz`)
- South Wairarapa (SWDC jobs are not present in the public layer as observed)

## Commands

```bash
python3 skills/tiakiwai-water-nz/scripts/cli.py summary --json
python3 skills/tiakiwai-water-nz/scripts/cli.py faults --council wcc --water-type storm --limit 20
python3 skills/tiakiwai-water-nz/scripts/cli.py faults --search "miramar" --json
python3 skills/tiakiwai-water-nz/scripts/cli.py fault 940173 --json
```

- `faults [--council wcc|hcc|pcc|uhcc] [--water-type drinking|storm|waste] [--search TEXT] [--include-resolved] [--limit N] [--json]` — open jobs, newest first
- `fault JOB_NUMBER [--json]` — one job with full detail
- `summary [--council ...] [--water-type ...] [--include-resolved] [--json]` — open-job counts by council and water type

## Notes

- Data source: the public ArcGIS feature layer Tiaki Wai's own outage map reads
  (`Job_Status_Public_View`); no key or login.
- Rows the source marks "Do Not Display" are always excluded; resolved jobs are
  excluded unless `--include-resolved`.
- Timestamps are converted to Pacific/Auckland ISO; raw epoch values remain in
  `fault`'s `raw_properties`.
- Jobs are operational maintenance records, not customer-facing outage notices —
  a job's existence does not by itself mean supply is off.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Endpoint discovery and field notes: `references/source-notes.md`
