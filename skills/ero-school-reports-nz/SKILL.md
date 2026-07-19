---
name: ero-school-reports-nz
description: "Find and retrieve official Education Review Office school reports with section or page provenance. Use for report evidence, not rankings."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "education"
  thecolab.source_owner: "Education Review Office"
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
  thecolab.source_url: "https://www.ero.govt.nz/review-reports"
  thecolab.allowed_domains: "ero.govt.nz, www.ero.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "degraded"
  thecolab.maintainer: "@adam91holt"
---

# ERO School Reports NZ

Use the read-only Python CLI to retrieve and filter records exposed by the official first-party source.
Every command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# search reports by school
python3 scripts/cli.py search SCHOOL --json
# find a school's latest report
python3 scripts/cli.py latest SCHOOL_ID --json
# find a report identifier
python3 scripts/cli.py report ID --json
# discover action and next-step sections
python3 scripts/cli.py actions ID --json
# discover report history
python3 scripts/cli.py history SCHOOL_ID --json
```

Add `--limit N` (1–100) to bound any command. Human output is the default.

## Coverage and interpretation

- Do not create numeric ratings or cross-school rankings unless ERO publishes the measure.
- Historical review frameworks and dates must remain explicit.
- Extracted findings require linked section or page provenance.

The CLI parses ERO institution pages and returns report metadata plus section-level HTML provenance. It never converts parser failure into an empty result and does not calculate ratings or rankings.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/test_contract.py` — deterministic repository contract audit
- `scripts/smoke_test.py` — parser fixture and bounded live probe
- `tests/fixtures/institution.html` — deterministic official report-schema fixture
- `references/source-profile.json` — command schema, source allowlist and warnings
- `references/source-notes.md` — feasibility, provenance and source limits
