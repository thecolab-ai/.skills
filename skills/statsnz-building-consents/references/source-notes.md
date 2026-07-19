# Source notes

- Primary owner: Stats NZ
- Metadata: https://datainfoplus.stats.govt.nz/item/nz.govt.stats/ee083b32-8c10-4ccf-b1ee-a4990b27273c
- Current verified release: https://www.stats.govt.nz/information-releases/building-consents-issued-may-2026/
- Access mode: bounded first-party HTML metadata plus linked XLSX workbook
- Authentication: none
- Last verified: 2026-07-19
- Update cadence: monthly

## Implemented source contract

The release HTML contains a `pageViewData` JSON attribute. It publishes release metadata, document links, and graph series as embedded CSV. The parser validates that the document and graph surfaces both exist. The linked official workbook is parsed read-only with `openpyxl`; each annual value carries its Stats NZ series reference, sheet/cell provenance, release URL, and retrieval time.

The current release supports monthly actual, seasonally adjusted and trend new-dwelling series; annual regional new-dwelling comparisons; and national building-type count, value, and floor-area series. Regional value and floor-area tables are not present in the release workbook. The connector returns exit 7 for non-national `value` requests and does not infer or reconstruct those values.

Time-series bounds are inclusive as entered. Month/day end bounds are converted internally to an
exclusive next-period boundary, so `--to 2026-05` cannot leak a June observation. Reversed ranges
return invalid input.

Consents are intentions or authorisations rather than completed buildings. Published values may be revised, and geography and classification changes must be retained when comparing releases.
