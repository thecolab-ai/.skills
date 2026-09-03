# Source notes

Last verified: 2026-09-03

## Primary surfaces

- Canonical List landing page: <https://www.heritage.org.nz/list-details>
- Full List CSV export: <https://hnzpt-prod-web.azurewebsites.net/api/report/GetPlaceListCsv>
- Source owner: Heritage New Zealand Pouhere Taonga
- Authentication: none
- Access: read-only HTTPS GET

The landing page is the canonical source URL. Its deployed Next.js chunk (`/_next/static/chunks/332-6c747a831ed918bd.js` when verified) builds the unfiltered download URL as `/api/report/GetPlaceListCsv` against the `hnzpt-prod-web.azurewebsites.net` API origin. The chunk filename is deployment-specific and is evidence, not a stable interface.

## Live verification

Verified 2026-09-03 before scaffolding:

- `https://www.heritage.org.nz/list-details` returned HTTP 200 and `text/html; charset=utf-8`.
- `https://hnzpt-prod-web.azurewebsites.net/api/report/GetPlaceListCsv` returned HTTP 200, `text/csv`, and `attachment; filename=place-list.csv`.
- The export was 2,368,448 bytes and contained 7,361 data rows at verification time.
- The first observed data row had List number `9997`, name `Tait House`, type `Historic Place Category 2`, status `Listed`, and council `Christchurch City`.

Row counts, ordering, deployment chunk names, and entries are observations rather than permanent invariants. The smoke test therefore asserts a conservative non-empty scale and the required schema, not an exact live count or sample entry.

## Required CSV schema

The parser fails closed with exit code 6 if any required column disappears:

| Source column | CLI field | Searchable | Returned |
|---|---|---:|---:|
| `ListNumber` | `list_number` | yes | yes |
| `Name` | `name` | yes | yes |
| `ListEntryType` | `entry_type` | yes | yes |
| `ListEntryStatus` | `entry_status` | yes | yes |
| `DateEntered` | `date_entered` | no | exact lookup only |
| `DateOfEffect` | `date_of_effect` | no | exact lookup only |
| `Address` | `address` | yes | yes |
| `LegalDescription` | internal parser field | no | no |
| `ExtentOfListEntry` | internal parser field | no | no |
| `DistrictCouncil` | `district_council` | yes | yes |
| `NZAANumbers` | `nzaa_numbers` | no | exact lookup only |

`NZAANumbers` is normalised from the bracketed comma-separated source field to a JSON string array. Other fields remain source strings; the CLI does not reinterpret dates or claim that an address is a legal parcel identifier.

## Retrieval policy

Each command performs one bounded official CSV request:

- 10-second timeout
- 10 MB response cap
- exact redirect-host allowlist
- no cache and no bundled upstream dataset
- no filtered-export endpoint or hidden write action

Search filtering is local and deterministic after the official download. Search output is capped at 100 records. The full source body is not saved or emitted.

## Deterministic fixture

`tests/fixtures/place-list-sample.csv` is a small synthetic fixture shaped like the observed public schema. It contains invented names, addresses, legal descriptions, and identifiers; it is not copied from the live export. It covers UTF-8, quoting, commas, multiline CSV cells, multiple entry types/statuses, and NZAA normalisation.
