---
name: us-ntd-safety
description: "Query United States Federal Transit Administration National Transit Database safety data on data.transportation.gov. Use for coded US major safety and security event fields and monthly modal safety and service aggregates. This is United States transit data, not Auckland or New Zealand."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "transport"
  thecolab.source_owner: "Federal Transit Administration"
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
  thecolab.source_url: "https://data.transportation.gov/"
  thecolab.allowed_domains: "data.transportation.gov"
  thecolab.last_verified: "2026-10-11"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# US National Transit Database safety

Use `scripts/cli.py` for two United States Federal Transit Administration
resources on data.transportation.gov. These are not Auckland Transport feeds.
The catalogue scope tag that says Auckland does not describe this publisher.

Read `references/source-notes.md` for licences, withheld fields, units and lag.

```bash
python3 skills/us-ntd-safety/scripts/cli.py events --limit 20 --json
python3 skills/us-ntd-safety/scripts/cli.py events --limit 20 --year 2024 --mode MB --ntd-id 00000 --json
python3 skills/us-ntd-safety/scripts/cli.py modes --limit 20 --year 2024 --month January --json
```

## Commands

- `events [--limit N] [--year YYYY] [--mode CODE] [--ntd-id DDDDD]` reads SODA
  resource `9ivb-8ae9` (Major Safety and Security Events). Output is coded
  fields and counts only.
- `modes [--limit N] [--year YYYY] [--month Month] [--mode CODE] [--ntd-id DDDDD]`
  reads SODA resource `5ti2-5uiv` (Monthly Modal Time Series). Output is
  monthly agency-mode aggregates.

`--limit` is an integer from 1 to 100. The default is 20. `--year` is
1900–2099. `--mode` is a 1–4 letter NTD code such as `MB` or `HR`. `--month`
is a full English month name such as `January` and applies only to `modes`.
Bad arguments fail before any network call.

Each command checks that resource's view metadata before reading rows.
`events` continues only when `licenseId` is `USGOV_WORKS`. `modes` continues
only when `licenseId` is `PUBLIC_DOMAIN`. A missing or different id is refused.
The other resource's id does not satisfy the check.

## Output

`--json` returns `meta` and `results`. `meta` includes `source_url`,
`publisher`, `retrieved_at`, the verified `licence`, `geography` (`United States`),
stated `units`, and `latest_data` when the view has `rowsUpdatedAt`. That
timestamp is the Socrata update instant in UTC. It is not the newest event
date and not an Auckland date.

`incident_date`, `incident_time` and `month_year` are copied as source strings.
They have no timezone. Do not relabel them as UTC or Auckland time.

Absent measures are omitted, except an explicit JSON null, which stays null.
Do not treat either as zero. A non-numeric token in a measure stays a string
and is listed in `unparsed_measures`.

The row set never includes incident narratives, person lists, approximate
addresses, coordinates, free-text comments, or other-description fields.
Use `--json` when you need the full coded set. Text output is a short summary.
