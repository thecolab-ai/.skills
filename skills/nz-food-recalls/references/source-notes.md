# Source notes

- Primary owner: MPI food recalls
- Primary source: https://www.mpi.govt.nz/food-safety-home/food-recalls-and-complaints/
- Declared outbound hosts: www.mpi.govt.nz
- Access mode: bounded first-party portal/index retrieval
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: source-managed active notices
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

The official yearly index and detail notices were checked directly on 2026-07-19. Search, allergen and brand commands perform a bounded first-party detail enrichment so official batch, hazard/allergen, distribution and consumer-action fields participate in filtering.

The source does not consistently publish an active/closed field. `active` returns exit 7 when the bounded records have no explicit status rather than labelling every historical published notice active.

## Parser and maintenance

Fixtures cover yearly listing, batch/date text, milk-allergen retrieval, distribution and consumer action. Layout changes fail closed with exit code 6.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
