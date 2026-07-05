# GETS procurement NZ source notes

## GETS

Public base:

```text
https://www.gets.govt.nz
```

Verified public surfaces:

- `ExternalRSSFeed.htm` - RSS 2.0 feed of open tenders/quotes. Items include title, link, RFx ID, organisation, open date, close date, categories, and publication date.
- `ExternalIndex.htm` - current tender list table.
- `ExternalLateTenderList.htm` - late tender list table.
- `ExternalClosedTenderList.htm` - closed tender list table.
- `ExternalAwardedTenderList.htm` - completed/award notice list table.
- `ExternalTenderSearching.htm?SearchingText=<query>` - public search result table.
- `ExternalTenderDetails.htm?id=<rfx-id>` - public detail page for one RFx ID. The agency path prefix is optional for public detail reads.

GETS detail pages expose public notice metadata and overview text. Some full tender documents, subscriptions, questions, or response actions require GETS login and must be treated as out of scope.

## Award notices and open data

MBIE publishes the "New Zealand Government procurement award notices" dataset through data.govt.nz CKAN metadata:

```text
https://catalogue.data.govt.nz/api/3/action/package_show?id=new-zealand-government-procurement-award-notices
```

The package lists CSV resources for award notices, regions, suppliers, and product categories, plus MBIE source URLs under:

```text
https://www.mbie.govt.nz/assets/Data-Files/NZGPP-GETS-Open-Data/
```

During implementation, the CKAN metadata was keyless and readable, but the MBIE asset host returned HTTP 403 to local automated clients. The CLI therefore exposes the source URLs through `datasets sources` and uses GETS completed-tender HTML for the working `awards` command.

The MBIE open-data page notes the award-notice report is updated quarterly and includes records from 1 July 2019 to 24 February 2025, with historic data from 29 July 2014 to 30 June 2019.

## Significant service contracts

Public page:

```text
https://www.procurement.govt.nz/data-and-reporting/reporting/significant-service-contracts-framework/
```

Verified public workbook:

```text
https://www.procurement.govt.nz/assets/procurement-property/documents/significant-services-contract-dashboard.xlsx?m=ca63730c2622cedad7f919fed42e140be24ba4db
```

The workbook is an aggregate dashboard. It includes key figures and top-provider lists for March 2020 and September 2020, but it is not a contract-by-contract register. The page says agencies are not required to submit significant service contract reports until further notice, and flags some commercially sensitive content as login-restricted.

## Parsing caveats

- Prefer RSS/XML and CKAN metadata where possible.
- GETS list and detail HTML is parsed conservatively from table rows and label cells. If the upstream table layout changes, commands should fail clearly rather than guess.
- Dates are returned as displayed by GETS unless they come from the significant-service-contract workbook, where Excel serial dates are converted to ISO dates.
- All commands are read-only and keyless.
