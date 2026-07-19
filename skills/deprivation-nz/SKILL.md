---
name: deprivation-nz
description: "Look up New Zealand small-area socioeconomic deprivation (NZDep2023) by SA1/SA2 code, place name, decile, or SA3 region - the standard index of relative poverty, material hardship, and disadvantage used for health, housing, school decile, child poverty, and funding analysis. No API key or login required."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "property"
  thecolab.source_owner: "University of Otago"
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
  thecolab.source_url: "https://services6.arcgis.com/ZVM1rEuVZjtC1Wwk/arcgis/rest/services/"
  thecolab.allowed_domains: "services6.arcgis.com,www.arcgis.com"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Deprivation NZ (NZDep2023)

## Goal

Query the New Zealand Index of Deprivation 2023 (NZDep2023) through a small deterministic CLI with human-readable and JSON output, without browser automation, login, API keys, or local cache state.

NZDep2023 ranks every small area in New Zealand on relative socioeconomic deprivation. Decile 1 = least deprived, decile 10 = most deprived. It is the standard proxy for area-level poverty, material hardship, and disadvantage used across health, housing, education, and social-policy analysis.

This skill ships support for:

- Per-area deprivation decile, raw score, and population for Statistical Area 1 (SA1)
- Averaged deprivation decile/score for Statistical Area 2 (SA2), with parent SA3 region
- Name search over SA2 area names (returns SA1 or SA2 detail)
- Listing areas in a specific deprivation decile
- Listing all SA2 areas inside an SA3 region with their deprivation
- A national summary of the SA1 decile distribution

## Use this when

- A user asks how deprived, poor, or disadvantaged a New Zealand suburb, street, or area is
- A user needs the NZDep2023 decile or score for an SA1 or SA2 code, or for a named place
- A workflow needs area-level deprivation as a proxy for child poverty, material hardship, or need
- A user is matching deprivation to health, housing, school decile, or funding allocation
- Another tool or agent needs machine-readable NZDep2023 values

## Do not use this for

- Individual or household income, benefit numbers, or the public housing register (NZDep is area-level only, not person-level)
- Geospatial boundary polygons, maps, or GIS overlays (this CLI requests `returnGeometry=false`)
- Older indexes (NZDep2018, NZDep2013) - only the 2023 release is wired
- Census microdata or confidentialised unit records
- Redistributing the dataset as a standalone product

## CLI

Run with:

```bash
python3 skills/deprivation-nz/scripts/cli.py <command> [flags]
```

Every command supports `--json` for machine-readable output; the default is human-readable.

## Commands

- `sa1 --code <SA1_code> [--json]` - NZDep2023 decile, score, and population for a 7-digit SA1 area
- `sa2 --code <SA2_code> [--json]` - averaged NZDep2023 decile/score for a 6-digit SA2 area, plus its SA3 region
- `search --name <text> [--level sa1|sa2] [--limit N] [--json]` - find areas whose SA2 name matches text
- `decile --value <1-10> [--level sa1|sa2] [--limit N] [--json]` - list areas in a given deprivation decile
- `region --sa3 <SA3_name> [--limit N] [--json]` - list SA2 areas within an SA3 region with their deprivation
- `stats [--json]` - national count and decile distribution across all SA1 areas

Examples:

```bash
python3 skills/deprivation-nz/scripts/cli.py sa1 --code 7000000 --json
python3 skills/deprivation-nz/scripts/cli.py sa2 --code 127100
python3 skills/deprivation-nz/scripts/cli.py search --name "Auckland" --level sa2 --limit 10 --json
python3 skills/deprivation-nz/scripts/cli.py decile --value 10 --level sa2 --limit 20 --json
python3 skills/deprivation-nz/scripts/cli.py region --sa3 "Northcote (Auckland)" --json
python3 skills/deprivation-nz/scripts/cli.py stats --json
```

## Resources

- CLI entrypoint: `scripts/cli.py`
- Feature service and field notes: `references/api-notes.md`

## Notes

- Source: New Zealand Index of Deprivation 2023 (NZDep2023), University of Auckland / Stats NZ, published as a public ArcGIS Feature Service (no login, no key)
- Decile 1 is least deprived; decile 10 is most deprived - always state the direction when reporting
- SA1 carries the per-area decile/score/population; SA2 carries area-averaged values plus the parent SA3 region
- `search` and `region` match on names case-insensitively using an ArcGIS `LIKE` query; name input is validated to safe characters before being sent
- The service caps each query at 2,000 records; use `--limit` and narrower filters for large regions
- Cite NZDep2023 as the upstream source when reporting figures, and note that it measures area-level relative deprivation, not individual circumstances
- Default output is human-readable; every command supports `--json` for chaining into other tools
