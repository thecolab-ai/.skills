# Source notes

- Primary owner: Product Safety New Zealand recalls
- Primary source: https://www.productsafety.govt.nz/recalls
- Declared outbound hosts: www.productsafety.govt.nz
- Access mode: bounded first-party portal/index retrieval
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: source-managed
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

The official recall listing and detail notices were checked directly on 2026-07-19. Search, supplier, category and hazard commands perform bounded first-party detail enrichment so supplier, identifiers, hazard and remedy participate in filtering.

The source does not consistently publish an active/closed field. `active` returns exit 7 when the bounded records have no explicit status rather than labelling every published recall active.

## Parser and maintenance

Fixtures cover list metadata and detail-only supplier, identifier, swallowed-parts/sunburn hazards and official remedy. Layout changes fail closed with exit code 6.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
