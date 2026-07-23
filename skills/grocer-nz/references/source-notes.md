# Source notes

- Primary owner: Grocer.nz
- Primary source: https://assets-prod.grocer.nz/public
- Declared outbound hosts: assets-prod.grocer.nz,grocer.nz,meilisearch.grocer.nz
- Access mode: html-readonly
- Authentication: none
- Last verified: 2026-07-24

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

`MEILI_KEY` is grocer.nz's public, read-only browser search key, not a user credential. It is sent only to the declared Meilisearch host and cross-host redirects are rejected.
