# Source notes

- Primary owner: Petstock
- Primary source: https://www.petstock.co.nz
- Declared outbound hosts: hx85npq0xp-dsn.algolia.net, www.petstock.co.nz
- Access mode: html-readonly
- Authentication: none
- Last verified: 2026-07-19

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

`ALGOLIA_API_KEY` is Petstock's public, read-only browser search key, not a user credential. The Algolia origin is pinned and cross-host redirects are rejected.
