# Education Counts NZ API Notes

## Source Shape

Education Counts teacher workforce data is published on public HTML pages with downloadable Excel workbooks and PDF indicator reports. The relevant source pages are:

- Initial teacher education statistics: `https://www.educationcounts.govt.nz/statistics/initial-teacher-education-statistics`
- Entering and leaving teaching: `https://www.educationcounts.govt.nz/statistics/teacher-movement`
- Teacher turnover: `https://www.educationcounts.govt.nz/statistics/teacher-turnover`
- Teacher numbers: `https://www.educationcounts.govt.nz/statistics/teacher-numbers`
- Teacher Demand and Supply Planning Projection series: `https://www.educationcounts.govt.nz/publications/series/a-summary-of-the-teacher-demand-and-supply-planning-tool`

The pages can return HTTP 403 to plain HTTP clients even though the content is public. Commands classify HTTP 403 and HTTP 429 as `blocked` so agents can report source access accurately instead of treating the source as missing.

## Workbook Handling

The CLI parses `.xlsx` files with Python standard-library ZIP/XML tooling. It reads workbook sheet names, shared strings, inline strings, and cached cell values. It normalises rows by locating a header row with year columns when possible, then emits long-form records with source metadata.

Legacy `.xls` binaries and PDFs are not parsed because that would require non-stdlib dependencies. They are still listed by `resources` with `format` and `source_url` fields.

## Blocked Source Handling

The skill does not embed Education Counts result rows. If a source page or workbook is blocked, the command returns `status: "blocked"` with the upstream URL and a short explanation. Use `workbook --url` with a user-supplied public workbook URL or local `file://` path when the user has already obtained the file through a browser.

## Reporting Caveats

- Education Counts notes that ITE table totals and counts are rounded, so component rows may not sum to totals.
- ITE sector of qualification can be indicative where derived from courses studied.
- Teacher movement/leaving data lags entering data because leaving status requires the following year's workforce status.
- Workforce pages distinguish headcount from full-time teacher equivalent (FTTE), regular teachers from day relief, and total response ethnicity from prioritised ethnicity.
