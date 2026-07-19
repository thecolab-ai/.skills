---
name: fenz-incidents-nz
description: "Query official Fire and Emergency New Zealand operational reports and annual incident datasets by place, type and period."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "emergency"
  thecolab.source_owner: "Fire and Emergency New Zealand"
  thecolab.source_type: "official"
  thecolab.auth: "none"
  thecolab.access_mode: "html-readonly"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "html-readonly"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.fireandemergency.nz/incidents-and-news/incident-reports/"
  thecolab.allowed_domains: "www.fireandemergency.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# FENZ Incidents NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# list recent incident resources
python3 scripts/cli.py recent --json
# search incident resources
python3 scripts/cli.py search QUERY --json
# filter by region
python3 scripts/cli.py region NAME --json
# filter by incident type
python3 scripts/cli.py type NAME --json
# find an incident identifier
python3 scripts/cli.py incident ID --json
# discover annual statistical data
python3 scripts/cli.py annual --year VALUE --json
# discover regional trend resources
python3 scripts/cli.py trend --region VALUE --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Do not expose details beyond those FENZ publishes.
- Preliminary operational labels are not final classifications.
- Absence from the public feed does not prove no incident occurred.
- No notification or dispatch function is provided.

The CLI parses FENZ's labelled seven-day incident records and marks them preliminary. `annual`
discovers an official financial-year download and aggregates its tab-delimited exposure rows by
regional council and incident type. `trend` applies the same aggregation across published years.
Every annual result retains dataset URL, metadata context, financial year and row-unit caveats.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/incidents.html`, `annual-resources.html` and `annual.tsv` — source fixtures
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
