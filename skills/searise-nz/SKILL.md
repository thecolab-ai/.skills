---
name: searise-nz
description: "Query NZ SeaRise sea-level rise and vertical land movement projections for every 2 km of the Aotearoa New Zealand coastline, from the official Zenodo-published dataset (Naish et al. 2024): find the nearest projection site to a location, read its vertical land movement rate, and read sea-level projections to 2300 by SSP scenario with and without VLM. Use when the task involves NZ sea-level rise projections, coastal subsidence or uplift rates, or climate adaptation planning inputs. Read-only; no authentication required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "NZ SeaRise programme (Victoria University of Wellington, GNS Science, NIWA)"
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
  thecolab.source_url: "https://zenodo.org/records/11398538"
  thecolab.allowed_domains: "zenodo.org"
  thecolab.last_verified: "2026-07-24"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# SeaRise NZ

## Goal

Read the official NZ SeaRise dataset (Naish et al. 2024, Zenodo record
11398538): vertical land movement rates and sea-level rise projections to
2300 for ~7,500 sites spaced every 2 km along the NZ coastline, by SSP
scenario and percentile.

## Use this when

- A task needs location-specific NZ sea-level rise projections (e.g. "how much
  sea-level rise should Petone plan for by 2100 under SSP2-4.5?")
- A task needs coastal subsidence/uplift (vertical land movement) rates
- A task needs relative sea-level rise that accounts for land movement

## Do not use this for

- Live tide levels or storm surge (use `nz-tides-surf`, `gwrc-hilltop-nz`)
- Coastal sensitivity classification layers (use `niwa-coastal-nz`)
- Regional inundation map overlays (use `wcc-arcgis-nz` for Wellington)

## Commands

```bash
python3 skills/searise-nz/scripts/cli.py sites --near "-41.29,174.78" --limit 5
python3 skills/searise-nz/scripts/cli.py vlm 3414 --json
python3 skills/searise-nz/scripts/cli.py projections 3414 --scenario SSP2-4.5 --confidence medium --json
python3 skills/searise-nz/scripts/cli.py projections 3414 --year 2100 --json
```

- `sites [--near lat,lon] [--limit N] [--json]` — projection sites, nearest-first when `--near` is given (downloads a ~674 KB CSV)
- `vlm SITE_ID [--json]` — vertical land movement rate, uncertainty, and quality for one site
- `projections SITE_ID [--scenario SSPx-y.z] [--confidence low|medium|all] [--year YYYY] [--no-vlm] [--json]` — decadal sea-level projections 2020–2300 with 17th/50th/83rd percentiles

## Notes

- Licence: CC BY 4.0 — cite Naish et al. (2024), Zenodo record 11398538
- `projections` downloads and parses a ~54 MB CSV per call (about 20–30 s); filter flags
  reduce output, not transfer — prefer one call and reuse the JSON
- Scenarios: SSP1-1.9, SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5; values are
  metres relative to the 1995–2014 baseline
- Negative VLM is subsidence and adds to relative sea-level rise; the default
  projections file already includes VLM (`--no-vlm` for climate-only)
- This is the 2024 (V2) dataset that supersedes the 2022 release — medians are
  similar but uncertainty bounds widened

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Dataset provenance, column layout, and the Takiwa map relationship:
  `references/source-notes.md`
