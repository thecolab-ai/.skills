---
name: searise-nz
description: "Query NZ SeaRise sea-level rise and vertical land movement projections for every 2 km of the Aotearoa New Zealand coastline, from the official Zenodo-published dataset (Hamling, Naish, Levy et al.): inspect record metadata and files, find projection sites, read vertical land movement, and retrieve one or many sites' projections to 2300 by SSP scenario with and without VLM. Use when the task involves NZ sea-level rise projections, coastal subsidence or uplift rates, dataset provenance, or climate adaptation planning inputs. Read-only; no authentication required."
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
  thecolab.source_url: "https://zenodo.org/records/14722058"
  thecolab.allowed_domains: "zenodo.org"
  thecolab.last_verified: "2026-07-26"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# SeaRise NZ

## Goal

Read the official NZ SeaRise dataset published on Zenodo: vertical land
movement rates for 8,173 coastal sites and sea-level rise projections to 2300
for 8,179 site ids spaced every 2 km along the NZ coastline, by SSP scenario
and percentile.

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
python3 skills/searise-nz/scripts/cli.py record --json
python3 skills/searise-nz/scripts/cli.py sites --near "-41.29,174.78" --limit 5
python3 skills/searise-nz/scripts/cli.py vlm 2503 --json
python3 skills/searise-nz/scripts/cli.py projections 2503 --scenario SSP2-4.5 --confidence medium --json
python3 skills/searise-nz/scripts/cli.py projections 2503 2504 2505 --year 2100 --json
```

Site 2503 is the projection site nearest Wellington CBD (0.48 km); always
resolve an id with `sites --near lat,lon` rather than assuming one.

- `record [--json]` — Zenodo DOI, version, publication date, title, creators, licence, and file inventory with byte sizes, checksums, and download URLs
- `sites [--near lat,lon] [--limit N] [--json]` — projection sites, nearest-first when `--near` is given (downloads a ~674 KB CSV)
- `vlm SITE_ID [--json]` — vertical land movement rate, uncertainty, and quality for one site
- `projections SITE_ID [SITE_ID ...] [--scenario SSPx-y.z] [--confidence low|medium|all] [--year YYYY] [--no-vlm] [--json]` — sea-level projections for a 2005 baseline plus decadal 2020–2300 steps, with 17th/50th/83rd percentiles

## Notes

- Licence: CC BY 4.0 — cite the dataset as Hamling, I., Naish, T., Levy, R.
  et al., *New Zealand Vertical land movement and sea rise projections*
  (Zenodo). The associated paper is Naish, T. et al. (2024), "The significance
  of vertical land movements at convergent plate boundaries in probabilistic
  sea-level projections for AR6 scenarios: the New Zealand case", *Earth's
  Future* — cite the dataset, not just the paper
- **The dataset straddles two Zenodo versions on purpose.** Projections come
  from v4 (`14722058`, Jan 2025), the current release; site details come from
  v3 (`11398538`, May 2024), the newest version that still publishes the
  site/VLM file. `record` reports both.
- 8,173 sites carry location and VLM detail, but the projection tables cover
  8,179 site ids — a handful of ids have projections with no site-details row,
  so `vlm` can legitimately fail for an id `projections` accepts
- `projections` downloads and scans one ~58 MB CSV per invocation (about 20–35 s),
  regardless of the number of site IDs. The CSV is iterated once and is not
  persisted or cached; all downloaded data remains ephemeral.
- Scenario, confidence, year, and `--no-vlm` apply to every requested site.
  Filters reduce output, not transfer size.
- One requested site preserves the original response shape. Multiple requested
  IDs return `requested_site_ids` plus ordered `sites` results. Duplicate IDs
  are repeated in input order. Each result has `status: ok`, `empty` when the
  site exists but filters select no rows, or `not_found` when the source has no
  rows for that ID.
- Scenarios: SSP1-1.9, SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5; values are
  metres relative to the 1995–2014 baseline. `--scenario` accepts either
  spelling (`SSP3-7` and `SSP3-7.0` both work)
- Low-confidence projections exist only for SSP1-2.6 and SSP5-8.5; the other
  three scenarios are medium-confidence only. `--confidence low` on those
  returns an explicit empty result, not a silent zero
- Negative VLM is subsidence and adds to relative sea-level rise; the default
  projections file already includes VLM (`--no-vlm` for climate-only)
- v4 values carry 3 decimal places against v3's 2, and add a zeroed 2005
  baseline row; the underlying projections are otherwise unchanged
- Invalid input and upstream/schema failures are structured JSON on stderr with
  a non-zero exit code. Missing sites in a multi-site request are data results,
  not command failures.

## Resources

- CLI entrypoint: `scripts/cli.py`
- Contract test: `scripts/test_contract.py`; smoke test: `scripts/smoke_test.py`
- Dataset provenance, column layout, and the Takiwa map relationship:
  `references/source-notes.md`
