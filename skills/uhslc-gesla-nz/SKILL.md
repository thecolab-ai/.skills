---
name: uhslc-gesla-nz
description: "Read a short University of Hawaii Sea Level Center GESLA sea-level series for one New Zealand station. Use for hourly or sub-hourly sea level in metres with quality flags. Not for LINZ tide predictions, the LINZ minute archive, or a global download."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "University of Hawaii Sea Level Center"
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
  thecolab.source_url: "https://uhslc.soest.hawaii.edu/erddap/info/global_hourly_gesla/index.html"
  thecolab.allowed_domains: "uhslc.soest.hawaii.edu"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# UHSLC GESLA New Zealand sea level

Use `scripts/cli.py` for one New Zealand GESLA record and a window of at most 48 hours. The command reads ERDDAP tabledap CSV from `uhslc.soest.hawaii.edu` and returns sea level in metres with the published quality flags. It does not accept a URL and it does not download the global table.

```bash
python3 scripts/cli.py series --station auckland-auct-nzl-ttw --from 2024-01-01T00:00:00Z --to 2024-01-01T02:00:00Z --json
```

`--from` is included and `--to` is excluded. Times are UTC instants (`2024-01-01T00:00:00Z` or a numeric offset). A station id is a lowercase GESLA `record_id` with an `nzl` segment. `--json` prints the `meta` / `results` envelope from `scripts/provenance.py`.

`sea_level` is the source decimal token in metres, or null when the source token is the documented missing value `-99.9999`. `flag1` and `flag2` keep the published codes and meanings. Rows marked do-not-use stay in the result. Repeated timestamps stay in source order. The source datum is unspecified.

Read `references/source-notes.md` for the flag vocabulary, licence, empty-window behaviour and bounds. `scripts/test_contract.py` is offline. `scripts/smoke_test.py` adds one bounded live request.
