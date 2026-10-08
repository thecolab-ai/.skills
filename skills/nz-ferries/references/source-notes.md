# Source notes

- Primary owner: Participating New Zealand ferry operators
- Primary source: https://www.sealink.co.nz
- Declared outbound hosts: api.at.govt.nz,at.govt.nz,gtfs.at.govt.nz,pim-mobile.fullers.co.nz,www.bluebridge.co.nz,www.fullers.co.nz,www.interislander.co.nz,www.sealink.co.nz
- Access mode: public-api
- Authentication: mixed; user-supplied `AT_API_KEY` is required for AT Metro/Fullers data
- Last verified: 2026-10-08

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

Public HTTP requests and the optional Fullers browser navigation use 10-second bounds. The browser waits for the document, avoiding indefinite network-idle waits. Live probes retry transient failures once; valid empty sailing arrays are accepted, while schema failures remain failures.
