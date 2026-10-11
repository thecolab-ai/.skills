# Source notes

- Primary owner: New Zealand Government
- Primary source: https://www.beehive.govt.nz
- Declared outbound hosts: www.beehive.govt.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-08

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

Live probes retry a transient RSS failure once. Browser navigation is limited to 10 seconds followed by four one-second content checks, without repeated page reloads. Persistent upstream blocks remain explicit; parser failures remain failures.
