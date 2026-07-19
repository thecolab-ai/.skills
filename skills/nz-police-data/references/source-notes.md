# Source notes

- Owner/source: New Zealand Police, `https://www.police.govt.nz/.../policedatanz`
- Primary source: https://www.police.govt.nz/about-us/publications-statistics/data-and-statistics/policedatanz
- Authentication: none
- Last verified: 2026-07-19
- Presentation: Police-owned catalogue pages embedding workbooks hosted at `public.tableau.com`
- Access: public and read-only; monthly update on the last working day; CC BY 4.0

The CLI parses the live official report catalogue and each report's exact Tableau workbook/view
reference. Police does not publish a stable documented row-query API, so `trend`, `area` and
`demographics` return exit 7 rather than unrelated catalogue records. `datasets` discovers official
reports and `definitions` provides the source's RCVS/RCOS scope and update cadence.

Recorded victimisations and proceedings do not measure all underlying crime. The Tableau reports' suppression, rounding and privacy rules remain authoritative. Do not attempt re-identification or produce person/address-level or predictive-policing outputs.
