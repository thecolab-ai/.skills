---
name: {{SKILL_NAME}}
description: "{{DESCRIPTION}}"
license: MIT
compatibility: "Requires Python 3.10+ and user-supplied credentials"
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
  thecolab.cache_ttl: "none"
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

Load credentials lazily inside `scripts/cli.py`, never emit them, and never use
live personal records in fixtures or CI. Read `references/source-notes.md` and
run the deterministic contract test before any opt-in live probe.
