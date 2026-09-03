# Ministry of Education source notes

## Provenance

- Owner: New Zealand Ministry of Education
- Canonical page: https://www.education.govt.nz/school/school-terms-and-holidays
- Declared outbound host: `www.education.govt.nz`
- Access: public HTML over HTTPS; no account or browser required
- Authentication: none
- Last verified: 2026-09-03
- Verification result: HTTP 200 with complete current 2026, 2027 and 2028 sections plus a complete past-year 2025 section
- Intended cache duration: 24 hours

The live page is authoritative and can add or remove current or past published years. Current-year sections use `h2`/`h3`; the page's past-year section uses `h3`/`h4`. The CLI handles both heading depths and does not hard-code a current year.

## Source structure

The parser consumes semantic content only:

- `h2`/`h3`: current or past `<year> school terms` and `<year> school holidays` sections
- `h3`/`h4`: Term 1-4, half-day requirements and Summer holidays, according to section depth
- `p`: date descriptions, public-holiday notes, opening requirements and flexibility caveats

A year is accepted only when it has four parsed term records and four parsed break records. Missing dates or incomplete sections are a source-schema error (exit 6), not an empty success.

`tests/fixtures/source-sample.html` is a synthetic, minimal example shaped like the public page. It contains no credentials or personal data. `scripts/smoke_test.py` verifies variable opening and closing boundaries, fixed break ranges, date classification and next-break behaviour against that fixture before making one bounded live probe.

## Date semantics

- Term 1 may start anywhere inside the Ministry's published opening range.
- Term 4 begins on a fixed date but finishes on each school's chosen closing date, no later than the published boundary.
- Terms 2 and 3 and the three inter-term holiday ranges are fixed on the source page.
- Summer holidays start on the school's closing date, no later than the published boundary, and run for 5 or 6 weeks.
- Public holidays, local anniversary days, teacher-only days, local events and emergencies can close individual schools during a term.

The CLI therefore returns explicit `certainty` and `caveat` fields rather than inventing precision the Ministry does not publish.

## Failure and maintenance expectations

Every request uses the repository `nzfetch` helper with a 10-second default timeout and an exact outbound-host allowlist. HTTP blocks/rate limits are exit 4; transport/upstream errors are exit 5; malformed source content is exit 6. Do not add unofficial mirrors, historical datasets, school-directory data or browser automation without a separate reviewed scope and updated metadata.
