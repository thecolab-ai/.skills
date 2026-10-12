---
name: statsnz-geographic-tables
description: "Read Stats NZ Datafinder metadata and the published sample for the Current Geographic Boundaries table (122777) and the Geographic Areas Table 2026 (123518). Use for the table licence, feature count, publication time, geography-version names, and a bounded meshblock-concordance preview. Stats NZ CPI, GDP, population, and CSV catalogue queries belong to stats-nz."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "public-data"
  thecolab.source_owner: "Stats NZ"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "public-api"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "public-api"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://datafinder.stats.govt.nz/table/122777-current-geographic-boundaries-table/"
  thecolab.allowed_domains: "datafinder.stats.govt.nz"
  thecolab.last_verified: "2026-10-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# Stats NZ geographic tables

Read public Koordinates metadata and the published sample for two Stats NZ Datafinder tables. Attribute Stats NZ under Creative Commons Attribution 4.0 International.

## Use this when

- A task needs the licence, feature count, field names, or publication time for table 122777 or 123518
- A task needs the geography-version index in table 122777
- A task needs a bounded published sample of the 2026 geographic-areas concordance in table 123518

## Use another skill when

- The task is CPI, GDP, population, migration, or the Stats NZ large-datasets CSV catalogue (`stats-nz`)
- The task needs the keyed Datafinder query API, a bulk export, or the full concordance
- The task needs census microdata or a Datafinder user profile

## CLI

```bash
python3 skills/statsnz-geographic-tables/scripts/cli.py table 122777 --json
python3 skills/statsnz-geographic-tables/scripts/cli.py sample 122777 --json
python3 skills/statsnz-geographic-tables/scripts/cli.py table 123518 --json
python3 skills/statsnz-geographic-tables/scripts/cli.py sample 123518 --json
```

Commands:

- `table 122777|123518 [--json]` shows the licence, feature count, publication time, version, and field names
- `sample 122777|123518 [--json]` reads the published version sample only

`feature_count` is the Koordinates count for the whole table. `sample_row_count` counts only the rows returned by the published sample. Table 122777 is a geography-version index. Table 123518 is a meshblock concordance whose sample is a short wide preview.

Each request times out after 15 seconds. A response over 256 KiB, or a sample over 200 rows, is rejected. Redirects must stay on `datafinder.stats.govt.nz` and on the table or sample path. The `created_by` user profile is not emitted.

`--json` prints a `meta` and `results` envelope. `meta.latest_data` is the table `published_at` timestamp, not a statistical reference period. A row field such as `Date_Published` keeps the geography version date, including its original spacing.

## Resources

- CLI and tests: `scripts/`
- Endpoint notes, licence, and bounds: `references/source-notes.md`
