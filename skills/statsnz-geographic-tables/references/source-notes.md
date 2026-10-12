# Source notes

- Publisher: Stats NZ
- Primary source: https://datafinder.stats.govt.nz/table/122777-current-geographic-boundaries-table/
- Authentication: none
- Last verified: 2026-10-12
- Data licence: Creative Commons Attribution 4.0 International (`cc-by`, version 4.0). Verified from the `license` object on both table documents. The licence full text served by Datafinder begins "Attribution 4.0 International".
- Attribution: Stats NZ, Creative Commons Attribution 4.0 International.
- Host: `datafinder.stats.govt.nz` only. No API key is sent.
- Code licence of this skill is MIT and does not set the data licence.

## Tables

| ID | Page | Role |
|---|---|---|
| 122777 | https://datafinder.stats.govt.nz/table/122777-current-geographic-boundaries-table/ | Current Geographic Boundaries Table. A geography-version index. |
| 123518 | https://datafinder.stats.govt.nz/table/123518-geographic-areas-table-2026/ | Geographic Areas Table 2026. A meshblock concordance. |

Metadata URL: `https://datafinder.stats.govt.nz/services/api/v1/tables/{id}/`

The published sample URL is taken from `data.sample` on that document. On 2026-10-12 it was `/services/api/v1/tables/{id}/versions/{version}/data/sample/`. Version ids change when Stats NZ republishes; the CLI does not hard-code them.

Checked the same day:

- 122777 `feature_count` 47, `published_at` 2026-03-29T20:36:31.056278Z, sample 47 rows and 8498 bytes.
- 123518 `feature_count` 57575, `published_at` 2026-03-31T21:23:43.468268Z, sample 50 rows, 101 columns, and 75217 bytes.

`published_at` is the Koordinates publication timestamp. It is not a census reference period. Geography names can include trailing spaces and non-breaking spaces; those characters are preserved. Meshblock codes with a leading zero stay strings.

## Bounds

- Timeout: 15 seconds per request.
- Body cap: 256 KiB. A larger body is a schema failure, not a partial table.
- Sample cap: 200 rows. The CLI does not page and does not call an export.
- Smoke fetches metadata and the sample for table 122777 only.
- The keyed `/services/query/` API and any export path are refused. This skill does not ask for an API key.
- `created_by` on the table or version document is a user profile and is dropped.

`stats-nz` covers CPI, GDP, population, migration, and the large-datasets CSV catalogue. It does not read these Datafinder tables.
