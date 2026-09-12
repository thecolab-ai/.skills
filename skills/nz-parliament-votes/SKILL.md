---
name: nz-parliament-votes
description: "Query official New Zealand Parliament weekly Journals for recorded divisions, preserving only printed party counts and explicitly printed voter names."
license: MIT
compatibility: "Requires Python 3.10+ and network access for live data"
metadata:
  thecolab.category: "government"
  thecolab.source_owner: "New Zealand Parliament"
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
  thecolab.source_url: "https://journals.parliament.nz/"
  thecolab.allowed_domains: "journals.parliament.nz"
  thecolab.last_verified: "2026-09-12"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Parliament Votes

Use the read-only Python CLI in `scripts/cli.py` to search weekly Journals and extract supported recorded party divisions. Every data command supports `--json`, bounded requests, stable exit codes, source URLs and retrieval timestamps.

## Commands

```bash
# List one bounded page of weekly Journals; optionally filter titles on that page
python3 scripts/cli.py search [QUERY] --page 1 --limit 20 --json

# Extract printed divisions from a Journal UUID returned by search
python3 scripts/cli.py votes JOURNAL_ID --json
```

The common lookup path is positional (`QUERY` or `JOURNAL_ID`). Human-readable output is the default. `--limit` is restricted to 1–50 and each request has a 10-second timeout and 4 MiB response ceiling.

## Interpretation rules

- Weekly Journals are **drafts**, not the authoritative Sessional Journal record.
- Return source-printed party labels/counts; preserve ambiguous singleton labels as `entity_kind: unknown`.
- Never infer an individual MP's vote from party membership, classify a singleton as a person, resolve a printed label to an identity, or add roles/electorates.
- Participant rows are emitted only when their printed counts reconcile with the side total.
- Missing abstentions remain `null`; unsupported layouts produce diagnostics, not inferred results or empty-source claims.
- Search filtering applies only to the one requested API page; it is not a full-archive search.

## Resources

- `scripts/cli.py` — canonical command entrypoint
- `scripts/parliament_votes.py` — strict stdlib Journal and search parser
- `scripts/test_contract.py` — deterministic contract, adversarial parser, and normal/empty/blocked tests
- `scripts/smoke_test.py` — synthetic fixture assertions and bounded live search probe
- `tests/fixtures/` — minimal scrubbed synthetic Journal, empty response, and contract sentinel
- `references/source-profile.json` — machine-readable commands and source constraints
- `references/source-notes.md` — provenance, parser semantics, and coverage limits
