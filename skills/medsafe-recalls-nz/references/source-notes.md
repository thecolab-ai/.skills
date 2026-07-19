# Source notes

- Primary owner: Medsafe recalls
- Primary source: https://www.medsafe.govt.nz/hot/Recalls/RecallSearch.asp
- Declared outbound hosts: www.medsafe.govt.nz
- Access mode: bounded first-party portal/index retrieval
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: source-managed
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

The public search form and labelled detail table were checked directly on 2026-07-19. The connector submits bounded read-only searches and follows only first-party detail links. Because the portal search does not cover every detail field, a no-result query can trigger a bounded detail scan of recent official records for product codes, batches, models and software versions.

A recognisable zero-result table is a valid empty result. Missing/changed table structure remains a schema failure. Recall scope is never widened beyond published detail fields.

## Parser and maintenance

Fixtures cover result rows, a legitimate empty result and detail-only product identifiers. Live probes are bounded and outage-aware.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
