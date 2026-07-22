# Source notes

- Primary owner: NEMA official emergency alert feed information; MetService severe weather CAP
- Primary source: https://www.civildefence.govt.nz/about/news-and-events/news-and-events/cap-feed-for-emergency-mobile-alert-is-now-live
- Declared outbound hosts: www.civildefence.govt.nz, alerthub.civildefence.govt.nz, alerts.metservice.com
- Access mode: official CAP 1.2 feeds (NEMA Atom index; MetService RSS 2.0 index)
- Authentication: none
- Last verified: 2026-07-22
- Update cadence: live feeds; landing page freshness source-managed
- Reuse: retain primary-source links, published context and Crown/source terms; MetService CAP is Creative Commons BY 4.0 (per feed copyright); no republishing claim is made

## MetService feed

`https://alerts.metservice.com/cap/rss` is MetService's public CAP index for current
watches, warnings and advisories (verified live 2026-07-22; the channel is empty when
nothing is in force). Items link to CAP 1.2 XML documents on the same host; the same
allowlist rule applies as for NEMA linked entries. The channel `pubDate` is RFC 2822
and is normalised to UTC ISO for the shared staleness check. Each returned alert row
carries a `feed` field (`nema` or `metservice`). When one feed is unavailable the other
still answers, with an explicit per-feed warning in the envelope; only both failing is
a command failure.

## Feasibility decision

NEMA's current CAP technical-standard page identifies `https://alerthub.civildefence.govt.nz/atom/pwp` and its RSS equivalent as the public Emergency Mobile Alert feeds for NEMA, CDEM Groups, Health, Police, MPI and FENZ. The Atom feed was fetched successfully on 2026-07-19 and was valid but contained zero current/recent entries at that instant.

The parser requires an Atom namespace and CAP 1.2 payloads. Link-only entries are fetched only when the resolved URL remains on the declared Alert Hub host; Atom metadata is never fabricated into an alert. Alert/filter commands fetch every linked entry in the bounded feed set (maximum 100) before applying the caller's result limit, so link ordering cannot hide a matching alert. Active state applies CAP status, effective/expiry timestamps and update/cancel references. Point matching supports published CAP latitude,longitude polygons and kilometre-radius circles; invalid or non-finite coordinates fail with exit 2 before a network request. Geocodes remain machine-readable.

## Parser and maintenance

Requests explicitly revalidate the live feed. `feed-status` reports feed age, a 15-minute staleness threshold and health rather than hardcoding success. Fixtures cover namespaces, link resolution, future/cancel lifecycle, polygon/circle geometry and invalid HTML/XML. Schema changes fail closed with exit code 6.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
