# ComCom Connectivity Map Source Notes

## Public Sources

- Telecommunications Connectivity Map page:
  `https://www.comcom.govt.nz/regulated-industries/telecommunications/monitoring-the-telecommunications-market/telecommunications-connectivity-map/`
- Annual monitoring report page:
  `https://www.comcom.govt.nz/regulated-industries/telecommunications/monitoring-the-telecommunications-market/annual-monitoring-report/`

The connectivity-map page currently embeds the public map through
`https://comcom.emtel.co.nz/publicWebsite/` and links a provider-list workbook.
The annual monitoring page links report PDFs and questionnaire workbooks.

## Coverage vs Availability

The ComCom page says the map is based on information supplied by broadband
providers and is a point-in-time view. The CLI therefore treats the map as
coverage evidence, not proof that a user can order service at a specific
address.

The page also describes a parcel threshold for wireless broadband coverage. The
CLI exposes the threshold as `methodology.parcel_threshold` when the wording is
present.

## Fetch-State Classification

- `direct_http`: the source was fetched directly with Python standard-library
  HTTP.
- `blocked_by_upstream`: HTTP 403/429 or an Incapsula/bot-challenge style HTML
  response. This is distinct from a dead source.
- `dead_link`: a non-blocking HTTP error such as a missing file.
- `not_discovered`: the ComCom page was reachable, but no public layer URL was
  present in the HTML.

The CLI does not solve CAPTCHA, log in, mutate state, or scrape private provider
systems.

## PDF and Workbook Limits

The annual reports are public PDFs. This skill links the PDFs and classifies
them as source documents, but does not text-extract tables from them.

The provider list is an XLSX workbook. The CLI includes a small standard-library
XLSX preview so agents can confirm the workbook shape without adding
dependencies.
