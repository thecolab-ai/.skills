# Source notes

- Owner/source: Education Review Office, `https://www.ero.govt.nz/review-reports`
- Authentication: none
- Last verified: 2026-10-08
- Institution pages: `/institution/{education-institution-number}`
- Access: public and read-only; hosts `ero.govt.nz`, `www.ero.govt.nz`

Discovery now uses the official `ReportsApi/GetReports` index to resolve the current institution URL, and the connector then parses the institution page HTML. The connector preserves the institution URL, report type/date where published, and section-level provenance (`section_heading` and stable ordinal within the fetched page). `actions` selects only explicitly labelled next-step, action, improvement, priority and expected-outcome sections; it does not synthesize a judgement or score.

ERO changed its school report format in 2026, so historical framework and report headings remain as published. Closed institutions may no longer appear online. Access challenges are explicit blocked states and user-configured proxy routing remains supported.

Current reports place the signed publication date inside the h3/h4 body beneath a school/month h2. The parser finds it only within that report, excludes Other/Past Reports listing blocks and "Page updated:" footer dates (8 October 2026: institution 280 otherwise reported a "Past Reports" block dated by its 28 September 2026 footer), and handles HTML void elements without corrupting heading depth. Empty unrecognisable report pages fail as schema errors.
