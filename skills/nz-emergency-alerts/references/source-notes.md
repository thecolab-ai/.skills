# Source notes

- Primary owner: NEMA official emergency alert feed information
- Primary source: https://www.civildefence.govt.nz/about/news-and-events/news-and-events/cap-feed-for-emergency-mobile-alert-is-now-live
- Declared outbound hosts: www.civildefence.govt.nz, alerthub.civildefence.govt.nz
- Access mode: official CAP 1.2 Atom feed
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: live feed; landing page freshness source-managed
- Reuse: retain primary-source links, published context and Crown/source terms; no republishing claim is made

## Feasibility decision

NEMA's current CAP technical-standard page identifies `https://alerthub.civildefence.govt.nz/atom/pwp` and its RSS equivalent as the public Emergency Mobile Alert feeds for NEMA, CDEM Groups, Health, Police, MPI and FENZ. The Atom feed was fetched successfully on 2026-07-19 and was valid but contained zero current/recent entries at that instant.

The parser requires an Atom namespace and CAP 1.2 payloads. Link-only entries are fetched only when the resolved URL remains on the declared Alert Hub host; Atom metadata is never fabricated into an alert. Alert/filter commands fetch every linked entry in the bounded feed set (maximum 100) before applying the caller's result limit, so link ordering cannot hide a matching alert. Active state applies CAP status, effective/expiry timestamps and update/cancel references. Point matching supports published CAP latitude,longitude polygons and kilometre-radius circles; invalid or non-finite coordinates fail with exit 2 before a network request. Geocodes remain machine-readable.

## Parser and maintenance

Requests explicitly revalidate the live feed. `feed-status` reports feed age, a 15-minute staleness threshold and health rather than hardcoding success. Fixtures cover namespaces, link resolution, future/cancel lifecycle, polygon/circle geometry and invalid HTML/XML. Schema changes fail closed with exit code 6.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
