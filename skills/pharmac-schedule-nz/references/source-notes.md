# Source notes

- Primary owner: Pharmac Pharmaceutical Schedule
- Primary source: https://www.pharmac.govt.nz/pharmaceutical-schedule/about-the-schedule
- Declared outbound hosts: www.pharmac.govt.nz, schedule.pharmac.govt.nz
- Access mode: official monthly production XML download
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: monthly schedule releases
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

The issue's landing surface and Pharmac's Schedule production resources were checked directly on 2026-07-19. Pharmac publishes current and archived `Schedule_YYYY-MM.xml` files and explicitly says production systems should use the XML. The archive documents a monthly update cadence and Schedule schema. The CLI discovers the latest version from the official index and can load named monthly releases.

Special Authority criteria can contain complex nested cases. The parser preserves structured rule/request attributes and text, official SA identifiers/forms, the Schedule publication effective date and its source without inferring eligibility. Version comparison reports each changed field with before/after values and both release URLs. Device classification follows the containing Schedule section and should be treated as source-labelled rather than inferred clinical classification.

## Parser and maintenance

The deterministic XML fixture covers funded-pack fields, nested Special Authority criteria, effective-date provenance and field-level version deltas. A live probe checks the current release metadata. XML/root/schema changes fail closed with exit code 6.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
