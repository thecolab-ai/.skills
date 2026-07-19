# Source notes

- Primary owner: Fire and Emergency New Zealand incident reports
- Primary source: https://www.fireandemergency.nz/incidents-and-news/incident-reports/
- Annual data: https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/
- Metadata: https://www.fireandemergency.nz/assets/Documents/About-FENZ/Incident-data/FENZ-Incident-Metadata-2025_12.pdf
- Declared outbound hosts: www.fireandemergency.nz
- Access mode: bounded first-party portal/index retrieval
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: operational feed and annual publication dependent
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

The connector parses FENZ's labelled operational incident table and marks classifications as
preliminary. The proactive-release page publishes financial-year incident downloads from 2017-18
through 2024-25. Its metadata states that each file is one tab-delimited table with one record per
exposure, updated annually. `annual` and `trend` discover these official links and aggregate by the
published Regional Council and Incident Type fields, retaining exposure and distinct-incident counts.

## Parser and maintenance

The deterministic fixtures cover labelled operational fields, official annual resource discovery,
tab-delimited annual rows, regional aggregation, exposure-versus-incident semantics and bounds.
ZIP-wrapped and direct text tables are supported. Missing required annual columns fail closed.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
