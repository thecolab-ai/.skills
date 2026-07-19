# Source notes

- Owner/source: Education Review Office, `https://www.ero.govt.nz/review-reports`
- Authentication: none
- Last verified: 2026-07-19
- Institution pages: `/institution/{education-institution-number}`
- Access: public and read-only; hosts `ero.govt.nz`, `www.ero.govt.nz`

ERO institution pages contain current and previous reports in HTML. The connector preserves the institution URL, report type/date where published, and section-level provenance (`section_heading` and stable ordinal within the fetched page). `actions` selects only explicitly labelled next-step, action, improvement, priority and expected-outcome sections; it does not synthesize a judgement or score.

ERO changed its school report format in 2026, so historical framework and report headings remain as published. Closed institutions may no longer appear online. Access challenges are explicit blocked states and user-configured proxy routing remains supported.
