---
name: {{SKILL_NAME}}
description: "{{DESCRIPTION}}"
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "{{CATEGORY}}"
  thecolab.source_owner: "{{SOURCE_OWNER}}"
  thecolab.source_type: "{{SOURCE_TYPE}}"
  thecolab.auth: "{{AUTH}}"
  thecolab.access_mode: "{{ACCESS_MODE}}"
  thecolab.data_class: "{{DATA_CLASS}}"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "{{RISK}}"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "{{SKILL_TYPE}}"
  thecolab.pack: "{{PACK}}"
  thecolab.source_url: "{{SOURCE_URL}}"
  thecolab.allowed_domains: "{{ALLOWED_DOMAINS}}"
  thecolab.last_verified: "{{LAST_VERIFIED}}"
  thecolab.health: "untested"
  thecolab.maintainer: "@adam91holt"
---

# {{SKILL_TITLE}}

Use the Python CLI in `scripts/cli.py`. Every data command must support
`--json`, use explicit timeouts, and fail closed when the source schema changes.

Read `references/source-notes.md` before replacing the scaffold status command.
Run `scripts/test_contract.py` and `scripts/smoke_test.py` after implementation.
