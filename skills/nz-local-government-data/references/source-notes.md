# NZ local government data source notes

## Stats NZ / data.govt.nz local authority statistics

- Issue starting point: `https://catalogue.data.govt.nz/dataset/groups/local-authority-statistics`
- Live CKAN fallback used by the CLI: `package_search` with `groups:local-and-regional-government` and local-authority search terms.
- Outputs preserve dataset/resource URLs, `metadata_modified`, resource formats, datastore flags, and licence metadata where CKAN exposes it.
- Resource formats vary. The CLI previews CKAN datastore resources or CSV links only; other formats are listed for follow-up.

## DIA Local Councils downloadable data index

- HTTPS URL: `https://www.localcouncils.govt.nz/lgip.nsf/wpg_url/Resources-Download-Data-Index`
- HTTP fallback: `http://www.localcouncils.govt.nz/lgip.nsf/wpg_url/Resources-Download-Data-Index`
- Live testing showed the HTTPS host can fail for Python clients with `TLSV1_UNRECOGNIZED_NAME`; the CLI tries HTTPS first and records fallback use.
- Machine-readable examples discovered on the page include rates rebates statistics CSV/XLSX and dog control statistics XLSX. The page also links to LTP and other HTML/PDF resources.

## DIA local government performance metrics

- Source page: `https://www.dia.govt.nz/local-government-performance-metrics`
- The page links PDFs for council groups and an XLSX data release for council profiles. The CLI finds the data release link dynamically by label.
- The current workbook observed during implementation is a compact one-sheet XLSX with columns such as `Council`, `Code`, `Population for 2024 (no.)`, `Land area for 2025 (km²)`, and `Total rates revenue for 2024 ($000)`.
- Council `Code` values are DIA profile groups, not universal council identifiers:
  - `A` Auckland Council group
  - `U` unitary authority group
  - `RC` regional council group
  - `M` large metro group
  - `MP` small metro / large provincial group
  - `PR` small provincial / rural group
  - `CI` Chatham Islands Council

## OAG local-government insights

- Source page: `https://oag.parliament.nz/2025/local-govt`
- This is official analysis/context rather than a machine-readable council dataset in the CLI.
- Some automated clients receive HTTP 403. Treat that as a fetch limitation and cite the URL rather than scraping around access controls.

## Caveats to communicate

- Discovery coverage depends on official source pages and CKAN metadata remaining available.
- PDF-only sources are listed, not transformed into tabular data.
- DIA profile metrics are useful for simple comparisons, but are not a full spending ledger and should not be described as complete rates-spend transparency.
- Check source pages for licence/reuse terms before redistribution.
