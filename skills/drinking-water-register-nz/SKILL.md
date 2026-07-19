---
name: drinking-water-register-nz
description: "Query public Hinekōrako drinking-water supplier, supply, service-area and document records. Use for registration discovery; registration is not proof of current water safety."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "environment"
  thecolab.source_owner: "Taumata Arowai"
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
  thecolab.source_url: "https://hinekorako.taumataarowai.govt.nz/publicregister/supplies/"
  thecolab.allowed_domains: "hinekorako.taumataarowai.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Drinking Water Register NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search registered suppliers
python3 scripts/cli.py supplier QUERY --json
# search supplies
python3 scripts/cli.py supply ID_OR_NAME --json
# filter by region
python3 scripts/cli.py region NAME --json
# discover nearby records where official location data permit
python3 scripts/cli.py near --lat VALUE --lon VALUE --json
# discover public documents
python3 scripts/cli.py documents ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Registration is not proof of current potability or compliance.
- Missing public documents do not prove non-compliance.
- Suppression, privacy and small-supply publication limits are preserved.

The CLI uses the same public Power Pages grid and read-only detail pages as the official
register. Supply results include the public ID, name, type, community and canonical detail URL;
exact ID lookup adds registration status, population, region, authority and published documents
where present. `documents` requires an exact case-insensitive supply ID or name, returns a stable
document-only record (including an empty document list where none are published), and returns no
records for fuzzy-only matches. `near` is an explicit unsupported operation because the register does not expose
reliable public coordinates or service-area geometry.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/grid.json` and `supply-detail.html` — representative public-register fixtures
- `references/source-notes.md` — feasibility, provenance and source limits
