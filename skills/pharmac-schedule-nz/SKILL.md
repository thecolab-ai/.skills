---
name: pharmac-schedule-nz
description: "Query official Pharmac Schedule funding, subsidy, restriction and Special Authority resources. Use for source-backed medicine/device funding research; not clinical advice."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "health"
  thecolab.source_owner: "Pharmac"
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
  thecolab.source_url: "https://www.pharmac.govt.nz/pharmaceutical-schedule/about-the-schedule"
  thecolab.allowed_domains: "www.pharmac.govt.nz, schedule.pharmac.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# Pharmac Schedule NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search medicines, devices, brands, chemicals or identifiers
python3 scripts/cli.py search QUERY --json
# find a medicine by identifier or name
python3 scripts/cli.py medicine ID_OR_NAME --json
# find a device by identifier or name
python3 scripts/cli.py device ID_OR_NAME --json
# find Special Authority criteria and forms
python3 scripts/cli.py special-authority QUERY --json
# discover changes between schedule releases
python3 scripts/cli.py changes --from VALUE --to VALUE --json
# show current schedule version resources
python3 scripts/cli.py schedule-version --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Funding retrieval is not prescribing, diagnosis, dosage or treatment advice.
- Do not infer suitability, interchangeability or entitlement beyond published rules.
- Clinical and eligibility decisions remain with authorised professionals.

The CLI loads Pharmac's official production XML, which Pharmac identifies as the production-system source. It parses funded packs, chemical/formulation/brand, subsidy, price, restrictions and Special Authority references. Monthly comparisons are keyed by the published pack identifier and explicitly identify additions, removals and changed subsidy/price/restriction fields.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/schedule.xml` — structured Schedule and Special Authority fixture
- `references/source-notes.md` — feasibility, provenance and source limits
