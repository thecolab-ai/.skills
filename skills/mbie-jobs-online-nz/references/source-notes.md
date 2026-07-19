# Source notes

- Owner/source: MBIE Jobs Online
- Primary source: https://www.mbie.govt.nz/business-and-employment/employment-and-skills/labour-market-reports-data-and-analysis/jobs-online
- Authentication: none
- Last verified: 2026-07-19
- Parsed export: `Jobs Online - All unadjusted quarterly data consolidated`, current March 2026 file
- CSV schema: `ACTUAL_DATE`, `KEYA` geography, `KEYBB` published series, `AVI_SUM` index
- Access: public and read-only; hosts `mbie.govt.nz`, `www.mbie.govt.nz`

Each `KEYBB` label is classified against MBIE's industry, ANZSCO occupation-group and skill-level
vocabularies, and the `dimension` is retained on every row. Industry and occupation commands require
that dimension, so they cannot silently cross-match the wrong family. Unknown future labels remain
`unknown` and are excluded from those filters.

AVI values are indices based on raw unweighted online advertisements, not vacancy or hiring counts. Current quarterly data are not seasonally adjusted, so MBIE recommends annual comparisons. The export URL is versioned by release and should be updated when MBIE publishes a new consolidated file; schema changes fail closed.
