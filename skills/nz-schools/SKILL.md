---
name: nz-schools
description: "Query official Ministry of Education school directory, roll, location and enrolment-zone resources. Use for source-backed school lookup, not rankings."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "education"
  thecolab.source_owner: "Ministry of Education"
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
  thecolab.source_url: "https://www.educationcounts.govt.nz/directories/list-of-nz-schools"
  thecolab.allowed_domains: "www.educationcounts.govt.nz, catalogue.data.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Schools

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search schools and directory resources
python3 scripts/cli.py search QUERY --json
# find a school by Ministry number
python3 scripts/cli.py school ID --json
# discover schools near valid WGS84 coordinates
python3 scripts/cli.py near --lat VALUE --lon VALUE --json
# discover official enrolment-zone resources
python3 scripts/cli.py zone --address VALUE --json
# filter by region
python3 scripts/cli.py region NAME --json
# discover school changes since an ISO date
python3 scripts/cli.py changes --since YYYY-MM-DD --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.
Latitude must be between -90 and 90, longitude between -180 and 180, and `--since` must be a valid `YYYY-MM-DD` date. Invalid values fail before the nightly source download.

## Coverage and interpretation

- Directory fields are not school rankings or quality claims.
- Enrolment-zone boundaries can change and require official school confirmation.
- No student-level or small-cell information is returned.

The Ministry publishes the Schools Directory as a nightly data.govt.nz DataStore resource. The
CLI reads that official resource and its modification timestamp, normalises directory fields,
and performs local search, region, Ministry-number and coordinate-distance queries. `changes`
reports opening dates present in the current directory with an explicit partial-coverage warning.
`zone --address` is unsupported until an authoritative geocoder and current zone geometry can be
combined without guessing.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/schools.json` — representative official-schema records
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
