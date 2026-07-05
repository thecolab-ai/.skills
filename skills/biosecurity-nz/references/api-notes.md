# API Notes

Probed on 2026-07-05 from the Codex runner.

## Official NZ Pest Register

- Landing page: `https://onzpr.mpi.govt.nz/`
- Importer host/detail pages: `https://pierpestregister.mpi.govt.nz/`
- data.govt.nz CKAN metadata:
  `https://catalogue.data.govt.nz/api/3/action/package_show?id=the-official-new-zealand-pest-register`
- The CKAN resource points to `https://onzpr.mpi.govt.nz/`, has format `Online database`, and does not expose a CKAN datastore table.
- Search/autocomplete endpoints found in ONZPR page JavaScript:
  - `GET https://onzpr.mpi.govt.nz/pest-api.php?method=AutoPopulateFreeSearch&term=fruit`
  - `GET https://onzpr.mpi.govt.nz/pest-api.php?method=FilterScientificName&term=fruit&page=1`
  - `GET https://onzpr.mpi.govt.nz/pest-api.php?method=FilterOrganismType&term=`
  - `POST https://onzpr.mpi.govt.nz/pest-api.php?method=GetTableDataAjax`
- `GetTableDataAjax` accepts form fields:
  - `param`: JSON string, for example `{"SearchText":"fruit fly"}` or `{"Notifiable":1}`
  - `draw`, `start`, `length`: DataTables paging fields
- Useful query keys observed in page JavaScript:
  - `SearchText`
  - `ScientificName`
  - `OrganismType`
  - `RegulatoryStatus` (`1` regulated, `2` non-regulated, `3` not assessed, combinations up to `7`)
  - `Unwanted` (`1`, `0`, or `2` for both)
  - `Notifiable` (`1`, `0`, or `2` for both)
  - `hsnoStatus`
- Detail page pattern:
  `https://pierpestregister.mpi.govt.nz/pest-register-importing/pest-details/?id=111`
- Action upon interception page pattern:
  `https://pierpestregister.mpi.govt.nz/pest-register-importing/pest-details/action-upon-interception/?id=111`

## PIER Import Requirements

- Landing page: `https://piersearch.mpi.govt.nz/`
- data.govt.nz CKAN metadata:
  `https://catalogue.data.govt.nz/api/3/action/package_show?id=product-import-export-requirements`
- Commodity suggestions JavaScript:
  `https://piersearch.mpi.govt.nz/import-commodity-names.js?m=1782914077`
- Commodity type resolver:
  `https://piersearch.mpi.govt.nz/pier-api.php?url=CommodityNames/Apple/Types?searchType=import`
- Commodity-only result page pattern:
  `https://piersearch.mpi.govt.nz/importing-commodities-to-new-zealand/search-by-commodity-only/search-results/?commodityName=Apple&commodityType=5`
- Country list modal pattern:
  `https://piersearch.mpi.govt.nz/importing-commodities-to-new-zealand/search-by-commodity-only/search-results//ImportCountriesList?commodityName=Apple&commodityType=5&commodityID=61`
- Import requirement page pattern:
  `https://piersearch.mpi.govt.nz/importing-commodities-to-new-zealand/import-requirements/?country=120&commodity=61`

## MPI Responses And Notifiable Sources

- Active response index:
  `https://www.mpi.govt.nz/biosecurity/exotic-pests-and-diseases-in-new-zealand/active-biosecurity-responses-to-pests-and-diseases`
- Notifiable organisms source page:
  `https://www.mpi.govt.nz/biosecurity/about-biosecurity-in-new-zealand/registers-and-lists`
- Notifiable organisms PDF landing:
  `https://www.mpi.govt.nz/dmsdocument/6403-Biosecurity-Notifiable-Organisms-Order-2016`
- Legislation source:
  `https://www.legislation.govt.nz/regulation/public/2016/0073/latest/whole.html`

## Access Caveats

- `www.mpi.govt.nz`, `www.biosecurity.govt.nz`, `onzpr.mpi.govt.nz`, `pierpestregister.mpi.govt.nz`, and `piersearch.mpi.govt.nz` use Imperva/Incapsula.
- Some ONZPR and PIER endpoints were accessible from the Codex runner during probing, but MPI active-response HTML returned an Incapsula challenge page. The CLI treats that as a structured `status: "blocked"` result.
- Do not bypass CAPTCHA, request-auth, or browser integrity checks. If direct HTTP is blocked, return the source URL and caveat rather than inventing data.
- PIER and ONZPR pages are public regulatory tools, but summaries from this skill are not legal import advice. Always verify final decisions against MPI source pages and official documents.
